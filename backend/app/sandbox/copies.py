"""Sandbox research: the store of public copies made on this computer, and what the app may know of them.

A **copy set** is one library in a few exact published versions, with one piece of asking code, built into one
locked-down container image. Its record (`set.json`) says where every file came from, each file's fingerprint, the
fingerprint the registry itself gave, the helper libraries, the asking code and the image. The record is data: it is
held to the exact shape written here, and nothing in it runs.

The store is a folder in the data folder (`<data>/sandbox/`):
    files/<sha256>-<file name>      every file fetched, kept under its own fingerprint
    index.jsonl                     trust on first use: the fingerprint of each file the first time it was fetched
    sets/<set id>/set.json          one copy set

What the rest of the app sees: with Sandbox research on, a library version that a copy set of this computer holds counts
as a real library that can run (in isolated mode only, in its own image), labelled "Sandbox copy". The pinned libraries
of `real_libraries.py` are untouched and always come first. With the switch off, nothing here is seen by anything.

The app's web process only reads this store. Making a copy (fetching, unpacking, building an image) is `maker.py`,
which only the research command and the prepare command use.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from app.canonical import canonical_bytes

SCHEMA = "isogeny.sandbox-copy-set/1"
IMAGE_REPOSITORY = "evidence-lab-sandbox"
FAMILY_PREFIX = "sandbox-"
LABEL_TAIL = "sandbox copy"
ALGORITHM = "ECDSA P-256"                 # what every piece of asking code answers about, in this version
ROLES = ("affected", "fixed", "yours", "more_affected", "more_fixed")
ASKING_KINDS = ("ours", "written")        # our own asking code for one of the four families, or code written for this library
MAX_VERSIONS, MAX_FILES, MAX_SOURCE_CHARS = 8, 40, 20000
_ID = re.compile(r"^[0-9a-f]{16}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^(@[a-z0-9][a-z0-9._-]{0,60}/)?[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,60}$")
_TAG = re.compile(r"^evidence-lab-sandbox-[a-z0-9][a-z0-9._-]{0,80}:[0-9a-f]{16}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class CopyError(Exception):
    """A copy could not be made, or a record is not what this version writes. One plain sentence. `later` is true when
    nothing was learned about the package itself (Docker did not answer, a download came back damaged, a file is not
    the one seen before): a stop, never a result, and a later try can go differently."""

    def __init__(self, text: str, later: bool = False) -> None:
        super().__init__(text)
        self.later = later


def slug(library: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", library.lower()).strip("-.") or "library"


def content_of(record: dict) -> dict:
    """What a set's id is the fingerprint of: everything that decides what is in its image. (Not when it was made.)"""
    return {"library": record["library"], "registry": record["registry"], "package": record["package"], "language": record["language"],
            "versions": [{"version": v["version"], "files": [{"file": f["file"], "sha256": f["sha256"]} for f in v["files"]],
                          "tree_sha256": v["tree_sha256"]} for v in record["versions"]],
            "asking": {"kind": record["asking"]["kind"], "sha256": record["asking"]["sha256"], "template_sha256": record["asking"]["template_sha256"]},
            "harness_sha256": record["harness_sha256"], "base_images": dict(record["base_images"])}


def set_id(record: dict) -> str:
    return hashlib.sha256(canonical_bytes(content_of(record))).hexdigest()[:16]


def image_tag(library: str, the_id: str) -> str:
    return f"{IMAGE_REPOSITORY}-{slug(library)}:{the_id}"


def family_of(record: dict) -> str:
    return FAMILY_PREFIX + record["id"]


