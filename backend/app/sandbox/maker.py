"""Sandbox research: making a public copy. Only the research command and the prepare command use this module; the
app's web process never does (a test reads the code and fails if it ever imports it).

`make_set` does, in order, for one library:
  1. reads the registry's own documents for the versions asked for (data, held to shape);
  2. picks the helper libraries by fixed rules: the newest version that fits what the FIXED version says it needs, as of
     the day the fixed version was published. Every version of the set gets the same helpers, so the library itself is
     the only thing that differs between them. What can't be read by the rules stops the copy; nothing is guessed;
  3. fetches each file once and checks its bytes against the registry's own fingerprint; the first fetch of a file is
     written into the store's index, and a later fetch that differs is refused (trust on first use, never replaced);
  4. unpacks every file as data. No install script and no set-up program runs: nothing of a package runs here at all;
  5. puts the build folder together (our harness and controls, our asking program, the asking code, the two dummy
     controls, the unpacked versions) and builds the image with no network and no RUN step;
  6. writes the set's record, with the image's own id.

A problem is one plain sentence: a `CopyError` (this copy can't be made), or the registry's own `RegistryError` (it
could not be read; where its `later` is set, nothing was learned and a later try can go differently). Either is a
stop, never a result.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from app import real_libraries
from app.config import COMPONENTS_DIR, DEMO_DIR, PYTHON_BASE_IMAGE
from app.run.runner import _docker_env, _files_digest
from app.sandbox import copies, registries, versions
from app.sandbox.copies import CopyError

TEMPLATES = DEMO_DIR / "sandbox" / "templates"
BUILD_LIMIT_SECONDS = 600
MAX_HELPERS, MAX_DEPTH = 30, 4
MAX_UNPACKED_BYTES, MAX_UNPACKED_FILES = 64 * 1024 * 1024, 20000
LANGUAGE_FILES = {"python": ("asking.py", "asking_code.py"), "node": ("asking.js", "asking_code.js")}
# Our own asking code for the four families: the whole adapter contract (it can also sign, so the speed test runs).
OURS: dict[str, dict[str, Any]] = {"python-ecdsa": {"file": "python-ecdsa/ecdsa_adapter.py", "language": "python", "commands": ["keygen", "sign", "verify", "info", "bench"]},
        "elliptic": {"file": "elliptic/elliptic_adapter.js", "language": "node", "commands": ["keygen", "sign", "verify", "info", "bench"]}}
PYTHON = ["/usr/local/bin/python", "-I", "-X", "pycache_prefix=/scratch/pyc"]
NODE = ["/usr/local/bin/node"]
IN_IMAGE = "/opt/evidence-lab/real"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def harness_sha256(language: str) -> str:
    """One fingerprint of everything of ours that goes into an image: the test harness and controls, and the template."""
    digest = hashlib.sha256()
    _files_digest(digest, COMPONENTS_DIR)
    _files_digest(digest, TEMPLATES / language)
    return digest.hexdigest()


def template_sha256(language: str) -> str:
    return hashlib.sha256((TEMPLATES / language / LANGUAGE_FILES[language][0]).read_bytes()).hexdigest()


# ---------------------------------------------------------------- trust on first use

def _index(root: Path) -> dict[tuple[str, str, str], dict]:
    """What this computer fetched first for each published version: {(registry, package, version): the first line}.
    One version, one file: a release can gain files later (a wheel beside its source package), and a copy is still made
    from the file seen first."""
    out: dict[tuple[str, str, str], dict] = {}
    try:
        lines = (Path(root) / "index.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and all(isinstance(entry.get(k), str) for k in ("registry", "package", "version", "file", "sha256", "at")):
            out.setdefault((entry["registry"], entry["package"], entry["version"]), entry)   # the first one stands
    return out


def fetch(root: Path, source, release: registries.Release) -> dict:
    """One file of one version, checked twice: against the registry's own fingerprint, and against the fingerprint this
    computer saw the first time it fetched that file. Returns the file's record; the bytes are kept in the store."""
    root = Path(root)
    wanted = release.file
    first = _index(root).get((release.registry, release.package, release.version))
    if first is not None and first["file"] != wanted.filename:
        # the registry now puts another file first for this version: the copy is still made from the one seen first
        same = next((f for f in release.others if f.filename == first["file"]), None)
        if same is None:
            raise CopyError(f"this computer made its copy of {release.package} {release.version} from {first['file']} on {first['at'][:10]}, "
                            f"and {registries.WORDS[release.registry]} no longer lists that file. A copy is made from the file seen first, "
                            "so nothing was fetched.", later=True)
        wanted = same
    data = source.file(release.registry, wanted)
    if wanted.size is not None and len(data) != wanted.size:
        raise CopyError(f"{wanted.filename} is not the size {registries.WORDS[release.registry]} gives for it, so it was not used.", later=True)
    if not wanted.holds(data):
        raise CopyError(f"{wanted.filename} does not have the fingerprint {registries.WORDS[release.registry]} itself gives for it, "
                        "so it was not used.", later=True)
    sha = hashlib.sha256(data).hexdigest()
    now = _now()
    if first is None:
        root.mkdir(parents=True, exist_ok=True)
        with (root / "index.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"registry": release.registry, "package": release.package, "version": release.version,
                                     "file": wanted.filename, "sha256": sha, "at": now, "source": source.key}, sort_keys=True) + "\n")
    elif first["sha256"] != sha:
        raise CopyError(f"{wanted.filename} is not the file this computer fetched for {release.package} {release.version} on "
                        f"{first['at'][:10]}. A published version's file does not change, so it was not used.", later=True)
    files = root / "files"
    files.mkdir(parents=True, exist_ok=True)
    (files / f"{sha}-{wanted.filename}").write_bytes(data)
    return {"file": wanted.filename, "package": release.package, "version": release.version, "url": wanted.url, "sha256": sha,
            "registry_fingerprint": wanted.registry_fingerprint, "size": len(data), "fetched_at": (first or {}).get("at", now),
            "source": source.key}


