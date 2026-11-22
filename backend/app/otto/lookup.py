"""Look for new advisories (phase 6, Otto's research loop): reading published advisories from one public source.

A person presses **Look for new advisories** on the Advisories page. The app then asks one public source, OSV
(osv.dev), what it has published about the libraries this assessment names, and keeps the ones that name a version
the assessment has. Reading is free: no Claude step is in it.

Rules kept here:
  - What is sent is the package's name and its ecosystem ("elliptic", "npm"), and nothing else: no version, no
    address, no file, nothing about the assessment. Whether an advisory names your version is worked out here, on
    this computer, from the ranges the source publishes.
  - What comes back is DATA. It is taken only in the exact shape OSV documents; anything else is refused with one
    plain sentence. Nothing in it runs, and nothing in it is an instruction.
  - How serious an advisory is, is never read: a score or a severity in an answer is dropped before anything is kept.
  - Only this module reaches the network for advisories, through `_http_transport`, at one fixed https address, and
    only from `read_source` (a person's click). No test reaches it: tests/conftest.py puts a transport there that
    fails the test, and tests read recorded answers (`RecordedSource`).
  - A recorded source is a folder of files on this computer, for tests, the walks and a demo with no internet: a
    snapshot file (the shape of research/snapshot/*/advisories.json) is used as it is; a file in OSV's own shape,
    named `<ecosystem>__<name>.json`, is read exactly like an answer from the network.

The result is a list of advisories in the snapshot's own shape (app/otto and ottolab already read that), each with
what it says about the versions this assessment has. It decides nothing and proposes nothing: a test for an advisory
exists only after the research step has tried it on public copies.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.knowledge.versions import key as version_key
from app.knowledge.versions import read_version

SOURCE_NAME = "OSV (osv.dev)"
SOURCE_HOST = "api.osv.dev"
SOURCE_URL = "https://api.osv.dev/v1/query"
SOURCE_PAGE = "https://osv.dev/vulnerability/"
SNAPSHOT_SCHEMA = "isogeny.advisory-snapshot/1"
TIMEOUT_SECONDS = 20.0
MAX_ANSWER_BYTES = 8 * 1024 * 1024
MAX_PAGES = 3                  # an answer in more pages than this is cut short, and the look says so
MAX_KEPT = 40                  # advisories one look keeps: first those that name a version the assessment has, then the newest
MAX_RANGES = 200               # version ranges of one record that are kept for matching
MAX_EXCERPTS = 12
MAX_EXCERPT_CHARS = 4000
MAX_ADVISORY_CHARS = 16000
# A package address's type (pkg:npm/...) and the name OSV gives that ecosystem. Others are not asked about: OSV keeps
# a distribution's packages under the distribution's release, which a library's name alone does not give.
ECOSYSTEMS = {"npm": "npm", "pypi": "PyPI", "golang": "Go", "maven": "Maven", "cargo": "crates.io", "nuget": "NuGet", "gem": "RubyGems"}
# Who published a record, by the form of its id, with the licence that publisher states for its records.
PUBLISHERS = (("GHSA-", "GitHub Advisory Database", "CC-BY-4.0"), ("PYSEC-", "PyPA Advisory Database", "CC-BY-4.0"),
              ("GO-", "Go Vulnerability Database", "CC-BY-4.0"), ("RUSTSEC-", "RustSec Advisory Database", "CC0-1.0"))
_CVE = re.compile(r"^CVE-\d{4}-\d{4,7}$")
_ID = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,39}$")
_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{3,39}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,59}$")
_PACKAGE = re.compile(r"^[A-Za-z0-9@][A-Za-z0-9._/@:-]{0,199}$")
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class LookupError_(Exception):
    """The source could not be read, or its answer can't be used. str(exc) is one plain sentence."""


@dataclass(frozen=True)
class Package:
    """One library of the assessment as the source knows it."""
    library: str        # the app's own name for it ("python-ecdsa")
    ecosystem: str      # OSV's name for where it is published ("PyPI")
    name: str           # its name there ("ecdsa")

    @property
    def key(self) -> str:
        return f"{self.ecosystem}__{self.name}"

    @property
    def words(self) -> str:
        return f"{self.name} ({self.ecosystem})"


