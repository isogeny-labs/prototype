"""Adam's Otto harness, at one pinned commit.

backend/otto.lock.json names the repository, the commit, the version and one SHA-256 over the files of that
commit. The prepare step (app.prepare) fetches exactly that commit into backend/.otto/<commit>/; the app never
downloads anything. Here the copy is checked against the pinned fingerprint and loaded by path, because Otto has
no packaging file. If it is missing or different, the app works as before and says why (status().reason).

Otto's own code is standard-library Python. Its Rust "snark" tool, the Lean prover and its model judge are not
used by this app and are neither built nor called.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

BACKEND_DIR = Path(__file__).resolve().parents[2]
LOCK_PATH = BACKEND_DIR / "otto.lock.json"
# Where the pinned copy is kept: one folder per pinned commit, ignored by git. EVIDENCE_LAB_OTTO_HOME names another
# folder (the end-to-end walk uses an empty one to show the app without Otto). Wherever it is, the copy is used only
# if its fingerprint is the pinned one.
HOME_ENV = "EVIDENCE_LAB_OTTO_HOME"
OTTO_HOME = Path(os.environ[HOME_ENV]).resolve() if os.environ.get(HOME_ENV) else BACKEND_DIR / ".otto"
SOURCE_ENV = "EVIDENCE_LAB_OTTO_SOURCE"   # optional: a local git checkout of Otto to take the pinned commit from
FETCH_LIMIT_SECONDS = 180
MAX_FILE_BYTES = 16 * 1024 * 1024
_SKIP_DIRS = {"__pycache__", ".git"}
_MODULES = ("canonical", "ledger", "records", "lab", "loop", "verifiers")

NOT_FETCHED = ("it has not been fetched on this computer. ./run-demo.sh fetches it; that needs read access to the "
               "isogeny-labs/otto repository once")
NOT_PINNED_COPY = ("the copy on this computer is not the pinned one (its fingerprint is different). Delete the folder "
                   "backend/.otto and run ./run-demo.sh again")


class OttoNotInstalled(Exception):
    """Otto is not usable on this computer. str(exc) is the plain reason."""


@dataclass(frozen=True)
class Lock:
    repository: str
    url: str
    commit: str
    version: str
    tree_sha256: str

    @property
    def folder(self) -> Path:
        return OTTO_HOME / self.commit


@dataclass(frozen=True)
class OttoStatus:
    installed: bool
    reason: str | None          # why not, as the end of the sentence "Otto is not installed on this computer: ..."
    repository: str | None
    commit: str | None
    version: str | None
    path: Path | None

    @property
    def sentence(self) -> str:
        if self.installed:
            return f"Otto harness: version {self.version}, commit {str(self.commit)[:7]} (pinned)."
        return f"Otto is not installed on this computer: {self.reason}."


def read_lock(path: Path = LOCK_PATH) -> Lock:
    """The pin, or OttoNotInstalled when the file is missing or not what it must be."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        lock = Lock(repository=str(data["repository"]), url=str(data["url"]), commit=str(data["commit"]),
                    version=str(data["version"]), tree_sha256=str(data["tree_sha256"]))
    except (OSError, ValueError, KeyError, TypeError):
        raise OttoNotInstalled("its pin file (backend/otto.lock.json) can't be read") from None
    hexdigits = set("0123456789abcdef")
    if len(lock.commit) != 40 or set(lock.commit) - hexdigits or len(lock.tree_sha256) != 64 or set(lock.tree_sha256) - hexdigits \
            or not lock.url.startswith("https://"):
        raise OttoNotInstalled("its pin file (backend/otto.lock.json) does not name a full commit and fingerprint")
    return lock


def tree_sha256(folder: Path) -> str:
    """One fingerprint over every regular file under the folder: for each file, in path order, its path and the
    SHA-256 of its bytes. Folders named __pycache__ and .git, compiled .pyc files and links are left out, so
    running Otto from the folder does not change it."""
    lines = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for name in sorted(files):
            path = Path(root) / name
            if name.endswith(".pyc") or path.is_symlink() or not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{path.relative_to(folder).as_posix()}\n{digest}\n")
    return hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()


def _git(args: list[str], cwd: Path | None = None, limit: int = FETCH_LIMIT_SECONDS) -> bytes | None:
    """Output of one git command, or None when git is missing, fails or takes too long."""
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=limit, stdin=subprocess.DEVNULL, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def _unpack(archive: bytes, target: Path) -> bool:
    """Write the regular files of a tar archive into the folder. Links and anything that would land outside it are
    left out; a file larger than the limit stops the unpacking."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                parts = Path(member.name).parts
                if member.name.startswith("/") or ".." in parts or member.size > MAX_FILE_BYTES:
                    return False
                source = tar.extractfile(member)
                if source is None:
                    return False
                path = target.joinpath(*parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source.read())
    except (tarfile.TarError, OSError):
        return False
    return True


def archive_of(commit: str, source: Path | None, url: str) -> bytes | None:
    """The files of that commit as a tar archive: from a local checkout when one is given and holds the commit,
    otherwise fetched from the repository with this computer's own git access. None when neither works."""
    if source is not None and (source / ".git").exists():
        got = _git(["archive", "--format=tar", commit], cwd=source)
        if got:
            return got
    with tempfile.TemporaryDirectory(prefix="evidence-lab-otto-") as folder:
        work = Path(folder)
        if _git(["init", "-q", str(work)]) is None:
            return None
        if _git(["fetch", "-q", "--depth", "1", url, commit], cwd=work) is None:
            return None
        return _git(["archive", "--format=tar", "FETCH_HEAD"], cwd=work) or None


