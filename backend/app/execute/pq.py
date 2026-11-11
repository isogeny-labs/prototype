"""Post-quantum readiness: does a server offer the hybrid key exchange X25519MLKEM768?

The question is asked with OpenSSL's own client (openssl s_client) from OpenSSL 3.5 or newer, because
older versions cannot offer this key exchange. Which checker is used, in order:
  1. the openssl program on this computer, if it is 3.5 or newer;
  2. otherwise, if Docker is running and our pinned OpenSSL image is already here, s_client in a container
     (our own fixed image, read-only, no capabilities, not root, with a time limit; host networking so it
     can reach this computer's own address; handshake only);
  3. otherwise the test cannot run, and says so. No hand-built probe and no guess.
Every command is an argument list. The only address ever used is the IP the address gate pinned."""
from __future__ import annotations

import os
import re
import secrets
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager

from ..components import redact
from ..config import OPENSSL_IMAGE
from ..runner import ModeInfo, _docker_env
from ..tlsprobe import openssl_cli
from . import RunContext, problem
from .server import gate, _ready

GROUP = "X25519MLKEM768"
OFFERED_LINE = "Negotiated TLS1.3 group: X25519MLKEM768"
CLIENT_SECONDS = 20.0
SERVER_START_SECONDS = 15.0
MAX_OUTPUT = 4000
DOCKER_FLAGS: tuple[str, ...] = (
    "--rm", "-i", "--label", "evidence-lab=1", "--pull", "never", "--network", "host", "--read-only",
    "--tmpfs", "/tmp:rw,nosuid,nodev,size=8m,uid=65534,gid=65534,mode=700", "--user", "65534:65534", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges", "--memory", "128m", "--memory-swap", "128m", "--cpus", "1",
    "--pids-limit", "32", "--log-driver", "none",
)


def client_args(ip: str, port: int, server_name: str | None, pq_only: bool) -> list[str]:
    target = f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
    args = ["s_client", "-connect", target]
    args += ["-servername", server_name] if server_name else ["-noservername"]
    if pq_only:
        args += ["-groups", GROUP, "-tls1_3"]
    return args + ["-brief"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, alive) -> bool:
    deadline = time.monotonic() + SERVER_START_SECONDS
    while time.monotonic() < deadline:
        if not alive():
            return False
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.15)
    return False


def parse_version(text: str) -> tuple[int, int] | None:
    m = re.match(r"OpenSSL (\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _run(argv: list[str], env: dict | None = None) -> tuple[int | None, str]:
    """(exit code or None on timeout, combined output). stdin is closed, so s_client ends after the handshake."""
    try:
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                              timeout=CLIENT_SECONDS, env=env, shell=False)
    except subprocess.TimeoutExpired:
        return None, "(no answer before the time limit)"
    except OSError as exc:
        return None, f"(the checker could not be started: {exc.__class__.__name__})"
    return done.returncode, redact(done.stdout + done.stderr)[:MAX_OUTPUT]


class LocalChecker:
    kind = "local"

    def __init__(self, path: str, version: str):
        self.path, self.version = path, version

    def s_client(self, ip: str, port: int, server_name: str | None, pq_only: bool) -> dict:
        args = client_args(ip, port, server_name, pq_only)
        code, output = _run([self.path, *args], {"PATH": os.defpath})
        return {"command": "openssl " + " ".join(args), "exit": code, "output": output}

    @contextmanager
    def control_server(self):
        """A test server that DOES offer the key exchange, with a test key that is deleted when it stops."""
        port = _free_port()
        with tempfile.TemporaryDirectory(prefix="evidence-lab-pq-") as folder:
            os.chmod(folder, 0o700)
            key, cert = os.path.join(folder, "k.pem"), os.path.join(folder, "c.pem")
            made = subprocess.run([self.path, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                                   "-keyout", key, "-out", cert, "-subj", "/CN=localhost", "-days", "1"],
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=20, env={"PATH": os.defpath})
            if made.returncode != 0:
                raise RuntimeError("the control certificate could not be made")
            proc = subprocess.Popen([self.path, "s_server", "-accept", f"127.0.0.1:{port}", "-groups", GROUP, "-tls1_3",
                                     "-key", key, "-cert", cert, "-brief"], stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={"PATH": os.defpath})
            try:
                if not _wait_for_port(port, lambda: proc.poll() is None):
                    raise RuntimeError("the control server did not start")
                yield port
            finally:
                proc.kill()
                proc.wait(timeout=5)


