"""Real nginx in the lab (phase 4b), isolated mode only. LAB ONLY.

The pinned nginx image (nginx 1.31.8 on OpenSSL 3.5.9) runs in a locked-down container: read-only, an unprivileged
user, no Linux capabilities, no new privileges, small memory and process limits, and nothing pulled at run time
(only `python -m app.prepare` pulls the image). It listens on 127.0.0.1 only. Its configuration, test certificate
and test key reach it through the container's input as a small archive: nothing is written to this computer's
disk, and the test key is never shown, stored or exported.

Used three ways: as the second copy in "Try on a test copy" (the change's exact nginx lines, checked by `nginx -t`
and measured); as the lab nginx server of demo/lab-nginx.csv, which Apply changes and reloads; and to put the
earlier settings back on Roll back. A setting nginx refuses is reported with nginx's own words, and the settings
that were in force stay in force."""
from __future__ import annotations

import hashlib
import io
import secrets
import socket
import subprocess
import tarfile
import threading
import time
from contextlib import contextmanager

from . import lab_servers, pqtls
from .config import NGINX_IMAGE
from .runner import _docker, _docker_env, docker_running, image_present

NGINX_VERSION_WORDS = "nginx 1.31.8 with OpenSSL 3.5.9"
NGINX_UID = "101:101"
FLAGS = ("-i", "--label", "evidence-lab-nginx=1", "--pull", "never", "--network", "host", "--read-only",
         "--tmpfs", "/run/lab:rw,nosuid,nodev,size=4m,uid=101,gid=101,mode=700", "--user", NGINX_UID, "--cap-drop", "ALL",
         "--security-opt", "no-new-privileges", "--memory", "64m", "--memory-swap", "64m", "--cpus", "1", "--pids-limit", "32")
START_SECONDS = 15.0
EXEC_SECONDS = 20.0
_ready_cache: dict = {}


class NginxUnavailable(Exception):
    """The lab nginx can't be used here; the message says why, in plain words."""