# ---------------------------------------------------------------- helper libraries, by fixed rules

def _fits(registry: str, wanted: str, version: str) -> bool | None:
    return versions.fits_pypi(wanted, version) if registry == "pypi" else versions.fits_npm(wanted, version)


def helpers_for(source, release: registries.Release, as_of: str | None) -> dict[str, registries.Release]:
    """The helper libraries one version needs, each in the newest version that fits and was published on or before
    `as_of`: {name: its release}. Raises CopyError where the rules can't decide."""
    chosen: dict[str, registries.Release] = {}

    def add(needing: registries.Release, depth: int) -> None:
        if needing.unreadable_needs:
            raise CopyError(f"what {needing.package} {needing.version} says it needs could not be read by fixed rules "
                            f"({needing.unreadable_needs[0]})")
        for name, wanted in needing.needs:
            have = chosen.get(name.lower())
            if have is not None:
                if _fits(needing.registry, wanted, have.version) is not True:
                    raise CopyError(f"two parts need versions of {name} that do not fit together")
                continue
            if depth >= MAX_DEPTH or len(chosen) >= MAX_HELPERS:
                raise CopyError("it needs more helper libraries than this version puts together")
            project = source.project(needing.registry, name)
            listed = versions.released(registries.read_versions(needing.registry, project))
            fitting = []
            for entry in listed:
                fit = _fits(needing.registry, wanted, entry["version"])
                if fit is None:
                    raise CopyError(f"what {needing.package} {needing.version} says it needs of {name} (\"{wanted}\") could not be read by fixed rules")
                if fit and (as_of is None or entry.get("published") is None or entry["published"] <= as_of):
                    fitting.append(entry["version"])
            if not fitting:
                raise CopyError(f"no published version of {name} fits what {needing.package} {needing.version} says it needs (\"{wanted}\")")
            version = fitting[-1]
            helper = registries.read_release(needing.registry, name, version, project, source.release(needing.registry, name, version))
            chosen[name.lower()] = helper
            add(helper, depth + 1)

    add(release, 0)
    return chosen


