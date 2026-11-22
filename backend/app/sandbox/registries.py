"""Sandbox research: the public package registries, read as data (npm and PyPI first; Kevin's decision 5).

Only the research command reads a registry, and only to make a public copy of a version an advisory names. What is
sent is the name (and for PyPI the version) of a public package, as part of the address of a public file. Nothing of
an assessment is sent. A registry's answer is data: it is held to the shape the registry documents, nothing in it
runs, and a file is used only if its bytes have the fingerprint the registry itself gives for it.

A folder of recorded answers and files on this computer can stand in for the registries (`EVIDENCE_LAB_REGISTRY_
SOURCE`; tests, the walks, a demo with no internet). Its layout:
    pypi/<name>.json            the project's document          (pypi.org/pypi/<name>/json)
    pypi/<name>/<version>.json  one release's document          (pypi.org/pypi/<name>/<version>/json)
    npm/<name>.json             the package's document          (registry.npmjs.org/<name>)
    files/<file name>           the files themselves
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# The look's word for where a library is published -> the registry this module can read. Others: no copy can be made.
ECOSYSTEMS = {"PyPI": "pypi", "npm": "npm"}
WORDS = {"pypi": "PyPI", "npm": "npm"}
HOSTS = {"pypi": ("pypi.org", "files.pythonhosted.org"), "npm": ("registry.npmjs.org",)}
LANGUAGES = {"pypi": "python", "npm": "node"}
TIMEOUT_SECONDS = 30.0
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_VERSIONS = 5000
_NAME = re.compile(r"^(@[a-z0-9][a-z0-9._-]{0,60}/)?[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,60}$")
_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,150}\.(whl|tar\.gz|tgz|zip)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DAY = re.compile(r"^(\d{4}-\d{2}-\d{2})T")


class RegistryError(Exception):
    """A registry could not be read, or what it answered is not what it documents. One plain sentence. A stop, never
    a result: "couldn't fetch" is not "no such copy"."""


@dataclass(frozen=True)
class File:
    filename: str
    url: str
    kind: str                       # "wheel" | "sdist" | "tgz"
    size: int | None
    sha256: str | None = None       # PyPI's own value for the file
    sha512_base64: str | None = None    # npm's own value (its "integrity")

    def holds(self, data: bytes) -> bool:
        """Do these bytes have the fingerprint the registry itself gives for the file?"""
        if self.sha256 is not None:
            return hashlib.sha256(data).hexdigest() == self.sha256
        if self.sha512_base64 is not None:
            return base64.b64encode(hashlib.sha512(data).digest()).decode("ascii") == self.sha512_base64
        return False

    @property
    def registry_fingerprint(self) -> str:
        return f"sha256:{self.sha256}" if self.sha256 else f"sha512:{self.sha512_base64}"


@dataclass
class Release:
    registry: str                   # "pypi" | "npm"
    package: str
    version: str
    published: str | None           # the day the registry says it was published (YYYY-MM-DD)
    file: File
    needs: list[tuple[str, str]] = field(default_factory=list)      # (a helper library's name, what versions of it fit)
    unreadable_needs: list[str] = field(default_factory=list)       # what it says it needs that this reader could not read


def check_name(registry: str, package: object) -> str:
    if registry not in HOSTS or not isinstance(package, str) or not _NAME.match(package) or ".." in package:
        raise RegistryError("That is not a package name this version can ask a registry about.")
    return package


def check_version(version: object) -> str:
    if not isinstance(version, str) or not _VERSION.match(version) or ".." in version:
        raise RegistryError("That is not a version this version can ask a registry about.")
    return version


# ---------------------------------------------------------------- where the bytes come from

Transport = Callable[[str, float, int], bytes]


def _http(url: str, timeout: float, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/json, */*", "User-Agent": "evidence-lab-sandbox"})
    with urllib.request.urlopen(request, timeout=timeout) as answer:     # (a fixed https address built here, on a listed host)
        return answer.read(limit + 1)


class LiveRegistry:
    """The public registries themselves. Every address is built here, on one of the listed hosts, and nowhere else."""

    key = "live"

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport or _http

    def _get(self, registry: str, url: str, limit: int, what: str) -> bytes:
        host = url.split("/", 3)[2] if url.startswith("https://") else ""
        if host not in HOSTS[registry]:
            raise RegistryError(f"{what} is at an address that is not one of the registry's own hosts, so it was not fetched.")
        try:
            data = self._transport(url, TIMEOUT_SECONDS, limit)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise RegistryError(f"{WORDS[registry]} has no {what}.") from None
            raise RegistryError(f"{WORDS[registry]} answered with an error (HTTP {int(exc.code)}) for {what}.") from None
        except OSError as exc:
            raise RegistryError(f"{WORDS[registry]} could not be reached ({exc.__class__.__name__}). Nothing was fetched.") from None
        except Exception as exc:      # never the error's own words: they can hold an address or a header
            raise RegistryError(f"The request to {WORDS[registry]} did not come back whole ({exc.__class__.__name__}).") from None
        if len(data) > limit:
            raise RegistryError(f"{what} is larger than this version takes.")
        return data

    def project(self, registry: str, package: str) -> bytes:
        package = check_name(registry, package)
        url = f"https://pypi.org/pypi/{package}/json" if registry == "pypi" else f"https://registry.npmjs.org/{package.replace('/', '%2F')}"
        return self._get(registry, url, MAX_DOCUMENT_BYTES, f"package named {package}")

    def release(self, registry: str, package: str, version: str) -> bytes | None:
        """PyPI keeps what a release needs in a document of its own; npm's project document holds everything."""
        if registry != "pypi":
            return None
        package, version = check_name(registry, package), check_version(version)
        return self._get(registry, f"https://pypi.org/pypi/{package}/{version}/json", MAX_DOCUMENT_BYTES, f"version {version} of {package}")

    def file(self, registry: str, wanted: File) -> bytes:
        return self._get(registry, wanted.url, MAX_FILE_BYTES, f"file {wanted.filename}")