def ready(mode) -> tuple[bool, str]:
    """Can the lab nginx run now? (yes/no, and why not in plain words). Never pulls or builds."""
    if mode is None or getattr(mode, "name", None) != "isolated":
        return False, "Real nginx in the lab needs isolated mode (Docker)."
    now = time.monotonic()
    if _ready_cache and now - _ready_cache["at"] < 15.0:
        return _ready_cache["value"]
    if not docker_running():
        value = (False, "Real nginx in the lab needs Docker, and Docker is not running.")
    elif not image_present(NGINX_IMAGE):
        value = (False, "Real nginx in the lab needs its pinned image, which is not prepared yet (./run-demo.sh prepares it).")
    else:
        value = (True, "")
    _ready_cache.update(at=now, value=value)
    return value


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o600, 0
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _exec(name: str, script: str, data: bytes | None = None) -> tuple[int | None, str]:
    """Run one fixed shell script inside our container (argument list, no host shell)."""
    try:
        done = subprocess.run(["docker", "exec", "-i", name, "sh", "-c", script], input=data, capture_output=True,
                              timeout=EXEC_SECONDS, env=_docker_env(), shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return None, "nginx did not answer in time"
    return done.returncode, (done.stdout + done.stderr).decode("utf-8", "replace").strip()


def _last_line(text: str) -> str:
    """nginx's own reason: its "[emerg]" line when there is one (it names the setting), else its last line."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    named = [line for line in lines if "[emerg]" in line or "[crit]" in line]
    line = (named or lines or [""])[0 if named else -1]
    return line.split("] ", 1)[-1][:300] if "] " in line else line[:300]


class LabNginx:
    """One lab nginx container on 127.0.0.1:port. start() and apply() never leave a half-changed server: a setting
    nginx refuses is put back before anything else happens."""

    def __init__(self, port: int):
        self.port = port
        self.name = f"evlab-nginx-{port}"
        self.settings: dict | None = None
        self.fingerprint: str | None = None
        self.version_words = NGINX_VERSION_WORDS
        self._keep: tuple[bytes, bytes, bytes] | None = None
        self._previous: tuple[bytes, bytes, bytes] | None = None
        self._proc: subprocess.Popen | None = None
        self._output: list[str] = []
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _drain(self, proc: subprocess.Popen) -> None:
        for line in iter(proc.stdout.readline, b""):
            if len(self._output) < 200:
                self._output.append(line.decode("utf-8", "replace").rstrip())

    def start(self, settings: dict) -> None:
        """Start the container with these settings and a fresh test certificate. Raises NginxUnavailable."""
        with self._lock:
            s = lab_servers.normal(settings)
            keep = pqtls.test_certificate(s["certificate"], "lab-nginx")
            _docker(["rm", "-f", self.name], 10)      # a container of this name left by an earlier crash
            files = {"nginx.conf": lab_servers.nginx_config(s, self.port).encode(), "cert.pem": keep[0], "key.pem": keep[1]}
            script = ("tar -x -C /run/lab && nginx -t -q -c /run/lab/nginx.conf 2>&1 && "
                      "exec nginx -c /run/lab/nginx.conf -g 'daemon off;'")
            self._output = []
            try:
                proc = subprocess.Popen(["docker", "run", "--rm", "--name", self.name, *FLAGS, "--entrypoint", "sh", NGINX_IMAGE, "-c", script],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=_docker_env())
            except OSError as exc:
                raise NginxUnavailable(f"The lab nginx could not be started ({exc.__class__.__name__}).") from None
            proc.stdin.write(_archive(files))
            proc.stdin.close()
            threading.Thread(target=self._drain, args=(proc,), daemon=True).start()
            deadline = time.monotonic() + START_SECONDS
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    time.sleep(0.2)
                    raise NginxUnavailable(f"nginx did not start with these settings: {_last_line(chr(10).join(self._output)) or 'no reason given'}.")
                try:
                    socket.create_connection(("127.0.0.1", self.port), timeout=0.3).close()
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                proc.kill()
                raise NginxUnavailable("nginx did not start in time.")
            self._proc, self.settings, self._keep = proc, s, keep
            self.fingerprint = hashlib.sha256(keep[2]).hexdigest()

    def apply(self, settings: dict, keep: tuple[bytes, bytes, bytes] | None = None) -> tuple[bool, str]:
        """Give the running nginx new settings: check them with `nginx -t`, then reload. (accepted?, nginx's words).
        When nginx refuses them, the earlier files are put back and nginx keeps running as it was."""
        with self._lock:
            if not self.running:
                return False, "The lab nginx is not running."
            s = lab_servers.normal(settings)
            if keep is None:
                keep = self._keep if self._keep and lab_servers.keep_kind(self._keep) == s["certificate"] else pqtls.test_certificate(s["certificate"], "lab-nginx")
            files = {"nginx.conf": lab_servers.nginx_config(s, self.port).encode(), "cert.pem": keep[0], "key.pem": keep[1]}
            script = ("mkdir -p /run/lab/new /run/lab/before && rm -f /run/lab/new/* && tar -x -C /run/lab/new && "
                      "cp /run/lab/nginx.conf /run/lab/cert.pem /run/lab/key.pem /run/lab/before/ && cp /run/lab/new/* /run/lab/ && "
                      "if nginx -t -q -c /run/lab/nginx.conf 2>&1; then nginx -c /run/lab/nginx.conf -s reload 2>&1 && echo RELOADED; "
                      "else cp /run/lab/before/* /run/lab/ && echo REFUSED; fi")
            code, out = _exec(self.name, script, _archive(files))
            if code != 0 or "RELOADED" not in out:
                return False, _last_line(out.replace("REFUSED", "")) or "nginx refused the settings"
            time.sleep(0.8)   # the new worker takes over
            self._previous, self._keep, self.settings = self._keep, keep, s
            self.fingerprint = hashlib.sha256(keep[2]).hexdigest()
            return True, "nginx -t: the configuration test is successful; nginx reloaded"

    def previous_certificate(self) -> tuple[bytes, bytes, bytes] | None:
        return self._previous

    def stop(self) -> None:
        with self._lock:
            if self._proc is not None:
                _docker(["rm", "-f", self.name], 15)
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None


@contextmanager
def nginx_copy(settings: dict):
    """A throwaway lab nginx with these settings on a spare port, removed on exit. Yields {"port", "fingerprint",
    "settings", "accepted"}. Raises NginxUnavailable (with nginx's own words when it refused the settings)."""
    server = LabNginx(lab_servers.free_port())
    server.name = f"evlab-nginx-copy-{secrets.token_hex(4)}"
    try:
        server.start(settings)
        yield {"port": server.port, "fingerprint": server.fingerprint, "settings": server.settings,
               "accepted": "nginx -t passed and nginx started"}
    finally:
        server.stop()


__all__ = ["LabNginx", "nginx_copy", "ready", "NginxUnavailable", "NGINX_VERSION_WORDS"]
