"""Prepare isolated mode:  cd backend && .venv/bin/python -m app.prepare [--check]

This is the ONLY code that may download or build a container image. ./run-demo.sh calls it once
before the app starts; the app itself never builds or downloads anything.

- Docker not running: says so and stops. The app then runs in demo mode.
- A pinned base image is missing: tries to download exactly that pinned image (time limit; needs internet). Since
  phase 4b that includes the pinned nginx lab image (Try on real nginx, and the lab nginx of demo/lab-nginx.csv).
- Our components image is missing: builds it from demo/components/ on the pinned Python base, with no network.
- Real libraries (phase 4c): for each family (Java, python-ecdsa, elliptic, OpenSSL) it downloads the pinned
  images and files the library itself comes from, checks every file's fingerprint, and builds that family's
  image with no network. A family that can't be prepared is named; the others still work.

It always exits with code 0, so it can never stop the app from starting. `--check` only reports.
"""
from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from . import real_libraries
from .config import COMPONENTS_DIR, NGINX_IMAGE, OPENSSL_IMAGE, PYTHON_BASE_IMAGE, REPO_ROOT
from .runner import _docker_env, components_image_tag, docker_running, image_present, real_image_tag

PULL_LIMIT_SECONDS = 120
REAL_PULL_LIMIT_SECONDS = 900     # the two Java images are a few hundred MB each
BUILD_LIMIT_SECONDS = 180
REAL_BUILD_LIMIT_SECONDS = 600
DOWNLOAD_LIMIT_SECONDS = 60
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
DOWNLOADS_DIR = REPO_ROOT / "data" / "downloads"   # checked copies of the pinned library files, kept between runs


def _run(args: list[str], limit: int) -> bool:
    try:
        done = subprocess.run(["docker", *args], capture_output=True, text=True, errors="replace", timeout=limit,
                              stdin=subprocess.DEVNULL, shell=False, env=_docker_env())
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def pull(reference: str, limit: int = PULL_LIMIT_SECONDS) -> bool:
    return _run(["pull", "--quiet", reference], limit)


def build(tag: str) -> bool:
    return _run(["build", "--pull=false", "--network", "none", "-t", tag, "-f", str(COMPONENTS_DIR / "Dockerfile"),
                 str(COMPONENTS_DIR)], BUILD_LIMIT_SECONDS)


# ---------------------------------------------------------------- real libraries (phase 4c)

def _matches(data: bytes, pin: dict) -> bool:
    """Is this exactly the pinned file? By SHA-256, or by npm's integrity value (SHA-512, base64)."""
    if "sha256" in pin:
        return hashlib.sha256(data).hexdigest() == pin["sha256"]
    return base64.b64encode(hashlib.sha512(data).digest()).decode("ascii") == pin["sha512_base64"]


def fetch(pin: dict, folder: Path = DOWNLOADS_DIR) -> Path | None:
    """The pinned file, from the kept copy or downloaded once. None unless its fingerprint is exactly the pinned one."""
    path = folder / pin["file"]
    try:
        if path.is_file() and _matches(path.read_bytes(), pin):
            return path
    except OSError:
        pass
    try:
        with urllib.request.urlopen(pin["url"], timeout=DOWNLOAD_LIMIT_SECONDS) as answer:   # a fixed https address from the pins
            data = answer.read(MAX_DOWNLOAD_BYTES + 1)
    except (OSError, ValueError):
        return None
    if len(data) > MAX_DOWNLOAD_BYTES or not _matches(data, pin):
        return None
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def build_real(family: str, tag: str, files: list[Path]) -> bool:
    """Build one family's image from a folder put together for it: our harness and controls (components/), the
    family's wrapper folder (real/) and the checked library files (pkgs/). No network during the build."""
    pins = real_libraries.FAMILIES[family]
    with tempfile.TemporaryDirectory(prefix="evidence-lab-build-") as folder:
        context = Path(folder)
        _copy_tree(COMPONENTS_DIR, context / "components")
        _copy_tree(real_libraries.REAL_DIR / family, context / "real")
        (context / "pkgs").mkdir()
        for path in files:
            shutil.copy(path, context / "pkgs" / path.name)
        args = ["build", "--pull=false", "--network", "none", "-t", tag, "-f", str(context / "real" / "Dockerfile"),
                "--build-arg", f"PYTHON_BASE={PYTHON_BASE_IMAGE}"]
        for name, reference in pins["images"].items():
            args += ["--build-arg", f"{name}={reference}"]
        return _run([*args, str(context)], REAL_BUILD_LIMIT_SECONDS)


def prepare_real(family: str, check_only: bool, say, base_ready: bool) -> bool:
    pins = real_libraries.FAMILIES[family]
    tag = real_image_tag(family)
    if image_present(tag):
        return True
    if check_only or not base_ready or not (real_libraries.REAL_DIR / family / "Dockerfile").is_file():
        return False
    for reference in pins["images"].values():
        if not image_present(reference):
            say(f"Downloading what the {pins['label']} image is built from (once, needs internet) ...")
            if not (pull(reference, REAL_PULL_LIMIT_SECONDS) and image_present(reference)):
                say(f"  could not download {reference}.")
                return False
    files = []
    for pin in pins["downloads"]:
        path = fetch(pin)
        if path is None:
            say(f"  could not get {pin['file']} with the pinned fingerprint (no internet, or the file is not the pinned one).")
            return False
        files.append(path)
    say(f"Building the {pins['label']} image (once, no network needed) ...")
    try:
        built = build_real(family, tag, files) and image_present(tag)
    except OSError:
        built = False
    if not built:
        say("  could not build it.")
    return built


def main(argv: list[str] | None = None, say=print) -> int:
    check_only = "--check" in (sys.argv[1:] if argv is None else argv)
    if not docker_running():
        say("Isolated mode: not available (Docker is not running). The app will run in demo mode.")
        return 0
    bases = (("Python base image", PYTHON_BASE_IMAGE), ("OpenSSL checker image", OPENSSL_IMAGE), ("nginx lab image", NGINX_IMAGE))
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
    real = {family: prepare_real(family, check_only, say, bool(built)) for family in real_libraries.FAMILIES}
    for label, reference in bases:
        say(f"{label}: {'ready' if present[reference] else 'missing'}  ({reference})")
    say(f"Demo components image: {'ready' if built else 'missing'}  ({tag})")
    for family, ready in real.items():
        say(f"Real library, {real_libraries.FAMILIES[family]['label']}: {'ready' if ready else 'missing'}  ({real_image_tag(family)})")
    if built:
        say("Isolated mode: ready. Demo software will run in a locked-down container with no network.")
    else:
        say("Isolated mode: not ready. The app will run in demo mode.")
    missing = [real_libraries.FAMILIES[f]["label"] for f, ready in real.items() if not ready]
    if built and missing:
        say(f"Real libraries: {', '.join(missing)} can't run until {'its image is' if len(missing) == 1 else 'their images are'} "
            "prepared (needs internet once). The app says so wherever one is named.")
    if not present[OPENSSL_IMAGE]:
        say("Post-quantum check: the OpenSSL checker image is missing, so it needs OpenSSL 3.5 or newer on this computer.")
    if not present[NGINX_IMAGE]:
        say("Real nginx in the lab: the nginx lab image is missing, so a try runs on the test copy only and the lab nginx can't start.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