def fetch(lock: Lock, say=lambda text: None) -> bool:
    """Put the pinned commit into backend/.otto/<commit>/ and check it. Only the prepare step calls this."""
    if lock.folder.is_dir() and tree_sha256(lock.folder) == lock.tree_sha256:
        return True
    source = os.environ.get(SOURCE_ENV)
    archive = archive_of(lock.commit, Path(source) if source else None, lock.url)
    if archive is None:
        say("  could not fetch it (no access to the repository from this computer, no internet, or git is missing).")
        return False
    OTTO_HOME.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="fetching-", dir=OTTO_HOME))
    try:
        if not _unpack(archive, work) or tree_sha256(work) != lock.tree_sha256:
            say("  what was fetched is not the pinned copy (its fingerprint is different). Nothing was installed.")
            return False
        if lock.folder.exists():
            shutil.rmtree(lock.folder)
        work.rename(lock.folder)
        _forget()
        return True
    finally:
        shutil.rmtree(work, ignore_errors=True)


_cache_lock = threading.Lock()
_cached: tuple[tuple, OttoStatus] | None = None
_modules: dict[str, ModuleType] = {}


def _forget() -> None:
    global _cached
    with _cache_lock:
        _cached = None


def status(lock_path: Path = LOCK_PATH) -> OttoStatus:
    """Is the pinned Otto on this computer, unchanged? Worked out once per process and pin file."""
    global _cached
    key: tuple[str, int | None]
    try:
        key = (str(lock_path), lock_path.stat().st_mtime_ns)
    except OSError:
        key = (str(lock_path), None)
    with _cache_lock:
        if _cached is not None and _cached[0] == key:
            return _cached[1]
    try:
        lock = read_lock(lock_path)
    except OttoNotInstalled as exc:
        found = OttoStatus(False, str(exc), None, None, None, None)
    else:
        base = dict(repository=lock.repository, commit=lock.commit, version=lock.version)
        if sys.platform.startswith("win"):
            found = OttoStatus(False, "its ledger needs Linux or macOS file locking, which Windows does not have", path=None, **base)
        elif not (lock.folder / "otto" / "__init__.py").is_file():
            found = OttoStatus(False, NOT_FETCHED, path=None, **base)
        elif tree_sha256(lock.folder) != lock.tree_sha256:
            found = OttoStatus(False, NOT_PINNED_COPY, path=None, **base)
        else:
            found = OttoStatus(True, None, path=lock.folder, **base)
    with _cache_lock:
        _cached = (key, found)
    return found


def load() -> ModuleType:
    """Adam's `otto` package, loaded from the pinned folder (and from nowhere else). Raises OttoNotInstalled with
    the plain reason. The package is loaded by its path, so no other folder named otto can stand in for it."""
    found = status()
    if not found.installed or found.path is None:
        raise OttoNotInstalled(found.reason or "it is not installed")
    with _cache_lock:
        package = _modules.get("otto")
        if package is not None and Path(str(package.__file__)).parent.parent == found.path:
            return package
        folder = found.path / "otto"
        spec = importlib.util.spec_from_file_location("otto", folder / "__init__.py", submodule_search_locations=[str(folder)])
        if spec is None or spec.loader is None:
            raise OttoNotInstalled("its code could not be loaded")
        previous = {name: sys.modules.get(name) for name in list(sys.modules) if name == "otto" or name.startswith("otto.")}
        for name in previous:
            del sys.modules[name]
        package = importlib.util.module_from_spec(spec)
        sys.modules["otto"] = package
        try:
            spec.loader.exec_module(package)
            for name in _MODULES:
                importlib.import_module(f"otto.{name}")
        except Exception as exc:   # a broken or foreign copy must never take the app down
            for name in [n for n in sys.modules if n == "otto" or n.startswith("otto.")]:
                del sys.modules[name]
            raise OttoNotInstalled(f"its code could not be loaded ({exc.__class__.__name__})") from None
        _modules["otto"] = package
        return package


def module(name: str) -> ModuleType:
    """One module of the pinned package: "lab", "ledger", "loop", "canonical", "records" or "verifiers"."""
    load()
    return importlib.import_module(f"otto.{name}")


def own_checks(limit: int = 900) -> dict:
    """Adam's own two checks (AGENTS.md of his repository): his unit tests and the audit of his worked example. They
    run on a throwaway copy of the pinned files, never in the pinned folder itself, so nothing they write can change
    it. {"tests_ok", "tests_line", "audit_ok", "audit_line"}; raises OttoNotInstalled when Otto is not here."""
    found = status()
    if not found.installed or found.path is None:
        raise OttoNotInstalled(found.reason or "it is not installed")
    with tempfile.TemporaryDirectory(prefix="evidence-lab-otto-check-") as scratch:
        copy = Path(scratch) / "otto"
        shutil.copytree(found.path, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"), symlinks=False)
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # his tests need no key and get none

        def run(args: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, *args], cwd=copy, capture_output=True, text=True, timeout=limit, env=env,
                                  stdin=subprocess.DEVNULL, shell=False)
        tests = run(["-m", "unittest", "discover", "-s", "tests"])
        audit = run(["-m", "otto", "--lab", "examples/rho-negation", "audit"])
    return {"tests_ok": tests.returncode == 0, "tests_line": (tests.stderr.strip().splitlines() or ["no output"])[-1],
            "audit_ok": audit.returncode == 0, "audit_line": (audit.stdout.strip().splitlines() or ["no output"])[-1]}


def public_status() -> dict:
    """What the screens show about the harness: never a path on this computer."""
    found = status()
    return {"installed": found.installed, "sentence": found.sentence, "reason": found.reason,
            "version": found.version, "commit": found.commit, "repository": found.repository}