def _needs_met(release: registries.Release, helpers: dict[str, registries.Release]) -> str | None:
    """Why this version can't run with the set's helper libraries, or None."""
    if release.unreadable_needs:
        return "what it says it needs could not be read by fixed rules"
    for name, wanted in release.needs:
        have = helpers.get(name.lower())
        if have is None:
            return f"it needs {name}, which the fixed version does not"
        if _fits(release.registry, wanted, have.version) is not True:
            return f"it needs another version of {name} than the fixed version runs with"
    return None


# ---------------------------------------------------------------- unpacking, as data

def _safe(name: str) -> PurePosixPath | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or any(len(p) > 200 for p in path.parts):
        return None
    return path


def _members(data: bytes, filename: str) -> dict[PurePosixPath, bytes]:
    """The regular files inside a package file, by their path inside it. Nothing but plain files and folders is taken:
    a link, a device or a path that leaves the folder refuses the whole file."""
    out: dict[PurePosixPath, bytes] = {}
    total = 0
    try:
        if filename.endswith((".whl", ".zip")):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    path = _safe(info.filename)
                    if path is None or (info.external_attr >> 28) == 0xA:        # (0xA: a symbolic link)
                        raise CopyError(f"{filename} holds something that is not a plain file, so it was not unpacked.")
                    total += info.file_size
                    if total > MAX_UNPACKED_BYTES or len(out) >= MAX_UNPACKED_FILES:
                        raise CopyError(f"{filename} is larger unpacked than this version takes.")
                    out[path] = archive.read(info)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                for member in archive:
                    if member.isdir():
                        continue
                    path = _safe(member.name)
                    if path is None or not member.isreg():
                        raise CopyError(f"{filename} holds something that is not a plain file, so it was not unpacked.")
                    total += member.size
                    if total > MAX_UNPACKED_BYTES or len(out) >= MAX_UNPACKED_FILES:
                        raise CopyError(f"{filename} is larger unpacked than this version takes.")
                    handle = archive.extractfile(member)
                    out[path] = handle.read() if handle is not None else b""
    except (tarfile.TarError, zipfile.BadZipFile, OSError, EOFError, ValueError, RuntimeError):
        raise CopyError(f"{filename} could not be read as a package file.") from None
    return out


def _strip_top(members: dict[PurePosixPath, bytes]) -> dict[PurePosixPath, bytes]:
    """A source package and an npm package keep everything in one top folder: take what is inside it."""
    tops = {p.parts[0] for p in members}
    if len(tops) != 1 or any(len(p.parts) < 2 for p in members):
        raise CopyError("a package file does not keep its files in one top folder, so it was not unpacked.")
    return {PurePosixPath(*p.parts[1:]): data for p, data in members.items()}


def _python_tree(file: dict, data: bytes) -> tuple[dict[PurePosixPath, bytes], dict]:
    """(what goes on the library's import path, what the package says it is). From a wheel: everything. From a source
    package: only the importable folders and modules; its set-up program is left out, and nothing of it runs."""
    members = _members(data, file["file"])
    if file["file"].endswith(".whl"):
        meta = next((d for p, d in members.items() if len(p.parts) == 2 and p.parts[0].endswith(".dist-info") and p.name == "METADATA"), None)
        tree = members
    else:
        inside = _strip_top(members)
        meta = inside.get(PurePosixPath("PKG-INFO"))
        base = PurePosixPath("src") if any(p.parts[0] == "src" and p.name == "__init__.py" for p in inside) else None
        tree = {}
        for path, content in inside.items():
            rel = PurePosixPath(*path.parts[1:]) if base is not None and path.parts[0] == "src" and len(path.parts) > 1 else (path if base is None else None)
            if rel is None or path.suffix not in (".py", ".pyi", ".typed", ".txt", ".json") and path.name != "py.typed":
                continue
            package_dir = len(rel.parts) > 1 and (PurePosixPath(rel.parts[0]) / "__init__.py") in {
                (PurePosixPath(*q.parts[1:]) if base is not None and q.parts[0] == "src" and len(q.parts) > 1 else q) for q in inside}
            module = len(rel.parts) == 1 and rel.suffix == ".py" and rel.name not in ("setup.py", "conftest.py")
            if package_dir or module:
                tree[rel] = content
    says: dict[str, str | None] = {"name": None, "version": None}
    for line in (meta or b"").decode("utf-8", "replace").splitlines()[:200]:
        if line.startswith("Name: ") and says["name"] is None:
            says["name"] = line[6:].strip()[:120]
        elif line.startswith("Version: ") and says["version"] is None:
            says["version"] = line[9:].strip()[:80]
        elif not line.strip():
            break
    if not tree:
        raise CopyError(f"{file['file']} holds no Python code that can be loaded as it is, so no copy was made of it.")
    return tree, says


