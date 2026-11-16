"""The one place that runs component code, and the one place that decides the mode.

Two modes, decided once when the app starts and recorded in every run:
- demo: our own demo components run as local processes with a time limit. Not isolated.
- isolated: the same components run inside a locked-down container (no network, read-only, non-root,
  CPU / memory / process / time limits). Only when Docker is running AND our image was prepared beforehand.

Either way exactly one program is started per test run: our own batch driver
(demo/components/harness/driver.py), which is handed one JSON job on standard input. The container
command is one fixed list (DOCKER_RUN_FLAGS). Nothing in it comes from a request, a file or the database,
there is no host folder mounted, and this module never builds or downloads an image (only
`python -m app.prepare` does). A run never falls back from one mode to the other.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from app import real_libraries
from app.run.components import redact, scrub
from app.config import COMPONENTS_DIR, OPENSSL_IMAGE, PYTHON_BASE_IMAGE, Settings

DEMO_LINE = "Demo mode: running our own demo software, not isolated."
DEMO_IMAGES_MISSING = " Docker is running, but the test images are not prepared yet; ./run-demo.sh prepares them."
DEMO_FORCED = " Isolated mode is switched off for this run."
ISOLATED_LINE = "Isolated mode: our demo software runs in a locked-down container with no network."
# Phase 4c: what the isolated-mode line adds about the real libraries, by which of their images are prepared.
REAL_ALL_LINE = " Real libraries run the same way, each in its own container."
REAL_SOME_LINE = " Real libraries run the same way, each in its own container; not prepared on this computer: {missing}."
REAL_NONE_LINE = " The real libraries are not prepared on this computer; ./run-demo.sh prepares them."
ISOLATED_UNAVAILABLE_LINE = "Isolated mode was asked for, but it is not available on this computer, so tests that run software can't run."

# BatchResult.problem values (plain text; fixed, so callers can map them to reason codes)
PROBLEM_TIMEOUT = "timeout"
PROBLEM_ISOLATED = "isolated mode is not available"
PROBLEM_REAL_NEEDS_ISOLATED = "real software runs only in isolated mode"      # phase 4c: never as a local program
PROBLEM_REAL_IMAGE_MISSING = "this library's container image is not prepared"
PROBLEM_TOO_MUCH_OUTPUT = "too much output"
PROBLEM_NO_DONE = "the test harness stopped before it finished"
PROBLEM_BAD_LINE = "the test harness wrote something unreadable"
PROBLEM_NOT_STARTED = "the test harness could not be started"
PROBLEM_REFUSED_PREFIX = "the test harness refused the job: "

MAX_OUTPUT_BYTES = 1024 * 1024
STDERR_TAIL = 2000
IMAGE_REPOSITORY = "evidence-lab-components"
CONTAINER_LABEL = "evidence-lab=1"
CONTAINER_DRIVER = "/opt/evidence-lab/components/harness/driver.py"
LOCAL_DRIVER = COMPONENTS_DIR / "harness" / "driver.py"

# The ONE fixed flag list for running components in a container. No -v, no --privileged, no --device, no -e.
DOCKER_RUN_FLAGS: tuple[str, ...] = (
    "--rm", "-i", "--pull", "never", "--label", CONTAINER_LABEL, "--network", "none", "--read-only",
    "--tmpfs", "/scratch:rw,noexec,nosuid,nodev,size=64m,uid=65534,gid=65534,mode=700", "--workdir", "/scratch", "--user", "65534:65534",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "256m", "--memory-swap", "256m",
    "--cpus", "2", "--pids-limit", "64", "--ipc", "none", "--log-driver", "none",
)
CONTAINER_COMMAND: tuple[str, ...] = ("python", "-I", "-X", "pycache_prefix=/scratch/pyc", CONTAINER_DRIVER)
# In a real-library image (phase 4c) the same driver is told to read that image's own table of subjects.
REAL_CONTAINER_COMMAND: tuple[str, ...] = (*CONTAINER_COMMAND, "--real")
_DOCKER_ENV_KEYS = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR")


@dataclass(frozen=True)
class ModeInfo:
    name: str                     # "demo" | "isolated"
    line: str                     # the sentence shown on screen
    reason: str | None            # why not isolated, in plain words
    docker_running: bool
    components_image: str | None  # our image tag, only if it is present locally
    openssl_image: str | None     # the pinned OpenSSL checker image, only if it is present locally
    real_images: dict = field(default_factory=dict)  # phase 4c: family -> its image tag, only those present locally


@dataclass
class BatchResult:
    ok: bool
    lines: list[dict]
    problem: str | None
    mode: str
    command: str        # plain display text of what was run
    started_at: str
    duration_ms: int
    stderr_tail: str


# ------------------------------------------------------------------ docker helpers (read-only questions)

def _docker_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _DOCKER_ENV_KEYS if k in os.environ}
    env.setdefault("PATH", os.defpath)
    return env


def _docker(args: list[str], timeout: float) -> tuple[int | None, str]:
    """Run the docker client with an argument list. (None, "") when docker is missing or does not answer in time."""
    try:
        done = subprocess.run(["docker", *args], capture_output=True, text=True, errors="replace", timeout=timeout,
                              stdin=subprocess.DEVNULL, shell=False, env=_docker_env())
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return done.returncode, done.stdout


def components_image_tag() -> str:
    """Our image's tag, derived from the exact files in demo/components: change a file and the tag changes,
    so a stale image is never used by mistake."""
    digest = hashlib.sha256()
    files = sorted(p for p in COMPONENTS_DIR.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    for path in files:
        digest.update(path.relative_to(COMPONENTS_DIR).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
    return f"{IMAGE_REPOSITORY}:{digest.hexdigest()[:16]}"


def _files_digest(digest, folder) -> None:
    files = sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    for path in files:
        digest.update(path.relative_to(folder).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")


def real_image_tag(family: str) -> str:
    """The tag of one real-library image (phase 4c), derived from everything that goes into it: our harness and
    controls, the family's wrapper folder, and the pins of the library's own files. Change any and the tag changes."""
    pins = real_libraries.FAMILIES[family]
    digest = hashlib.sha256()
    _files_digest(digest, COMPONENTS_DIR)
    _files_digest(digest, real_libraries.REAL_DIR / family)
    for shared in pins.get("shared_files", []):   # phase 4d: a wrapper file another family's folder holds
        path = real_libraries.REAL_DIR / shared
        digest.update(shared.encode() + b"\0" + hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
    digest.update(json.dumps({"base": PYTHON_BASE_IMAGE, "images": pins["images"], "downloads": pins["downloads"]},
                             sort_keys=True).encode())
    return f"{real_libraries.IMAGE_REPOSITORY}-{family}:{digest.hexdigest()[:16]}"


def docker_running() -> bool:
    rc, _ = _docker(["version", "--format", "{{.Server.Version}}"], 3)
    return rc == 0


def image_present(reference: str) -> bool:
    rc, _ = _docker(["image", "inspect", "--format", "{{.Id}}", reference], 5)
    return rc == 0


_probe_cache: dict = {}
_PROBE_SECONDS = 15.0


def _probe() -> tuple[bool, str | None, str | None]:
    """(docker running, our components tag if present, the OpenSSL image if present). Never builds or pulls.
    The answer is kept for a few seconds so that starting the app repeatedly (tests) stays quick."""
    now = time.monotonic()
    if _probe_cache and now - _probe_cache["at"] < _PROBE_SECONDS:
        return _probe_cache["value"]
    value: tuple[bool, str | None, str | None] = (False, None, None)
    if docker_running():
        tag = components_image_tag()
        value = (True, tag if image_present(tag) else None, OPENSSL_IMAGE if image_present(OPENSSL_IMAGE) else None)
    _probe_cache.update(at=now, value=value)
    return value


_real_cache: dict = {}


def _probe_real(running: bool) -> dict:
    """family -> its image tag, for the real-library images that are present locally (phase 4c). Never builds or pulls."""
    if not running:
        return {}
    now = time.monotonic()
    if _real_cache and now - _real_cache["at"] < _PROBE_SECONDS:
        return dict(_real_cache["value"])
    value = {}
    for family in real_libraries.FAMILIES:
        tag = real_image_tag(family)
        if image_present(tag):
            value[family] = tag
    _real_cache.update(at=now, value=value)
    return dict(value)


def real_line(real_images: dict) -> str:
    """What the isolated-mode line says about the real libraries: all prepared, some (naming the missing ones), or none."""
    missing = [real_libraries.FAMILIES[f]["label"] for f in real_libraries.FAMILIES if not real_images.get(f)]
    if not missing:
        return REAL_ALL_LINE
    return REAL_NONE_LINE if len(missing) == len(real_libraries.FAMILIES) else REAL_SOME_LINE.format(missing=", ".join(missing))


def detect_mode(settings: Settings) -> ModeInfo:
    running, components, openssl = _probe()
    if settings.force_mode == "demo":
        return ModeInfo("demo", DEMO_LINE + DEMO_FORCED, "Isolated mode is switched off for this run.", running, components, openssl)
    if running and components:
        real = _probe_real(running)
        return ModeInfo("isolated", ISOLATED_LINE + real_line(real), None, True, components, openssl, real)
    reason = ("Docker is running, but the test images are not prepared yet." if running else "Docker is not running.")
    if settings.force_mode == "isolated":  # asked for, not available: say so; never quietly run un-isolated instead
        return ModeInfo("isolated", ISOLATED_UNAVAILABLE_LINE, reason, running, None, openssl)
    return ModeInfo("demo", DEMO_LINE + (DEMO_IMAGES_MISSING if running else ""), reason, running, components, openssl)


STALE_AFTER_SECONDS = 900.0  # three times the longest job time limit (300 s): nothing of a live run is this old


def sweep_stale_containers(older_than: float = STALE_AFTER_SECONDS) -> None:
    """Remove containers of ours left behind by an earlier crash. Only ones older than any run can be, so a
    test running in another copy of the app (the accuracy check, the tests) is never touched.
    Quietly does nothing without Docker."""
    rc, out = _docker(["ps", "-aq", "--filter", f"label={CONTAINER_LABEL}"], 5)
    ids = out.split() if rc == 0 else []
    if not ids:
        return
    # rc may be non-zero when one of them ended meanwhile; the lines that were printed are still good
    _, out = _docker(["inspect", "--format", "{{.Id}} {{.Created}}", *ids], 10)
    now, stale = datetime.now(timezone.utc), []
    for line in out.splitlines():
        cid, _, created = line.strip().partition(" ")
        try:  # for example 2026-11-11T10:00:00.123456789Z; whole seconds are enough
            made = datetime.strptime(created[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue  # unreadable date: leave it alone
        if cid and (now - made).total_seconds() >= older_than:
            stale.append(cid)
    if stale:
        _docker(["rm", "-f", *stale], 20)


# ------------------------------------------------------------------ running one job

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _describe_job(job: dict) -> str:
    op = job.get("op") if isinstance(job, dict) else None
    if op == "call":
        return f"call: {job.get('subject')} {job.get('command')}"
    if op == "verify_batch":
        cases, subjects = job.get("cases"), job.get("subjects")
        return (f"verify_batch: {len(cases) if isinstance(cases, list) else '?'} cases, one verify call per case, "
                f"on {', '.join(map(str, subjects)) if isinstance(subjects, list) else '?'}")
    if op == "roundtrip":
        return f"roundtrip: {job.get('subject')} keygen, sign, verify (the test key stays inside the harness)"
    if op == "bench_rounds":
        subjects = job.get("subjects")
        return (f"bench_rounds: {job.get('rounds')} rounds of {job.get('repeats')} sign+verify, "
                f"on {', '.join(map(str, subjects)) if isinstance(subjects, list) else '?'}")
    if op == "kat_batch":
        cases = job.get("cases")
        return (f"kat_batch: {len(cases) if isinstance(cases, list) else '?'} official cases, one adapter call per case, "
                f"on {job.get('subject')} (answers are reported as SHA-256 fingerprints only)")
    if op == "kem_roundtrip":
        return f"kem_roundtrip: {job.get('subject')} keygen, encaps, decaps (keys and shared secrets stay inside the harness)"
    return "unknown job"


class ComponentRunner:
    """Runs the batch driver once per job, in the mode it was created with."""

    def __init__(self, mode: ModeInfo):
        self.mode = mode

    # The two command lines. Nothing from the job reaches either of them: the job only travels on stdin.
    def _container_argv(self, name: str, family: str | None = None) -> list[str]:
        if family is not None:  # a real library: its own image, the same flags, the driver told to read the image's table
            return ["docker", "run", "--name", name, *DOCKER_RUN_FLAGS, str(self.mode.real_images[family]), *REAL_CONTAINER_COMMAND]
        return ["docker", "run", "--name", name, *DOCKER_RUN_FLAGS, str(self.mode.components_image), *CONTAINER_COMMAND]

    @staticmethod
    def _local_argv(scratch: str) -> list[str]:
        return [sys.executable, "-I", "-X", f"pycache_prefix={os.path.join(scratch, 'pyc')}", str(LOCAL_DRIVER)]

    def _display(self, job: dict, family: str | None = None) -> str:
        what = redact(_describe_job(job))[:300]
        if family is not None:
            image = self.mode.real_images.get(family) or f"(the {family} image, not prepared)"
            return f"docker run {' '.join(DOCKER_RUN_FLAGS)} {image} {' '.join(REAL_CONTAINER_COMMAND)}    (job on stdin: {what})"
        if self.mode.name == "isolated":
            return (f"docker run {' '.join(DOCKER_RUN_FLAGS)} {self.mode.components_image} {' '.join(CONTAINER_COMMAND)}"
                    f"    (job on stdin: {what})")
        return f"python -I demo/components/harness/driver.py    (job on stdin: {what})"

    def run_job(self, job: dict, *, time_limit: float = 120.0,
                on_line: Callable[[dict], None] | None = None, family: str | None = None) -> BatchResult:
        """`family` names a real library's image (phase 4c). Such a job runs only there, in isolated mode: never
        as a local process, and never in another image."""
        started, t0 = _now(), time.perf_counter()
        isolated = self.mode.name == "isolated"
        display = self._display(job, family)

        def result(ok: bool, lines: list[dict], problem: str | None, stderr: bytes = b"") -> BatchResult:
            tail = redact(stderr[-STDERR_TAIL:].decode("utf-8", "replace"))
            return BatchResult(ok, lines, problem, self.mode.name, display, started,
                               int((time.perf_counter() - t0) * 1000), tail)

        if family is not None and not isolated:
            return result(False, [], PROBLEM_REAL_NEEDS_ISOLATED)
        if isolated and not (self.mode.docker_running and self.mode.components_image):
            return result(False, [], PROBLEM_ISOLATED)
        if family is not None and not self.mode.real_images.get(family):
            return result(False, [], PROBLEM_REAL_IMAGE_MISSING)
        payload = json.dumps(job).encode("utf-8")
        name = "evlab-" + secrets.token_hex(6)
        with tempfile.TemporaryDirectory(prefix="evidence-lab-run-") as scratch:
            if isolated:
                argv, env, cwd = self._container_argv(name, family), _docker_env(), scratch
            else:
                argv, cwd = self._local_argv(scratch), scratch
                env = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"}
            try:
                proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        cwd=cwd, env=env, shell=False, start_new_session=True)
            except OSError:
                return result(False, [], PROBLEM_ISOLATED if isolated else PROBLEM_NOT_STARTED)
            try:
                return self._converse(proc, payload, name, isolated, time_limit, on_line, result)
            finally:
                self._stop(proc, name, isolated)

    def _converse(self, proc, payload: bytes, name: str, isolated: bool, time_limit: float, on_line, result) -> BatchResult:
        events: queue.Queue = queue.Queue()
        stderr_chunks: list[bytes] = []

        def feed() -> None:
            try:
                proc.stdin.write(payload)
                proc.stdin.close()
            except OSError:
                pass

        def read_out() -> None:
            total, pending = 0, b""
            while True:
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_OUTPUT_BYTES:
                    events.put(("overflow", None))
                    return
                pending += chunk
                *whole, pending = pending.split(b"\n")
                for line in whole:
                    events.put(("line", line))
            if pending.strip():
                events.put(("line", pending))
            events.put(("eof", None))

        def read_err() -> None:
            kept = 0
            while True:
                chunk = os.read(proc.stderr.fileno(), 65536)
                if not chunk:
                    return
                if kept < 4 * STDERR_TAIL:  # keep a little, keep draining so the program never blocks on stderr
                    stderr_chunks.append(chunk[:4 * STDERR_TAIL])
                    kept += len(chunk)

        for target in (feed, read_out, read_err):
            threading.Thread(target=target, daemon=True).start()

        deadline = time.monotonic() + time_limit
        lines: list[dict] = []
        done_line: dict | None = None
        problem: str | None = None
        while True:
            try:
                kind, raw = events.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                problem = PROBLEM_TIMEOUT
                break
            if kind == "overflow":
                problem = PROBLEM_TOO_MUCH_OUTPUT
                break
            if kind == "eof":
                break
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = None
            if not isinstance(parsed, dict) or done_line is not None:
                problem = PROBLEM_BAD_LINE
                break
            parsed = scrub(parsed)
            if parsed.get("done") is True:
                done_line = parsed
                continue
            if "refused" in parsed:
                problem = PROBLEM_REFUSED_PREFIX + str(parsed["refused"])[:200]
                break
            lines.append(parsed)
            if on_line is not None:
                on_line(parsed)

        rc: int | None = None
        if problem is None:
            try:
                rc = proc.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                problem = PROBLEM_TIMEOUT
        self._stop(proc, name, isolated)
        stderr = b"".join(stderr_chunks)
        if problem is None:
            if isolated and rc in (125, 126, 127) and not lines and done_line is None:
                problem = PROBLEM_ISOLATED  # docker itself could not start the container; we do not run it un-isolated
            elif done_line is None or done_line.get("lines") != len(lines) or rc != 0:
                problem = PROBLEM_NO_DONE
        return result(problem is None, lines, problem, stderr)

    @staticmethod
    def _stop(proc, name: str, isolated: bool) -> None:
        """Make sure nothing is left running: kill the process group, and for a container kill and remove it by name."""
        if proc.poll() is None:
            if isolated:
                _docker(["kill", name], 10)
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, PermissionError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            if isolated:
                _docker(["rm", "-f", name], 10)
        else:
            if not isolated:  # the driver has ended; make sure no child of it lingers
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (OSError, PermissionError):
                    pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