class RecordedRegistry:
    """A folder of recorded answers and files on this computer. Nothing is sent anywhere."""

    key = "recorded"

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def _read(self, relative: str, limit: int, what: str, registry: str) -> bytes:
        path = (self.folder / relative).resolve()
        if self.folder.resolve() not in path.parents or not path.is_file() or path.is_symlink():
            raise RegistryError(f"The recorded registry folder has no {what}.")
        data = path.read_bytes()
        if len(data) > limit:
            raise RegistryError(f"{what} is larger than this version takes.")
        return data

    def project(self, registry: str, package: str) -> bytes:
        package = check_name(registry, package)
        return self._read(f"{registry}/{package.replace('/', '__')}.json", MAX_DOCUMENT_BYTES, f"package named {package}", registry)

    def release(self, registry: str, package: str, version: str) -> bytes | None:
        if registry != "pypi":
            return None
        package, version = check_name(registry, package), check_version(version)
        return self._read(f"pypi/{package}/{version}.json", MAX_DOCUMENT_BYTES, f"version {version} of {package}", registry)

    def file(self, registry: str, wanted: File) -> bytes:
        if not _FILE.match(wanted.filename):
            raise RegistryError("That is not a file name this version takes.")
        return self._read(f"files/{wanted.filename}", MAX_FILE_BYTES, f"file {wanted.filename}", registry)


def source_for(folder: Path | None):
    return RecordedRegistry(folder) if folder else LiveRegistry()


# ---------------------------------------------------------------- reading an answer (it is data: exact shape or refused)

def _load(raw: bytes, registry: str) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise RegistryError(f"The answer of {WORDS[registry]} is not valid JSON.") from None
    if not isinstance(data, dict):
        raise RegistryError(f"The answer of {WORDS[registry]} is not in the shape it documents.")
    return data


def _day(value: object) -> str | None:
    m = _DAY.match(value) if isinstance(value, str) else None
    return m.group(1) if m else None


def read_versions(registry: str, raw: bytes) -> list[dict]:
    """Every version a project's document lists: [{"version", "published"}] (in the document's order, held to MAX_VERSIONS)."""
    data = _load(raw, registry)
    out = []
    if registry == "pypi":
        releases = data.get("releases")
        if not isinstance(releases, dict):
            raise RegistryError("The answer of PyPI is not in the shape it documents.")
        for version, files in list(releases.items())[:MAX_VERSIONS]:
            if not isinstance(version, str) or not _VERSION.match(version) or not isinstance(files, list) or not files:
                continue                                    # (a version with no file was never published as one)
            days = sorted(d for d in (_day(f.get("upload_time_iso_8601") or f.get("upload_time")) for f in files if isinstance(f, dict)) if d)
            out.append({"version": version, "published": days[0] if days else None})
    else:
        versions, times = data.get("versions"), data.get("time")
        if not isinstance(versions, dict):
            raise RegistryError("The answer of npm is not in the shape it documents.")
        for version in list(versions)[:MAX_VERSIONS]:
            if isinstance(version, str) and _VERSION.match(version):
                out.append({"version": version, "published": _day(times.get(version)) if isinstance(times, dict) else None})
    return out