def _node_tree(file: dict, data: bytes) -> tuple[dict[PurePosixPath, bytes], dict]:
    inside = _strip_top(_members(data, file["file"]))
    says: dict[str, str | None] = {"name": None, "version": None}
    try:
        package = json.loads(inside[PurePosixPath("package.json")].decode("utf-8"))
        if isinstance(package, dict):
            says = {"name": str(package.get("name"))[:120] if package.get("name") else None,
                    "version": str(package.get("version"))[:80] if package.get("version") else None}
    except (KeyError, ValueError, RecursionError):
        raise CopyError(f"{file['file']} has no readable package.json, so no copy was made of it.") from None
    return inside, says


def _write_tree(folder: Path, tree: dict[PurePosixPath, bytes]) -> None:
    for path, content in tree.items():
        target = folder.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o644)


def _tree_sha256(folder: Path) -> str:
    digest = hashlib.sha256()
    _files_digest(digest, folder)
    return digest.hexdigest()


# ---------------------------------------------------------------- the image

def _docker(args: list[str], limit: int) -> tuple[int | None, str]:
    try:
        done = subprocess.run(["docker", *args], capture_output=True, text=True, errors="replace", timeout=limit,
                              stdin=subprocess.DEVNULL, shell=False, env=_docker_env())
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return done.returncode, done.stdout


def image_id(tag: str) -> str | None:
    rc, out = _docker(["image", "inspect", "--format", "{{.Id}}", tag], 20)
    return out.strip() if rc == 0 and out.strip().startswith("sha256:") else None


def base_images(language: str) -> dict[str, str]:
    return {"PYTHON_BASE": PYTHON_BASE_IMAGE, **({"NODE_IMAGE": real_libraries.NODE_IMAGE} if language == "node" else {})}


def not_ready(language: str) -> str | None:
    """Why an image of public copies could not be built right now, in one plain sentence, or None when it could: Docker
    answers and every base image the build starts from is on this computer. (Asked before anything that costs.)"""
    rc, _ = _docker(["version", "--format", "{{.Server.Version}}"], 20)
    if rc != 0:
        return "Docker is not running on this computer, so no image of public copies can be built"
    if any(image_id(reference) is None for reference in base_images(language).values()):
        return "a base image that the image of public copies starts from is not on this computer (./run-demo.sh prepares it)"
    return None


def subjects_for(library: str, language: str, the_versions: list[str], asking: dict) -> dict[str, list[str]]:
    """The image's fixed table: which command line answers for which subject."""
    table: dict[str, list[str]] = {}
    for version in the_versions:
        where = f"{IN_IMAGE}/{library}-{version}"
        key = f"{library}-{version}"
        if asking["kind"] == "ours":
            adapter = f"{IN_IMAGE}/{Path(asking['file']).name}"
            run = (PYTHON if language == "python" else NODE) + [adapter, where]
            table[key] = run
            table[f"control-slow:{key}"] = run + ["--slow"]
        else:
            program = (PYTHON + [f"{IN_IMAGE}/asking.py"]) if language == "python" else (NODE + [f"{IN_IMAGE}/asking.js"])
            table[key] = program + [where, f"{IN_IMAGE}/code"]
            # the two controls of the known-answer check: they must be refused by it, every time
            table[f"dummy-yes:{key}"] = program + [where, f"{IN_IMAGE}/dummy_yes"]
            table[f"dummy-no:{key}"] = program + [where, f"{IN_IMAGE}/dummy_no"]
    return table