@dataclass
class Found:
    """One published advisory about one library, as the source gave it: the snapshot's own shape, and what the source's
    ranges say about versions (kept apart: `ranges` is for matching, never shown as the publisher's words)."""
    advisory: dict
    ranges: list[dict] = field(default_factory=list)      # [{"introduced": "2.0.0", "fixed": "6.5.7", "last_affected": None}]
    versions: list[str] = field(default_factory=list)     # versions the source lists one by one
    record_id: str = ""


def package_of(library: str, purls: list[str]) -> Package | None:
    """The package the source can be asked about for this library, from the knowledge base's package addresses.
    None when the library is published nowhere the source keeps by name (OpenSSL, OpenJDK, a distribution's package)."""
    for purl in purls:
        m = re.fullmatch(r"pkg:([a-z0-9.+-]+)/(.+)", str(purl).strip().lower())
        if not m or m.group(1) not in ECOSYSTEMS:
            continue
        name = m.group(2).split("@", 1)[0].split("?", 1)[0]
        if m.group(1) == "maven":
            name = name.replace("/", ":")
        if _PACKAGE.match(name):
            return Package(library=library, ecosystem=ECOSYSTEMS[m.group(1)], name=name)
    return None


# ---------------------------------------------------------------- the network (one fixed address, on a person's click)

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The request goes to the one fixed address and nowhere else: a redirect is not followed. It then comes back as
    the HTTP status it is, which the reader says plainly."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):      # noqa: ARG002, D102
        return None