class DockerChecker:
    kind = "docker"

    def __init__(self, image: str, version: str):
        self.image, self.version = image, version

    def _argv(self, name: str, tail: list[str], entrypoint: str | None = None) -> list[str]:
        head = ["docker", "run", "--name", name, *DOCKER_FLAGS]
        if entrypoint:
            head += ["--entrypoint", entrypoint]
        return head + [self.image, *tail]

    @staticmethod
    def _remove(name: str) -> None:
        try:
            subprocess.run(["docker", "rm", "-f", name], stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
                           env=_docker_env())
        except (OSError, subprocess.SubprocessError):
            pass

    def s_client(self, ip: str, port: int, server_name: str | None, pq_only: bool) -> dict:
        args = client_args(ip, port, server_name, pq_only)
        name = "evlab-pq-" + secrets.token_hex(6)
        code, output = _run(self._argv(name, args), _docker_env())
        if code is None:
            self._remove(name)
        return {"command": f"docker run {' '.join(DOCKER_FLAGS)} {self.image} " + " ".join(args), "exit": code, "output": output}

    @contextmanager
    def control_server(self):
        port = _free_port()  # a number we picked; the only thing that varies in the fixed script below
        script = ("openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -keyout /tmp/k.pem -out /tmp/c.pem "
                  "-subj /CN=localhost -days 1 >/dev/null 2>&1 && exec openssl s_server "
                  f"-accept 127.0.0.1:{int(port)} -groups {GROUP} -tls1_3 -key /tmp/k.pem -cert /tmp/c.pem -brief")
        name = "evlab-pq-" + secrets.token_hex(6)
        proc = subprocess.Popen(self._argv(name, ["-c", script], entrypoint="sh"), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_docker_env())
        try:
            if not _wait_for_port(port, lambda: proc.poll() is None):
                raise RuntimeError("the control server did not start")
            yield port
        finally:
            self._remove(name)
            proc.kill()
            proc.wait(timeout=5)


def find_checker(mode: ModeInfo):
    """The checker to use, or (None, why not)."""
    path, version = openssl_cli()
    parsed = parse_version(version)
    if path and parsed and parsed >= (3, 5):
        return LocalChecker(path, version), None
    local = f"The openssl program on this computer is {version}." if path else "There is no openssl program on this computer."
    if not mode.docker_running:
        return None, f"{local} Docker is not running, so the OpenSSL 3.5 checker image can't be used either."
    if not mode.openssl_image:
        return None, f"{local} Docker is running, but the OpenSSL checker image is not prepared (./run-demo.sh prepares it)."
    code, output = _run(["docker", "run", "--name", "evlab-pq-" + secrets.token_hex(6), *DOCKER_FLAGS, OPENSSL_IMAGE, "version"],
                        _docker_env())
    parsed = parse_version(output.strip()) if code == 0 else None
    if not parsed or parsed < (3, 5):
        return None, f"{local} The OpenSSL checker image could not be used."
    return DockerChecker(OPENSSL_IMAGE, output.strip().splitlines()[0]), None


def _read(result: dict) -> dict:
    """Convenience fields next to the literal output. The reviewer reads the output itself."""
    output = result.get("output") or ""
    alert = re.search(r"SSL alert number (\d+)", output)
    lines = [line.strip() for line in output.splitlines()]
    return {**result, "negotiated_line": OFFERED_LINE in lines, "established": "CONNECTION ESTABLISHED" in lines,
            "alert": int(alert.group(1)) if alert else None}


def run_pq_readiness(spec: dict, ctx: RunContext) -> dict:
    address = spec["target"]["address"]
    check, blocked = gate(ctx, address)          # nothing is contacted unless the address passes the gate
    if blocked:
        return blocked
    checker, why_not = find_checker(ctx.mode)
    if checker is None:
        return problem("checker_too_old", why_not)
    not_ready = _ready(check)
    if not_ready:
        return not_ready
    ip, port, name = check.session.ip, check.session.port, check.session.server_name
    ctx.progress(f"asking the server for {GROUP}", 20)
    raw: dict = {"checker": {"kind": checker.kind, "version": checker.version},
                 "subject": {"address": address, "ip": ip,
                             "pq_only": _read(checker.s_client(ip, port, name, True)),
                             "normal": _read(checker.s_client(ip, port, name, False))}}
    ctx.progress("checking the control server", 60)
    try:
        with checker.control_server() as control_port:
            raw["control"] = {"port": control_port, "pq_only": _read(checker.s_client("127.0.0.1", control_port, None, True))}
    except Exception as exc:
        ctx.log(f"control server failed ({exc.__class__.__name__})")
        raw["control"] = {"error": f"the control server could not be run ({exc.__class__.__name__})"}
    ctx.progress("checking the result", 97)
    return raw