def make_set(*, root: Path, source, library: str, registry: str, package: str, wanted: list[dict], asking: dict, say=print) -> tuple[dict, list[dict]]:
    """Make one copy set and build its image. `wanted`: [{"version", "role"}], the fixed version among them. `asking`:
    {"kind": "ours"} for a library of ours, or {"kind": "written", "author", "source"}. Returns (the set's record, the
    versions that were left out, each with its plain reason). Raises CopyError, or passes a RegistryError on."""
    if registry not in registries.HOSTS:
        raise CopyError("this version can make a copy only of a package published on npm or PyPI")
    language = registries.LANGUAGES[registry]
    if not wanted or len(wanted) > copies.MAX_VERSIONS or sum(1 for w in wanted if w["role"] == "fixed") != 1:
        raise CopyError("a copy set holds one fixed version and at most seven others")
    project = source.project(registry, package)
    releases = {w["version"]: registries.read_release(registry, package, w["version"], project, source.release(registry, package, w["version"]))
                for w in wanted}
    fixed = next(w["version"] for w in wanted if w["role"] == "fixed")
    helpers = helpers_for(source, releases[fixed], releases[fixed].published)
    left_out: list[dict] = []
    kept = []
    for w in wanted:
        why = _needs_met(releases[w["version"]], helpers) if w["version"] != fixed else None
        if why is None:
            kept.append(w)
        elif w["role"] in ("affected",):
            raise CopyError(f"{package} {w['version']}, the affected version, can't be put together with the fixed version's helper libraries: {why}")
        else:
            left_out.append({"version": w["version"], "role": w["role"], "reason": f"it was left out: {why}."})
    if asking["kind"] == "ours":
        ours = OURS.get(library)
        if ours is None or ours["language"] != language:
            raise CopyError(f"the app has no asking code of its own for {library}")
        source_text = (real_libraries.REAL_DIR / ours["file"]).read_text(encoding="utf-8")
        asking_record: dict[str, Any] = {"kind": "ours", "author": "Isogeny Labs (the app's own wrapper for this library)", "language": language,
                         "file": ours["file"], "source": source_text, "commands": list(ours["commands"])}
    else:
        source_text = str(asking["source"])
        asking_record = {"kind": "written", "author": str(asking["author"])[:80], "language": language, "file": LANGUAGE_FILES[language][1],
                         "source": source_text, "commands": ["verify", "info"]}
    asking_record.update(sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(), lines=len(source_text.splitlines()),
                         template_sha256=template_sha256(language))
    with tempfile.TemporaryDirectory(prefix="evidence-lab-sandbox-") as scratch:
        context = Path(scratch)
        shutil.copytree(COMPONENTS_DIR, context / "components", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        real = context / "real"
        real.mkdir()
        helper_files = {name: fetch(root, source, release) for name, release in sorted(helpers.items())}
        helper_data = {name: (Path(root) / "files" / f"{f['sha256']}-{f['file']}").read_bytes() for name, f in helper_files.items()}
        version_records = []
        for w in kept:
            release = releases[w["version"]]
            record = fetch(root, source, release)
            data = (Path(root) / "files" / f"{record['sha256']}-{record['file']}").read_bytes()
            folder = real / f"{library}-{w['version']}"
            if language == "python":
                tree, says = _python_tree(record, data)
                _write_tree(folder, tree)
                for name, f in helper_files.items():
                    _write_tree(folder, _python_tree(f, helper_data[name])[0])
            else:
                tree, says = _node_tree(record, data)
                _write_tree(folder / "node_modules" / package, tree)
                for name, f in helper_files.items():
                    _write_tree(folder / "node_modules" / helpers[name].package, _node_tree(f, helper_data[name])[0])
            if says["version"] != w["version"]:
                raise CopyError(f"{record['file']} says it is version {says['version']}, not {w['version']}, so it was not used.")
            (real / f"{library}-{w['version']}.says.json").write_text(
                json.dumps({"name": library, "package": package, "version": says["version"]}, sort_keys=True), encoding="utf-8")
            version_records.append({"version": w["version"], "role": w["role"], "published": release.published,
                                    "files": [record, *[helper_files[n] for n in sorted(helper_files)]], "tree_sha256": _tree_sha256(folder),
                                    "helpers": [f"{helpers[n].package} {helpers[n].version}" for n in sorted(helpers)],
                                    "says": {"name": says["name"], "version": says["version"]}})
        if asking_record["kind"] == "ours":
            shutil.copy(real_libraries.REAL_DIR / asking_record["file"], real / Path(asking_record["file"]).name)
        else:
            template, code_file = LANGUAGE_FILES[language]
            shutil.copy(TEMPLATES / language / template, real / template)
            (real / "code").mkdir()
            (real / "code" / code_file).write_text(source_text, encoding="utf-8")
            for dummy in ("dummy_yes", "dummy_no"):
                shutil.copytree(TEMPLATES / language / dummy, real / dummy)
        (real / "subjects.json").write_text(json.dumps(subjects_for(library, language, [v["version"] for v in version_records], asking_record),
                                                       indent=2), encoding="utf-8")
        shutil.copy(TEMPLATES / language / "Dockerfile", context / "Dockerfile")
        for path in context.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        record = {"schema": copies.SCHEMA, "library": library, "registry": registry, "package": package, "language": language,
                  "versions": version_records, "asking": asking_record, "harness_sha256": harness_sha256(language),
                  "base_images": base_images(language), "made_at": _now(), "checked": {}}
        record["id"] = copies.set_id(record)
        tag = copies.image_tag(library, record["id"])
        args = ["build", "--pull=false", "--network", "none", "-t", tag, "-f", str(context / "Dockerfile")]
        for name, reference in record["base_images"].items():
            # (a build would fetch a base image that is not here, whatever --pull says: so it is looked for first, and
            #  a missing one is a stop. Only the prepare step may pull.)
            if image_id(reference) is None:
                raise CopyError(f"the image of the public copies of {library} was not built: a base image it starts from is not on this "
                                "computer, or Docker is not running (./run-demo.sh prepares the base images).", later=True)
            args += ["--build-arg", f"{name}={reference}"]
        say(f"Building the image of the public copies of {library} ({', '.join(v['version'] for v in version_records)}), with no network ...")
        rc, _ = _docker([*args, str(context)], BUILD_LIMIT_SECONDS)
        built = image_id(tag) if rc == 0 else None
        if built is None:
            raise CopyError(f"the image of the public copies of {library} could not be built (is Docker running, and are the base images prepared?)",
                            later=True)
        record["image"] = {"tag": tag, "id": built}
    copies.write_set(root, record)
    copies.forget_cache()
    return record, left_out


def library_files(root: Path, source, registry: str, package: str, version: str) -> tuple[dict[PurePosixPath, bytes], str | None, dict]:
    """The files of one version as they would go into an image, its read-me if it has one, and its file's record: what
    the author of asking code is shown. Fetched and checked like every copy; nothing of it runs."""
    project = source.project(registry, package)
    release = registries.read_release(registry, package, version, project, source.release(registry, package, version))
    record = fetch(root, source, release)
    data = (Path(root) / "files" / f"{record['sha256']}-{record['file']}").read_bytes()
    members = _members(data, record["file"])
    inside = members if record["file"].endswith(".whl") else _strip_top(members)
    readme = next((inside[p].decode("utf-8", "replace") for p in sorted(inside)
                   if len(p.parts) == 1 and p.name.lower() in ("readme.md", "readme.rst", "readme.txt", "readme")), None)
    tree = _python_tree(record, data)[0] if registries.LANGUAGES[registry] == "python" else _node_tree(record, data)[0]
    return tree, readme, record
