"""Where a measured library comes from: one small interface, so the capability check and the reviewer never care.

Built in this phase: the public pinned copy in our sandbox (`PublicCopy`). Level 3 (a later phase) adds a target
that is the customer's own container in their network; it implements the same three calls and nothing else changes.
The label a result carries comes from the target kind, in this one place (`LABELS`)."""
from __future__ import annotations

import subprocess
import secrets
from typing import Protocol

from app import real_libraries
from app.run.execute.pq import DOCKER_FLAGS, _docker_env, client_args

TARGET_KINDS = ("public_copy", "your_environment")
# How a measured answer was proven. "your_environment" is defined, and nothing in this phase can produce it.
LABELS = {"public_copy": "public_copy", "your_environment": "your_environment"}
TIME_LIMIT_SECONDS = 60


class Target(Protocol):
    kind: str

    def describe(self) -> dict: ...
    def run_job(self, job: dict, time_limit: float): ...           # a harness job on this library (keygen, round trips)
    def tls_client(self, port: int, groups: str) -> dict | None: ... # one TLS 1.3 handshake to 127.0.0.1:port; None: not measured here


def label_of(target_kind: object) -> str | None:
    return LABELS.get(target_kind) if isinstance(target_kind, str) else None


class PublicCopy:
    """The pinned public copy of exactly this library version (real_libraries.CAPABILITY_COPIES), in its own image."""
    kind = "public_copy"

    def __init__(self, name: str, version: str, runner):
        copy = real_libraries.capability_copy(name, version)
        if copy is None:
            raise ValueError("not a library version with a pinned copy")
        self.name, self.version, self.copy, self.runner = name, version, copy, runner

    @property
    def subject(self) -> str:
        return f"{self.name}-{self.version}"

    @property
    def family(self) -> str:
        return self.copy["family"]

    def describe(self) -> dict:
        image = (self.runner.mode.real_images or {}).get(self.family) if self.runner else None
        return {"kind": self.kind, "name": self.name, "version": self.version, "label": self.copy["label"], "image": image,
                "tls_client": self.tls_image()}

    def run_job(self, job: dict, time_limit: float = TIME_LIMIT_SECONDS):
        return self.runner.run_job({**job, "subject": self.subject}, time_limit=time_limit, family=self.family)

    def tls_image(self) -> str | None:
        where = self.copy.get("tls_client")
        if where == "family":
            return (self.runner.mode.real_images or {}).get(self.family) if self.runner else None
        return where

    def tls_client(self, port: int, groups: str) -> dict | None:
        """The copy's own `openssl s_client`, offering only `groups`, to the app's own test server on 127.0.0.1."""
        image = self.tls_image()
        if image is None:
            return None
        args = [*client_args("127.0.0.1", int(port), None, False), "-groups", groups, "-tls1_3"]
        name = "evlab-cap-" + secrets.token_hex(6)
        argv = ["docker", "run", "--name", name, *DOCKER_FLAGS, "--entrypoint", "openssl", image, *args]
        try:
            done = subprocess.run(argv, input="", capture_output=True, text=True, timeout=TIME_LIMIT_SECONDS, env=_docker_env())
            code, output = done.returncode, (done.stdout + done.stderr)[-4000:]
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20, env=_docker_env())
            code, output = None, "(no answer before the time limit)"
        except OSError as exc:
            code, output = None, f"(the client could not be started: {exc.__class__.__name__})"
        return {"command": f"docker run ... --entrypoint openssl {image} " + " ".join(args), "exit": code, "output": output}