def _http_transport(body: bytes, timeout: float) -> tuple[int, bytes]:
    """One POST to the source: (HTTP status, answer bytes). Raises OSError when there is no answer at all."""
    request = urllib.request.Request(SOURCE_URL, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json",
                                              "User-Agent": "advisory-reader"})      # a plain client name: nothing about who asks
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:   # noqa: S310 (a fixed https address)
            return response.status, response.read(MAX_ANSWER_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(64 * 1024)


Transport = Callable[[bytes, float], tuple[int, bytes]]


def request_body(package: Package, page_token: str | None = None) -> bytes:
    """Exactly what is sent for one package: its name and ecosystem, and the page marker the source handed back."""
    body: dict = {"package": {"name": package.name, "ecosystem": package.ecosystem}}
    if page_token:
        body["page_token"] = page_token
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


class OsvSource:
    """The public source itself. One request for each package (and each further page of its answer)."""

    key = "osv"
    words = f"{SOURCE_NAME}, a public database of published advisories"

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport

    def sends(self, packages: list[Package]) -> list[str]:
        return [p.words for p in packages]

    def answers(self, package: Package) -> list[bytes]:
        pages, token = [], None
        for _ in range(MAX_PAGES):
            try:
                status, raw = (self._transport or _http_transport)(request_body(package, token), TIMEOUT_SECONDS)
            except OSError as exc:
                raise LookupError_(f"{SOURCE_NAME} could not be reached ({exc.__class__.__name__}). Nothing was changed.") from None
            except Exception as exc:        # never the error's own words: they can hold an address or a header
                raise LookupError_(f"The request to {SOURCE_NAME} did not come back whole ({exc.__class__.__name__}). Nothing was changed.") from None
            if status != 200:
                raise LookupError_(f"{SOURCE_NAME} answered with an error (HTTP {int(status)}). Nothing was changed.")
            if len(raw) > MAX_ANSWER_BYTES:
                raise LookupError_(f"The answer of {SOURCE_NAME} about {package.words} is larger than this version takes.")
            pages.append(raw)
            token = _page_token(raw)
            if token is None:
                break
        return pages


class RecordedSource:
    """A folder of recorded answers on this computer (tests, the walks, a demo with no internet). Nothing is sent."""

    key = "recorded"

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.words = "recorded answers in a folder on this computer (nothing is sent anywhere)"

    def sends(self, packages: list[Package]) -> list[str]:
        return []

    def answers(self, package: Package) -> list[bytes]:
        path = self.folder / f"{package.key.replace('/', '_').replace(':', '_')}.json"
        try:
            if not path.is_file() or path.is_symlink():
                return []
            raw = path.read_bytes()
        except OSError:
            raise LookupError_("A recorded answer in the folder can't be opened.") from None
        if len(raw) > MAX_ANSWER_BYTES:
            raise LookupError_("A recorded answer in the folder is larger than this version takes.")
        return [raw]

    def snapshots(self) -> list[dict]:
        """Every snapshot file in the folder (the shape of research/snapshot/*/advisories.json), used as it is."""
        out = []
        try:
            files = sorted(p for p in self.folder.glob("*.json") if p.is_file() and not p.is_symlink())
        except OSError:
            return []
        for path in files:
            try:
                raw = path.read_bytes()
                data = json.loads(raw.decode("utf-8")) if len(raw) <= MAX_ANSWER_BYTES else None
            except (OSError, ValueError, RecursionError):
                continue
            if isinstance(data, dict) and data.get("schema") == SNAPSHOT_SCHEMA and isinstance(data.get("advisories"), list):
                out.append(data)
        return out


# ---------------------------------------------------------------- reading an answer (it is data: exact shape or refused)

def _load(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise LookupError_(f"The answer of {SOURCE_NAME} is not valid JSON.") from None
    if not isinstance(data, dict):
        raise LookupError_(f"The answer of {SOURCE_NAME} is not in the shape it documents.")
    return data


def _page_token(raw: bytes) -> str | None:
    token = _load(raw).get("next_page_token")
    return token if isinstance(token, str) and 0 < len(token) <= 2000 and token.isprintable() else None


def _plain(value: object, limit: int) -> str | None:
    """A field of the record as text: the publisher's own words, with nothing but control characters taken out."""
    if not isinstance(value, str):
        return None
    text = "".join(ch for ch in value if ch.isprintable() or ch in "\n\t").strip()
    return text[:limit] if text else None


def _pieces(details: str) -> list[str]:
    """The record's long text in pieces of a size the snapshot takes, cut at paragraph ends, each word for word."""
    out: list[str] = []
    for paragraph in re.split(r"\n\s*\n", details):
        paragraph = paragraph.strip()
        while paragraph:
            piece = paragraph[:MAX_EXCERPT_CHARS].strip()
            if piece:                                   # (a piece of nothing but blanks is no text of the publisher's)
                out.append(piece)
            paragraph = paragraph[MAX_EXCERPT_CHARS:]
    return out


# A publisher's one-line summary is shown as the advisory's title unless it rates the advisory: the app never says how
# serious an advisory is, so such a line is not put where a title stands (it stays among the publisher's quoted text).
_RATES = re.compile(r"(?i)\b(severity|cvss|critical|score|high[- ]risk|low[- ]risk|high[- ]impact|low[- ]impact)\b")


def _publisher(record_id: str, record: dict) -> tuple[str, str | None]:
    for prefix, name, licence in PUBLISHERS:
        if record_id.upper().startswith(prefix):
            reviewed = (record.get("database_specific") or {}).get("github_reviewed") if isinstance(record.get("database_specific"), dict) else None
            return (f"{name}, reviewed" if prefix == "GHSA-" and reviewed is True else name), licence
    return SOURCE_NAME, None


def _events(affected: dict) -> tuple[list[dict], list[str]]:
    """The version ranges and the single versions one `affected` entry of a record names, as plain text."""
    ranges: list[dict] = []
    raw_ranges, raw_versions = affected.get("ranges"), affected.get("versions")
    for r in raw_ranges if isinstance(raw_ranges, list) else []:
        if not isinstance(r, dict) or r.get("type") not in ("SEMVER", "ECOSYSTEM") or not isinstance(r.get("events"), list):
            continue        # a range of commits says nothing about a version number
        current: dict | None = None
        for event in r["events"][:200]:
            if not isinstance(event, dict):
                continue
            if isinstance(event.get("introduced"), str):
                current = {"introduced": event["introduced"][:80], "fixed": None, "last_affected": None}
                ranges.append(current)
            elif current is not None and isinstance(event.get("fixed"), str):
                current["fixed"] = event["fixed"][:80]
                current = None
            elif current is not None and isinstance(event.get("last_affected"), str):
                current["last_affected"] = event["last_affected"][:80]
                current = None
    listed = [v[:80] for v in (raw_versions if isinstance(raw_versions, list) else [])[:5000] if isinstance(v, str)]
    return ranges, listed


def read_answer(raw: bytes, package: Package, today: str) -> tuple[list[Found], int]:
    """The advisories in one answer of the source that are about this package: (those that can be used, how many
    records were left out because they are not in the documented shape). Raises LookupError_ when the answer itself
    is not what the source documents."""
    data = _load(raw)
    records = data.get("vulns", [])
    if not isinstance(records, list):
        raise LookupError_(f"The answer of {SOURCE_NAME} is not in the shape it documents.")
    found, left_out = [], 0
    for record in records:
        made = _one(record, package, today)
        if made is None:
            left_out += 1
        else:
            found.append(made)
    return found, left_out


MAX_WITHDRAWN = 200            # withdrawn records one look keeps the ids of


def withdrawn_in(raw: bytes, package: Package) -> list[dict]:
    """Sandbox research, the Watch list: the records in one answer that their publisher took back and that are about
    this package, as data: [{"record_id", "ids"}] (`ids`: the record's own id and the other ids it is known under, in
    capitals). A withdrawn record is never among what a look found; this only says that it was in the answer, so a
    weakness that was being watched can say "withdrawn by its publisher" and not merely disappear."""
    try:
        records = _load(raw).get("vulns", [])
    except LookupError_:
        return []
    out = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or not record.get("withdrawn"):
            continue
        record_id = record.get("id")
        if not isinstance(record_id, str) or not _ALIAS.match(record_id):
            continue
        raw_affected = record.get("affected")
        about = [a.get("package") for a in (raw_affected if isinstance(raw_affected, list) else []) if isinstance(a, dict)]
        if not any(isinstance(p, dict) and p.get("ecosystem") == package.ecosystem and str(p.get("name", "")).lower() == package.name.lower()
                   for p in about):
            continue
        raw_aliases = record.get("aliases")
        aliases = [a for a in (raw_aliases if isinstance(raw_aliases, list) else []) if isinstance(a, str) and _ALIAS.match(a)]
        out.append({"record_id": record_id, "ids": list(dict.fromkeys(i.upper() for i in [record_id, *aliases]))[:9]})
        if len(out) >= MAX_WITHDRAWN:
            break
    return out


def _one(record: object, package: Package, today: str) -> Found | None:
    if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not _ALIAS.match(record["id"]):
        return None
    record_id = record["id"]
    if record.get("withdrawn"):
        return None                                   # the publisher took it back
    raw_aliases, raw_published, raw_affected = record.get("aliases"), record.get("published"), record.get("affected")
    aliases = [a for a in (raw_aliases if isinstance(raw_aliases, list) else []) if isinstance(a, str) and _ALIAS.match(a)]
    cve = next((a for a in aliases if _CVE.match(a)), None)
    advisory_id = cve or record_id.upper()
    if not _ID.match(advisory_id):
        return None
    published = _STAMP.match(raw_published if isinstance(raw_published, str) else "")
    if published is None:
        return None
    ranges: list[dict] = []
    versions: list[str] = []
    for affected in raw_affected if isinstance(raw_affected, list) else []:
        about = affected.get("package") if isinstance(affected, dict) else None
        if not isinstance(about, dict) or about.get("ecosystem") != package.ecosystem or str(about.get("name", "")).lower() != package.name.lower():
            continue
        more_ranges, more_versions = _events(affected)
        ranges += more_ranges
        versions += more_versions
    ranges, versions = ranges[:MAX_RANGES], versions[:5000]
    if not ranges and not versions:
        return None                                   # it says nothing about a version of this package
    summary = _plain(record.get("summary"), 300)
    details = _plain(record.get("details"), MAX_ADVISORY_CHARS)
    excerpts = ([summary] if summary else []) + (_pieces(details) if details else [])
    if not excerpts:
        return None
    # The versions the record names, in the words of its own fields (the reading step quotes them).
    for r in ranges:
        excerpts.append(f'"introduced": "{r["introduced"]}"')
        if r["fixed"]:
            excerpts.append(f'"fixed": "{r["fixed"]}"')
        if r["last_affected"]:
            excerpts.append(f'"last_affected": "{r["last_affected"]}"')
    kept: list[str] = []
    total = 0
    for excerpt in dict.fromkeys(excerpts):
        if len(kept) >= MAX_EXCERPTS or total + len(excerpt) > MAX_ADVISORY_CHARS:
            break
        kept.append(excerpt)
        total += len(excerpt)
    publisher, licence = _publisher(record_id, record)
    # (the fingerprint is of this one record as the source sent it, written out in a fixed order)
    digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    others = [a for a in dict.fromkeys([record_id, *aliases]) if a != advisory_id and a.upper() != advisory_id][:8]
    advisory = {"id": advisory_id, "aliases": others, "package": {"name": package.library, "ecosystem": package.ecosystem},
                "published": published.group(1),
                "sources": [{"title": summary if summary and not _RATES.search(summary) else f"{publisher} record {record_id}",
                             "publisher": publisher,
                             "url": SOURCE_PAGE + record_id, "fetched_from": SOURCE_URL, "fetched": today, "sha256": digest,
                             "license": licence, "excerpts": kept}]}
    if snapshot_advisory(advisory) is None:       # (what a look keeps is always in the shape a research run takes)
        return None
    return Found(advisory=advisory, ranges=ranges, versions=versions, record_id=record_id)


# ---------------------------------------------------------------- does an advisory name a version you have?

def names_version(found: Found, version: object) -> dict:
    """What the source's ranges say about one version: {"state": "affected" | "not_affected" | "cant_tell", "fixed":
    the fixed version the range that holds it names, or None}. A version that can't be read is never guessed."""
    mine = read_version(version)
    if mine is None:
        return {"state": "cant_tell", "fixed": None}
    here = version_key(mine)
    unreadable = False
    for r in found.ranges:
        low = read_version(r["introduced"])           # ("0" reads as version 0: from the first release on)
        if low is None:
            unreadable = True
            continue
        if here < version_key(low):
            continue
        end, closed = (r["fixed"], False) if r["fixed"] else (r["last_affected"], True)
        if end is None:
            return {"state": "affected", "fixed": None}          # introduced, and no end is named
        top = read_version(end)
        if top is None:
            unreadable = True
        elif here < version_key(top) or (closed and here == version_key(top)):
            return {"state": "affected", "fixed": r["fixed"]}
    if isinstance(version, str) and version in found.versions:
        return {"state": "affected", "fixed": None}              # listed by itself, with no range that says where it ends
    return {"state": "cant_tell" if unreadable else "not_affected", "fixed": None}


_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_SOURCES = 20


def _is_text(value: object, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _is_link(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://") and len(value) <= 400 and not any(ch.isspace() for ch in value)


def snapshot_advisory(advisory: object) -> dict | None:
    """One advisory, if it is exactly what the snapshot's shape says an advisory is (the same rule the research side
    holds an inbox file to, so what a look keeps can always be handed to a research run); None otherwise. Nothing is
    changed: the publisher's quoted text stays byte for byte. The file is data: a damaged entry is left out, and it
    never breaks the page that lists it. A link must be an https address."""
    if not isinstance(advisory, dict) or set(advisory) != {"id", "aliases", "package", "published", "sources"}:
        return None
    if not isinstance(advisory["id"], str) or not _ID.match(advisory["id"]):
        return None
    aliases, package, sources = advisory["aliases"], advisory["package"], advisory["sources"]
    if not isinstance(aliases, list) or len(aliases) > 8 or not all(isinstance(x, str) and _ALIAS.match(x) for x in aliases):
        return None
    if not isinstance(package, dict) or set(package) != {"name", "ecosystem"} \
            or not all(isinstance(package[k], str) and _NAME.match(package[k]) for k in ("name", "ecosystem")):
        return None
    if not isinstance(advisory["published"], str) or not _DAY.match(advisory["published"]):
        return None
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
        return None
    total = 0
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"title", "publisher", "url", "fetched_from", "fetched", "sha256", "license", "excerpts"}:
            return None
        if not _is_text(source["title"], 300) or not _is_text(source["publisher"], 200) or not _is_link(source["url"]) \
                or not _is_link(source["fetched_from"]):
            return None
        if not isinstance(source["fetched"], str) or not _DAY.match(source["fetched"]) \
                or not isinstance(source["sha256"], str) or not _HEX64.match(source["sha256"]):
            return None
        if source["license"] is not None and not _is_text(source["license"], 100):
            return None
        excerpts = source["excerpts"]
        if not isinstance(excerpts, list) or not 1 <= len(excerpts) <= MAX_EXCERPTS or not all(_is_text(e, MAX_EXCERPT_CHARS) for e in excerpts):
            return None
        total += sum(len(e) for e in excerpts)
    if total > MAX_ADVISORY_CHARS:
        return None
    return advisory


def from_snapshot(snapshot: dict, packages: list[Package]) -> list[Found]:
    """A recorded snapshot's advisories about these libraries (their ranges are not known: the reading step reads the
    versions from the publisher's quoted text). Each is held to the snapshot's shape; one that is not is left out."""
    wanted = {p.library for p in packages}
    out = []
    for advisory in (snapshot.get("advisories") or [])[:2000]:
        made = snapshot_advisory(advisory)
        if made is not None and made["package"]["name"] in wanted:
            out.append(Found(advisory=made, ranges=[], versions=[], record_id=made["id"]))
    return out


def read_source(source, packages: list[Package], now: datetime | None = None, fits: Callable[[Found], bool] | None = None) -> dict:
    """One look: every package asked about once. Returns {"source", "sent", "asked", "found", "left_out", "cut",
    "more_pages", "not_listed"}: `found` is the usable advisories about these packages this look keeps, each once (by
    its id): first those `fits` says name a version the assessment has (worked out by the caller, on this computer),
    then the others, the newest first within each. The cut to what is kept comes after that ranking, so an older
    advisory that fits is never pushed out by newer ones that do not. `more_pages`: packages whose answer had more
    pages than this version reads. `not_listed`: how many usable advisories were read and not kept."""
    today = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    found: dict[str, Found] = {}
    asked, left_out, more_pages = [], 0, []
    withdrawn: list[dict] = []
    for package in packages:
        pages = source.answers(package)
        count = 0
        for raw in pages:
            more, bad = read_answer(raw, package, today)
            left_out += bad
            withdrawn += [{"library": package.library, **w} for w in withdrawn_in(raw, package)]
            for one in more:
                found.setdefault(one.advisory["id"], one)
                count += 1
        if pages and len(pages) >= MAX_PAGES and _page_token(pages[-1]) is not None:
            more_pages.append(package.words)
        asked.append({"library": package.library, "ecosystem": package.ecosystem, "name": package.name, "records": count,
                      "sha256": [hashlib.sha256(raw).hexdigest() for raw in pages]})
    if isinstance(source, RecordedSource):
        for snapshot in source.snapshots():
            for one in from_snapshot(snapshot, packages):
                found.setdefault(one.advisory["id"], one)
    newest = sorted(found.values(), key=lambda f: (f.advisory["published"], f.advisory["id"]), reverse=True)
    if fits is not None:
        newest.sort(key=lambda f: not fits(f))          # (a stable sort: those that fit first, each group still newest first)
    return {"source": source.key, "source_words": source.words, "sent": source.sends(packages), "asked": asked,
            "found": newest[:MAX_KEPT], "left_out": left_out, "cut": bool(more_pages) or len(newest) > MAX_KEPT,
            "more_pages": more_pages, "not_listed": max(0, len(newest) - MAX_KEPT), "withdrawn": withdrawn[:MAX_WITHDRAWN]}
