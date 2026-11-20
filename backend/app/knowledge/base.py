"""Loading the knowledge base and looking a library up in it (phase 4d, Level 1).

A lookup is never a pass: its answers carry the label "Release notes say" (`release_notes`). It reads only the
files under knowledge/libraries/ and never the network. The order of the answers when there is no yes or no is
fixed (docs/SPEC.md section 7e):

1. the library has no file                        -> not_in_knowledge_base (all three questions)
2. its file says only your environment can answer -> needs_your_environment (all three)
3. the question does not fit this kind of library -> doesnt_apply
4. the version can't be read                      -> couldnt_tell_version
5. no claim covers this version                   -> not_in_knowledge_base
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.config import REPO_ROOT
from app.knowledge.model import CAPABILITIES, Declared, LibraryFile, Source
from app.knowledge.versions import Version, at_least, key, read_version, shown

KNOWLEDGE_DIR = REPO_ROOT / "knowledge" / "libraries"
# Which question needs which kind of library; a library without that role answers "Doesn't apply".
ROLE_OF = {"ml_kem_768": "key_exchange", "x25519mlkem768": "tls", "ml_dsa_65": "signatures"}


class KnowledgeError(Exception):
    """A knowledge-base file that does not follow the rules. Said in plain words, naming the file."""


@dataclass(frozen=True)
class Answer:
    capability: str
    answer: str                    # yes | no | doesnt_apply | not_in_knowledge_base | couldnt_tell_version | needs_your_environment
    label: str | None              # "release_notes" for a yes or no; None otherwise
    first_version: str | None      # beside a "no": the version that added it; None when not known
    source: Source | None
    reason: str                    # one plain sentence saying why this is the answer

    def as_dict(self) -> dict:
        return {"capability": self.capability, "answer": self.answer, "label": self.label,
                "first_version": self.first_version, "reason": self.reason,
                "source": self.source.model_dump() if self.source else None}


@dataclass(frozen=True)
class Needs:
    """What one version of a library declares it needs (phase 6e), or why that is not known."""

    answer: str                    # declared | doesnt_apply | not_in_knowledge_base | couldnt_tell_version
    version: str | None            # the version as it was read, when it could be
    entry: Declared | None         # the knowledge-base entry, for "declared"
    reason: str                    # one plain sentence saying why this is the answer

    def as_dict(self) -> dict:
        entry = self.entry
        return {"answer": self.answer, "version": self.version, "reason": self.reason,
                "needs": [n.model_dump() for n in entry.needs] if entry else None,
                "file": entry.file if entry else None, "file_sha256": entry.file_sha256 if entry else None,
                "source": entry.source.model_dump() if entry else None}


def purl_base(purl: object) -> str | None:
    """pkg:type/namespace/name, lower-case, without version, qualifiers or subpath; None if it is not a purl."""
    if not isinstance(purl, str) or not purl.startswith("pkg:") or len(purl) > 500:
        return None
    base = re.split(r"[@?#]", purl, maxsplit=1)[0]
    return base.lower() if re.fullmatch(r"pkg:[a-z0-9.+-]+/[^\s]+", base, re.I) else None


class KnowledgeBase:
    def __init__(self, files: dict[str, LibraryFile]):
        self.files = files
        self._by_purl = {p.purl.lower(): f for f in files.values() for p in f.packages}
        self._by_name = {n.lower(): f for f in files.values() for n in f.match_names}

    def find(self, purl: object, name: object) -> LibraryFile | None:
        base = purl_base(purl)
        if base is not None:
            return self._by_purl.get(base)
        return self._by_name.get(name.lower()) if isinstance(name, str) else None

    def look_up(self, purl: object, name: object, version_text: object) -> dict[str, Answer]:
        entry = self.find(purl, name)
        if entry is None:
            why = "This library has no file in our knowledge base yet."
            return {c: Answer(c, "not_in_knowledge_base", None, None, None, why) for c in CAPABILITIES}
        if entry.needs_your_environment is not None:
            env = entry.needs_your_environment
            return {c: Answer(c, "needs_your_environment", None, None, env.source, env.reason) for c in CAPABILITIES}
        version = read_version(version_text)
        return {c: self._one(entry, c, version) for c in CAPABILITIES}

    @staticmethod
    def _one(entry: LibraryFile, capability: str, version: Version | None) -> Answer:
        if ROLE_OF[capability] not in entry.roles:
            return Answer(capability, "doesnt_apply", None, None, None,
                          f"This question is not asked of {entry.label}: it is not a library of that kind.")
        if version is None:
            return Answer(capability, "couldnt_tell_version", None, None, None,
                          "The version in your file can't be read as a released version number, so it can't be looked up.")
        claims = [c for c in entry.claims if c.capability == capability]
        yes = next((c for c in claims if c.answer == "yes"), None)
        if yes is not None and yes.versions.from_ and at_least(version, yes.versions.from_):
            return Answer(capability, "yes", "release_notes", None, yes.source,
                          f"{yes.source.title} says this was added in {yes.versions.from_}; this version is {shown(version)}.")
        no = next((c for c in claims if c.answer == "no"), None)
        if no is not None and no.versions.before and not at_least(version, no.versions.before):
            return Answer(capability, "no", "release_notes", no.versions.before, no.source,
                          f"{no.source.title} says this was added in {no.versions.before}; this version is {shown(version)}, before that.")
        return Answer(capability, "not_in_knowledge_base", None, None, None,
                      "Our knowledge base has no official source for this question and this library.")

    def declared_needs(self, purl: object, name: object, version_text: object) -> Needs:
        """What this version of this library itself declares it needs, from its publisher's package file. The order of
        the answers when it is not known is the lookup's: no file, no such package file, no readable version, no entry
        for this version. Nothing is worked out from another version."""
        entry = self.find(purl, name)
        if entry is None:
            return Needs("not_in_knowledge_base", None, None, "This library has no file in our knowledge base yet.")
        if entry.no_package_file is not None:
            return Needs("doesnt_apply", None, None, entry.no_package_file)
        version = read_version(version_text)
        if version is None:
            return Needs("couldnt_tell_version", None, None,
                         "The version can't be read as a released version number, so what it declares can't be looked up.")
        found = next((d for d in entry.declared if key(read_version(d.version)) == key(version)), None)     # type: ignore[arg-type]
        if found is None:
            return Needs("not_in_knowledge_base", shown(version), None,
                         f"Our knowledge base does not hold what {entry.label} {shown(version)} declares it needs.")
        return Needs("declared", shown(version), found,
                     f"{found.source.title} lists {len(found.needs)} {'package' if len(found.needs) == 1 else 'packages'} "
                     f"that {entry.label} {found.version} needs." if found.needs else
                     f"{found.source.title} lists no package that {entry.label} {found.version} needs.")

    def source_urls(self) -> tuple[str, ...]:
        """Every official source link in the knowledge base, in a fixed order (the evidence report may link to these)."""
        urls = [c.source.url for f in self.files.values() for c in f.claims]
        urls += [f.needs_your_environment.source.url for f in self.files.values() if f.needs_your_environment]
        return tuple(sorted(set(urls)))

    def first_version(self, entry: LibraryFile, capability: str) -> str | None:
        """The lowest version with a "yes" for this question, or None when no version is known to do it."""
        yes = [c.versions.from_ for c in entry.claims if c.capability == capability and c.answer == "yes" and c.versions.from_]
        return min(yes, key=lambda v: key(read_version(v))) if yes else None  # type: ignore[arg-type]


def load(directory: Path = KNOWLEDGE_DIR) -> KnowledgeBase:
    """Every file under knowledge/libraries/, checked. A broken file stops the load with its name and the problem."""
    files: dict[str, LibraryFile] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = LibraryFile.model_validate(data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeError(f"{path.name}: not a readable JSON file ({exc.__class__.__name__}).") from None
        except ValidationError as exc:
            first = exc.errors(include_url=False)[0]
            where = ".".join(str(p) for p in first["loc"]) or "(top)"
            raise KnowledgeError(f"{path.name}: {where}: {first['msg']}") from None
        if entry.library != path.stem:
            raise KnowledgeError(f"{path.name}: library is {entry.library!r}; it must equal the file name.")
        files[entry.library] = entry
    kb = KnowledgeBase(files)
    owners: dict[str, str] = {}
    for f in files.values():
        for p in f.packages:
            if owners.setdefault(p.purl.lower(), f.library) != f.library:
                raise KnowledgeError(f"{f.library}.json: {p.purl} is already listed by {owners[p.purl.lower()]}.json.")
    return kb


_CACHE: dict[Path, tuple[float, KnowledgeBase]] = {}


def knowledge_base(directory: Path = KNOWLEDGE_DIR) -> KnowledgeBase:
    """The loaded knowledge base, read again when a file changes."""
    stamp = max((p.stat().st_mtime for p in directory.glob("*.json")), default=0.0)
    cached = _CACHE.get(directory)
    if cached is None or cached[0] != stamp:
        _CACHE[directory] = (stamp, load(directory))
    return _CACHE[directory][1]


def schema() -> dict:
    """The model written out as JSON Schema (knowledge/schema.json), for people editing the files by hand."""
    out = LibraryFile.model_json_schema(by_alias=True)
    out["$id"] = "isogeny.knowledge/1"
    out["title"] = "One library in the Isogeny Evidence Lab knowledge base"
    return out