def check_set(record: object) -> dict:
    """A copy set's record, held to the exact shape this version writes. Raises CopyError."""
    def need(ok: bool, what: str) -> None:
        if not ok:
            raise CopyError(f"A copy set's record is not written as this version writes it ({what}).")

    need(isinstance(record, dict), "it is not a record")
    assert isinstance(record, dict)
    need(set(record) == {"schema", "id", "library", "registry", "package", "language", "versions", "asking", "harness_sha256", "base_images",
                         "image", "made_at", "checked"}, "its parts")
    need(record["schema"] == SCHEMA, "its schema")
    need(isinstance(record["library"], str) and bool(_NAME.match(record["library"])) and isinstance(record["package"], str)
         and bool(_NAME.match(record["package"])), "its names")
    need(record["registry"] in ("pypi", "npm") and record["language"] in ("python", "node"), "its registry")
    versions = record["versions"]
    need(isinstance(versions, list) and 1 <= len(versions) <= MAX_VERSIONS, "its versions")
    seen = set()
    for v in versions:
        need(isinstance(v, dict) and set(v) == {"version", "role", "published", "files", "tree_sha256", "helpers", "says"}, "a version's parts")
        need(isinstance(v["version"], str) and bool(_VERSION.match(v["version"])) and v["version"] not in seen, "a version")
        seen.add(v["version"])
        need(v["role"] in ROLES and (v["published"] is None or isinstance(v["published"], str)), "a version's role")
        need(isinstance(v["tree_sha256"], str) and bool(_HEX64.match(v["tree_sha256"])), "a version's fingerprint")
        need(isinstance(v["files"], list) and 1 <= len(v["files"]) <= MAX_FILES, "a version's files")
        for f in v["files"]:
            need(isinstance(f, dict) and set(f) == {"file", "package", "version", "url", "sha256", "registry_fingerprint", "size", "fetched_at",
                                                    "source"}, "a file's parts")
            need(isinstance(f["sha256"], str) and bool(_HEX64.match(f["sha256"])) and isinstance(f["url"], str) and len(f["url"]) <= 500
                 and isinstance(f["file"], str) and len(f["file"]) <= 160 and f["source"] in ("live", "recorded"), "a file")
        need(isinstance(v["helpers"], list) and all(isinstance(h, str) and len(h) <= 120 for h in v["helpers"]), "a version's helper libraries")
        need(isinstance(v["says"], dict) and set(v["says"]) == {"name", "version"}, "what a version says of itself")
    asking = record["asking"]
    need(isinstance(asking, dict) and set(asking) == {"kind", "author", "language", "file", "source", "sha256", "lines", "template_sha256",
                                                      "commands"}, "its asking code")
    need(asking["kind"] in ASKING_KINDS and asking["language"] == record["language"] and isinstance(asking["source"], str)
         and len(asking["source"]) <= MAX_SOURCE_CHARS, "its asking code's text")
    need(hashlib.sha256(asking["source"].encode("utf-8")).hexdigest() == asking["sha256"], "its asking code's fingerprint")
    need(isinstance(asking["commands"], list) and "verify" in asking["commands"], "what its asking code answers")
    need(isinstance(record["harness_sha256"], str) and bool(_HEX64.match(record["harness_sha256"])) and isinstance(record["base_images"], dict)
         and all(isinstance(k, str) and isinstance(v, str) for k, v in record["base_images"].items()), "what its image is built from")
    image = record["image"]
    need(isinstance(image, dict) and set(image) == {"tag", "id"} and isinstance(image["tag"], str) and bool(_TAG.match(image["tag"]))
         and isinstance(image["id"], str) and bool(_IMAGE_ID.match(image["id"])), "its image")
    need(isinstance(record["id"], str) and bool(_ID.match(record["id"])) and record["id"] == set_id(record), "its id is not the fingerprint of its content")
    need(image["tag"] == image_tag(record["library"], record["id"]), "its image's name")
    need(isinstance(record["made_at"], str) and isinstance(record["checked"], dict), "when it was made")
    return record


