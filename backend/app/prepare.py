"""Prepare isolated mode:  cd backend && .venv/bin/python -m app.prepare [--check]

This is the ONLY code that may download or build a container image. ./run-demo.sh calls it once
before the app starts; the app itself never builds or downloads anything.

- Docker not running: says so and stops. The app then runs in demo mode.
- A pinned base image is missing: tries to download exactly that pinned image (time limit; needs internet).
- Our components image is missing: builds it from demo/components/ on the pinned Python base, with no network.

It always exits with code 0, so it can never stop the app from starting. `--check` only reports.
"""
from __future__ import annotations

import subprocess
import sys

from .config import COMPONENTS_DIR, OPENSSL_IMAGE, PYTHON_BASE_IMAGE
from .runner import _docker_env, components_image_tag, docker_running, image_present

PULL_LIMIT_SECONDS = 120
BUILD_LIMIT_SECONDS = 180


def _run(args: list[str], limit: int) -> bool:
    try:
        done = subprocess.run(["docker", *args], capture_output=True, text=True, errors="replace", timeout=limit,
                              stdin=subprocess.DEVNULL, shell=False, env=_docker_env())
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def pull(reference: str) -> bool:
    return _run(["pull", "--quiet", reference], PULL_LIMIT_SECONDS)


def build(tag: str) -> bool:
    return _run(["build", "--pull=false", "--network", "none", "-t", tag, "-f", str(COMPONENTS_DIR / "Dockerfile"),
                 str(COMPONENTS_DIR)], BUILD_LIMIT_SECONDS)


def main(argv: list[str] | None = None, say=print) -> int:
    check_only = "--check" in (sys.argv[1:] if argv is None else argv)
    if not docker_running():
        say("Isolated mode: not available (Docker is not running). The app will run in demo mode.")
        return 0
    bases = (("Python base image", PYTHON_BASE_IMAGE), ("OpenSSL checker image", OPENSSL_IMAGE))
    present = {}
    for label, reference in bases:
        present[reference] = image_present(reference)
        if not present[reference] and not check_only:
            say(f"Downloading the {label} (once, needs internet) ...")
            present[reference] = pull(reference) and image_present(reference)
            if not present[reference]:
                say(f"  could not download it (no internet, or it took longer than {PULL_LIMIT_SECONDS} seconds).")
    tag = components_image_tag()
    built = image_present(tag)
    if not built and present[PYTHON_BASE_IMAGE] and not check_only:
        say("Building the demo components image (once, no network needed) ...")
        built = build(tag) and image_present(tag)
        if not built:
            say("  could not build it.")
    for label, reference in bases:
        say(f"{label}: {'ready' if present[reference] else 'missing'}  ({reference})")
    say(f"Demo components image: {'ready' if built else 'missing'}  ({tag})")
    if built:
        say("Isolated mode: ready. Demo software will run in a locked-down container with no network.")
    else:
        say("Isolated mode: not ready. The app will run in demo mode.")
    if not present[OPENSSL_IMAGE]:
        say("Post-quantum check: the OpenSSL checker image is missing, so it needs OpenSSL 3.5 or newer on this computer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