def _pypi_file(files: object) -> File | None:
    """The one file of a release a copy is made from: a wheel that is plain Python, or else the source package."""
    usable = []
    for f in files if isinstance(files, list) else []:
        if not isinstance(f, dict) or f.get("yanked") is True:
            continue
        name, url, digests = f.get("filename"), f.get("url"), f.get("digests")
        sha = digests.get("sha256") if isinstance(digests, dict) else None
        if not (isinstance(name, str) and _FILE.match(name) and isinstance(url, str) and isinstance(sha, str) and _HEX64.match(sha)):
            continue
        size = f.get("size") if isinstance(f.get("size"), int) and not isinstance(f.get("size"), bool) else None
        if f.get("packagetype") == "bdist_wheel" and name.endswith("-none-any.whl"):
            usable.append((0, File(name, url, "wheel", size, sha256=sha)))
        elif f.get("packagetype") == "sdist" and name.endswith((".tar.gz", ".zip")):
            usable.append((1, File(name, url, "sdist", size, sha256=sha)))
    usable.sort(key=lambda u: (u[0], u[1].filename))
    return usable[0][1] if usable else None


_REQUIRES = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:\(([^)]*)\)|([^;]*))?\s*(?:;(.*))?$")


def _pypi_needs(requires: object) -> tuple[list[tuple[str, str]], list[str]]:
    needs, unreadable = [], []
    for line in requires if isinstance(requires, list) else []:
        m = _REQUIRES.match(line) if isinstance(line, str) and len(line) <= 300 else None
        if m is None:
            unreadable.append(str(line)[:80])
            continue
        name, in_brackets, plain, marker = m.groups()
        marker = (marker or "").strip()
        if "extra" in marker:
            continue                                        # only wanted for an optional extra: not needed to run the library
        if marker:
            unreadable.append(str(line)[:80])               # (a condition on the computer or the Python version: not guessed)
            continue
        needs.append((name, (in_brackets if in_brackets is not None else plain or "").strip()))
    return needs, unreadable


def read_release(registry: str, package: str, version: str, project_raw: bytes, release_raw: bytes | None) -> Release:
    """One version of one package: its file with the registry's own fingerprint, and what it says it needs."""
    package, version = check_name(registry, package), check_version(version)
    if registry == "pypi":
        project = _load(project_raw, registry)
        files = (project.get("releases") or {}).get(version) if isinstance(project.get("releases"), dict) else None
        chosen = _pypi_file(files)
        if chosen is None:
            raise RegistryError(f"PyPI lists no plain-Python file for {package} {version} (a wheel for every computer, or its source package).")
        release = _load(release_raw, registry) if release_raw is not None else {}
        info = release.get("info") if isinstance(release.get("info"), dict) else {}
        needs, unreadable = _pypi_needs(info.get("requires_dist"))
        day = next((d["published"] for d in read_versions(registry, project_raw) if d["version"] == version), None)
        return Release(registry, package, version, day, chosen, needs, unreadable)
    project = _load(project_raw, registry)
    entry = (project.get("versions") or {}).get(version) if isinstance(project.get("versions"), dict) else None
    dist = entry.get("dist") if isinstance(entry, dict) and isinstance(entry.get("dist"), dict) else None
    if dist is None:
        raise RegistryError(f"npm lists no version {version} of {package}.")
    url, integrity = dist.get("tarball"), dist.get("integrity")
    if not (isinstance(url, str) and isinstance(integrity, str) and integrity.startswith("sha512-") and len(integrity) < 200):
        raise RegistryError(f"npm gives no SHA-512 fingerprint for {package} {version}, so its file can't be checked.")
    name = url.rsplit("/", 1)[-1]
    if not _FILE.match(name):
        raise RegistryError(f"The file of {package} {version} has a name this version does not take.")
    if entry.get("scripts") and any(k in entry["scripts"] for k in ("preinstall", "install", "postinstall")):
        pass        # (an install script is never run here: the files are unpacked as data, and that is all)
    needs, unreadable = [], []
    for helper, wanted in (entry.get("dependencies") or {}).items() if isinstance(entry.get("dependencies"), dict) else []:
        if isinstance(helper, str) and _NAME.match(helper) and isinstance(wanted, str) and len(wanted) <= 200:
            needs.append((helper, wanted))
        else:
            unreadable.append(str(helper)[:80])
    times = project.get("time") if isinstance(project.get("time"), dict) else {}
    return Release(registry, package, version, _day(times.get(version)), File(name, url, "tgz", None, sha512_base64=integrity[len("sha512-"):]),
                   needs, unreadable)