def read_set(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise CopyError("A copy set's record is not valid JSON.") from None
    return check_set(data)


def versions_of(record: dict) -> list[str]:
    """The set's versions, oldest first."""
    from app.sandbox.versions import order
    return [v["version"] for v in sorted(record["versions"], key=lambda v: order(v["version"]) or ())]


def as_library(record: dict) -> dict:
    """The set in the shape `real_libraries.library()` gives for a pinned library, so every part of the app that can
    run a real library can run this one the same way: in isolated mode only, in its own image."""
    versions = versions_of(record)
    fixed = next((v["version"] for v in record["versions"] if v["role"] == "fixed"), None)
    full = "sign" in record["asking"]["commands"]
    return {"family": family_of(record), "label": f"{record['library']} ({LABEL_TAIL})", "versions": versions,
            "algorithms": (ALGORITHM,), "fixed_in": {v["version"]: fixed for v in record["versions"] if fixed and v["role"] != "fixed"
                                                     and v["role"] != "more_fixed"},
            "advisories": {}, "distribution": {}, "sandbox": record["id"], "checks_only": not full}


# ---------------------------------------------------------------- the store, read

def sets_in(root: Path) -> list[dict]:
    """Every readable copy set of a store, newest first. A record that does not read is left out, never half-used."""
    folder = Path(root) / "sets"
    out = []
    try:
        entries = sorted(p for p in folder.iterdir() if p.is_dir() and _ID.match(p.name))
    except OSError:
        return []
    for entry in entries:
        path = entry / "set.json"
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            record = read_set(path.read_bytes())
        except (OSError, CopyError):
            continue
        if record["id"] == entry.name:
            out.append(record)
    out.sort(key=lambda r: (r["made_at"], r["id"]), reverse=True)
    return out


def write_set(root: Path, record: dict) -> Path:
    check_set(record)
    folder = Path(root) / "sets" / record["id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "set.json"
    path.write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------- what this process may see (only with the switch on)

_lock = threading.Lock()
_stores: dict[str, tuple[Path, Callable[[], bool]]] = {}       # a store's folder -> (the folder, is Sandbox research on there?)
_cache: dict[str, tuple[float, list[dict]]] = {}
CACHE_SECONDS = 2.0


def register(root: Path, enabled: Callable[[], bool]) -> None:
    """A running app (or a trial's scratch copy of it) says where its store is, and how to ask whether its switch is on."""
    with _lock:
        _stores[str(Path(root).resolve())] = (Path(root).resolve(), enabled)
        _cache.pop(str(Path(root).resolve()), None)


def unregister(root: Path) -> None:
    with _lock:
        _stores.pop(str(Path(root).resolve()), None)
        _cache.pop(str(Path(root).resolve()), None)


def forget_cache() -> None:
    with _lock:
        _cache.clear()


def _visible() -> list[dict]:
    with _lock:
        stores = list(_stores.values())
    out: list[dict] = []
    now = time.monotonic()
    for root, enabled in stores:
        try:
            if not enabled():
                continue
        except Exception:      # noqa: BLE001  (a store whose app can't say is not seen)
            continue
        key = str(root)
        with _lock:
            cached = _cache.get(key)
        if cached is None or now - cached[0] > CACHE_SECONDS:
            cached = (now, sets_in(root))
            with _lock:
                _cache[key] = cached
        out += cached[1]
    out.sort(key=lambda r: (r["made_at"], r["id"]), reverse=True)
    return out


def find(name: object, version: object) -> dict | None:
    """The copy set on this computer that a run on this version of this library uses: the OLDEST one that holds exactly
    this version; None with the switch off. The oldest, so that what an accepted check runs in never changes when a
    later research run makes another copy set of the same library: the copy a check was first run in stands. (The
    research command writes one piece of asking code for a library, and uses it again for a later advisory, so every
    copy set of a library holds the same asking code: ottolab/sandbox.py.)"""
    if not isinstance(name, str) or not isinstance(version, str) or not _stores:
        return None
    return next((r for r in reversed(_visible()) if r["library"] == name and any(v["version"] == version for v in r["versions"])), None)


def library(name: object, version: object) -> dict | None:
    found = find(name, version)
    return as_library(found) if found is not None else None


def named(name: object) -> dict | None:
    """The newest copy set of this library, whatever version."""
    if not isinstance(name, str) or not _stores:
        return None
    return next((r for r in _visible() if r["library"] == name), None)


def by_family(family: object) -> dict | None:
    if not isinstance(family, str) or not family.startswith(FAMILY_PREFIX) or not _stores:
        return None
    return next((r for r in _visible() if family_of(r) == family), None)


def by_id(the_id: object) -> dict | None:
    return by_family(FAMILY_PREFIX + the_id) if isinstance(the_id, str) else None


def family_of_subject(bare: str) -> str | None:
    """The sandbox family whose image holds this subject key ("starkbank-ecdsa-2.0.0")."""
    if not _stores:
        return None
    for record in reversed(_visible()):          # (the oldest that holds it, as `find` takes it)
        if any(bare == f"{record['library']}-{v['version']}" for v in record["versions"]):
            return family_of(record)
    return None


def images_present() -> dict[str, str]:
    """family -> image tag, for every visible copy set whose image is on this computer and is the one its record names
    (by the image's own id). Never builds or pulls."""
    out: dict[str, str] = {}
    for record in _visible():
        if image_is(record["image"]["tag"], record["image"]["id"]):
            out[family_of(record)] = record["image"]["tag"]
    return out


def image_is(tag: str, the_id: str) -> bool:
    try:
        done = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", tag], capture_output=True, text=True, timeout=20,
                              stdin=subprocess.DEVNULL, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and done.stdout.strip() == the_id
