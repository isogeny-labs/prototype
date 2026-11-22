"""Signed test packs (phase 5c): what crosses from Otto's research side to an installation of Evidence Lab.

A pack is DATA, like an antivirus update: advisories, for each one what Otto read in it, whether it has a test
(a design: published cases to rerun, never code) and a fix, and how each did when tried on public copies. Nothing in
a pack runs. A person installs it, and a person adds its checks to an assessment.

The file is the evidence file's envelope, {"pack": P, "fingerprint": F, "public_key": K, "signature": S}: F is the
SHA-256 of P's exact canonical bytes, S an Ed25519 signature over a fixed context line and F. A pack is taken only
when the signature holds, the signer is a key this installation trusts, the shape is exactly the one below, every
design in it can be run by this version, and it follows the pack installed before it (each pack names the
fingerprint of the one before). Anything else is refused with one plain sentence.

Trusted keys are part of the app (trusted-pack-keys.json beside this file), never read from the updates folder. A pack
built on this computer by the research command is signed with a key made here; its public half is in the data
folder and is trusted by this installation only.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.canonical import canonical_bytes, sha256_hex
from app.otto import designs

PACK_SCHEMA = "isogeny.test-pack/1"
SIGNING_CONTEXT = b"isogeny-evidence-lab/test-pack/v1\n"
KEYS_SCHEMA = "isogeny.pack-keys/1"
TRUSTED_KEYS_FILE = Path(__file__).with_name("trusted-pack-keys.json")
LOCAL_KEY_FILE = "otto-local-pack-key.pub"          # in the data folder: the public half of a key made on this computer
MAX_BYTES = 4 * 1024 * 1024
MAX_ADVISORIES = 60
TEST_STATES = ("ready", "not_offered", "none")
FIX_STATES = ("proven", "not_proven", "none")
_VERSION = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,3}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX128 = re.compile(r"^[0-9a-f]{128}$")
_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,39}$")
_RECORD = re.compile(r"^sha256:[0-9a-f]{64}$")


class PackError(ValueError):
    """This pack can't be used. str(exc) is one plain sentence."""


@dataclass(frozen=True)
class Pack:
    """One pack that passed every check."""
    pack: dict
    fingerprint: str
    public_key: str
    signature: str
    made_here: bool            # signed with the key made on this computer (a live research run), not the shipped one
    signer: str                # the trusted key's own label

    @property
    def version(self) -> str:
        return self.pack["version"]

    @property
    def envelope(self) -> dict:
        return {"pack": self.pack, "fingerprint": self.fingerprint, "public_key": self.public_key, "signature": self.signature}

    def design(self, design_sha256: str) -> dict | None:
        for test in self.pack["tests"]:
            if test["design_sha256"] == design_sha256:
                return test["design"]
        return None

    def advisory(self, advisory_id: str) -> dict | None:
        for advisory in self.pack["advisories"]:
            if advisory["id"] == advisory_id:
                return advisory
        return None


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


# ---------------------------------------------------------------- trusted keys

def _keys_in(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("schema") != KEYS_SCHEMA or not isinstance(data.get("keys"), list):
        return {}
    out = {}
    for key in data["keys"]:
        if isinstance(key, dict) and isinstance(key.get("public_key"), str) and _HEX64.match(key["public_key"]) \
                and isinstance(key.get("label"), str) and 0 < len(key["label"]) <= 200:
            out[key["public_key"]] = key["label"]
    return out


def trusted_keys(data_dir: Path | None = None) -> dict[str, tuple[str, bool]]:
    """{public key (hex): (label, made on this computer?)}: the keys shipped with the app, and this computer's own."""
    out = {key: (label, False) for key, label in _keys_in(TRUSTED_KEYS_FILE).items()}
    if data_dir is not None:
        try:
            local = (Path(data_dir) / LOCAL_KEY_FILE).read_text(encoding="ascii").strip()
        except (OSError, ValueError):
            local = ""
        if _HEX64.match(local) and local not in out:
            out[local] = ("A key made on this computer by the research command", True)
    return out


# ---------------------------------------------------------------- the shape

def _fail(text: str):
    raise PackError(text)


def _keys(value: object, wanted: set, what: str, optional: frozenset | set = frozenset()) -> dict:
    if not isinstance(value, dict) or not wanted <= set(value) or set(value) - wanted - set(optional):
        _fail(f"The pack's {what} does not have exactly the fields it must have.")
    return value   # type: ignore[return-value]


def _text(value: object, what: str, limit: int, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        _fail(f"The pack's {what} is not a short piece of text.")
    return value   # type: ignore[return-value]


def _count(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(f"The pack's {what} is not a whole number.")
    return value   # type: ignore[return-value]


def _quote(value: object, what: str) -> None:
    quote = _keys(value, {"source", "text"}, what)
    _text(quote["source"], what, 8)
    _text(quote["text"], what, 300)


def _trial(value: object, what: str, arms: tuple[str, ...]) -> None:
    if value is None:
        return
    trial = _keys(value, {"hypothesis", "decision", "outcome", "replayed", "arms"}, what)
    for name in ("hypothesis", "decision"):
        if not isinstance(trial[name], str) or not _RECORD.match(trial[name]):
            _fail(f"The pack's {what} does not name its Otto ledger entries.")
    if trial["outcome"] not in ("supported", "refuted", "inconclusive", "instrument_failure", "degenerate") or not isinstance(trial["replayed"], bool):
        _fail(f"The pack's {what} has an outcome this version does not know.")
    measured = _keys(trial["arms"], set(arms), what)
    for arm in arms:
        figures = measured[arm]
        if not isinstance(figures, dict) or not figures or len(figures) > 8 or not all(
                isinstance(k, str) and len(k) <= 30 and (isinstance(v, str) and len(v) <= 60 or isinstance(v, int) and not isinstance(v, bool))
                for k, v in figures.items()):
            _fail(f"The pack's {what} holds figures this version can't read.")


def check_pack(pack: object) -> dict:
    """The pack's content, if it is exactly what a pack must be and every design in it can be run here."""
    top = _keys(pack, {"schema", "version", "built_at", "previous", "signer", "research", "otto", "advisories", "tests"}, "content")
    if top["schema"] != PACK_SCHEMA:
        _fail("This is not a test pack this version knows.")
    if not isinstance(top["version"], str) or not _VERSION.match(top["version"]):
        _fail("The pack's version is not in the form year.month.number.")
    if not isinstance(top["built_at"], str) or not _TIME.match(top["built_at"]):
        _fail("The pack does not say when it was built.")
    if top["previous"] is not None and (not isinstance(top["previous"], str) or not _HEX64.match(top["previous"])):
        _fail("The pack does not name the pack before it by its fingerprint.")
    _text(top["signer"], "signer line", 200)
    research = _keys(top["research"], {"snapshot", "snapshot_sha256", "answers", "answers_note"}, "research part")
    if not isinstance(research["snapshot"], str) or not _DATE.match(research["snapshot"]) or research["answers"] not in ("recorded", "live", "mixed") \
            or not isinstance(research["snapshot_sha256"], str) or not _HEX64.match(research["snapshot_sha256"]):
        _fail("The pack's research part is not in the shape this version knows.")
    _text(research["answers_note"], "line about where its answers came from", 200)
    otto = _keys(top["otto"], {"repository", "commit", "version", "ledger", "scripts"}, "Otto part")
    ledger = _keys(otto["ledger"], {"height", "head", "root"}, "Otto ledger line")
    _count(ledger["height"], "Otto ledger height")
    if not all(isinstance(ledger[k], str) and _RECORD.match(ledger[k]) for k in ("head", "root")) \
            or not isinstance(otto["commit"], str) or not re.match(r"^[0-9a-f]{40}$", otto["commit"]):
        _fail("The pack's Otto part does not name a commit and a ledger head.")
    _text(otto["repository"], "Otto repository", 100)
    _text(otto["version"], "Otto version", 40)
    scripts = otto["scripts"]
    if not isinstance(scripts, dict) or not scripts or len(scripts) > 8 or not all(
            isinstance(k, str) and len(k) <= 60 and isinstance(v, str) and _HEX64.match(v) for k, v in scripts.items()):
        _fail("The pack does not give the fingerprints of the scripts Otto's harness ran.")

    tests = top["tests"]
    if not isinstance(tests, list) or len(tests) > MAX_ADVISORIES:
        _fail("The pack's tests are not a list.")
    by_hash: dict[str, dict] = {}
    for test in tests:
        entry = _keys(test, {"design", "design_sha256"}, "test")
        try:
            design = designs.check_design(entry["design"])
        except designs.DesignError as exc:
            raise PackError(f"A test in the pack can't be run by this version: {exc}") from None
        if entry["design_sha256"] != designs.design_sha256(design) or entry["design_sha256"] in by_hash:
            _fail("A test in the pack does not match its own fingerprint, or is there twice.")
        by_hash[entry["design_sha256"]] = design

    advisories = top["advisories"]
    if not isinstance(advisories, list) or not 1 <= len(advisories) <= MAX_ADVISORIES:
        _fail("The pack holds no advisories, or too many.")
    seen, used = set(), set()
    for advisory in advisories:
        a = _keys(advisory, {"id", "aliases", "package", "published", "sources", "reading", "reading_refused", "test", "fix", "steps", "ledger"}, "advisory")
        if not isinstance(a["id"], str) or not _ID.match(a["id"]) or a["id"] in seen:
            _fail("An advisory in the pack has no plain id, or is there twice.")
        seen.add(a["id"])
        what = f"advisory {a['id']}"
        if not isinstance(a["aliases"], list) or len(a["aliases"]) > 8 or not all(isinstance(x, str) and 0 < len(x) <= 40 for x in a["aliases"]):
            _fail(f"The other names of {what} are not plain text.")
        package = _keys(a["package"], {"name", "ecosystem"}, f"package of {what}")
        _text(package["name"], f"package of {what}", 60)
        _text(package["ecosystem"], f"package of {what}", 60)
        if not isinstance(a["published"], str) or not _DATE.match(a["published"]):
            _fail(f"{what.capitalize()} does not say when it was published.")
        sources = a["sources"]
        if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
            _fail(f"{what.capitalize()} names no source.")
        for source in sources:
            s = _keys(source, {"label", "title", "publisher", "url", "read_from", "fetched"}, f"source of {what}")
            _text(s["label"], f"source of {what}", 8)
            _text(s["title"], f"source of {what}", 300)
            _text(s["publisher"], f"source of {what}", 200)
            for link in (s["url"], s["read_from"]):          # the page a person would open, and the address the text was read from
                if not isinstance(link, str) or not link.startswith("https://") or len(link) > 400:
                    _fail(f"A source of {what} has no https link.")
            if not isinstance(s["fetched"], str) or not _DATE.match(s["fetched"]):
                _fail(f"A source of {what} has no date it was read.")
        reading = a["reading"]
        if reading is None:
            _text(a["reading_refused"], f"reason the reading of {what} was refused", 300)
        else:
            if a["reading_refused"] is not None:
                _fail(f"{what.capitalize()} has a reading and a refusal at once.")
            r = _keys(reading, {"plain_name", "weakness", "weakness_quote", "kind", "area", "affected", "fixed", "notes"}, f"reading of {what}")
            _text(r["plain_name"], f"plain name of {what}", 60)
            _text(r["weakness"], f"weakness of {what}", 800)
            _text(r["notes"], f"notes of {what}", 2000, empty=True)
            _text(r["kind"], f"kind of {what}", 40)
            _text(r["area"], f"area of {what}", 40)
            _quote(r["weakness_quote"], f"quote of {what}")
            affected = _keys(r["affected"], {"versions", "quote"}, f"affected versions of {what}")
            _text(affected["versions"], f"affected versions of {what}", 500)
            _quote(affected["quote"], f"quote of {what}")
            if r["fixed"] is not None:
                fixed = _keys(r["fixed"], {"version", "quote"}, f"fixed version of {what}")
                _text(fixed["version"], f"fixed version of {what}", 40)
                _quote(fixed["quote"], f"quote of {what}")
        test = _keys(a["test"], {"state", "reason", "design_sha256", "trial"}, f"test of {what}")
        if test["state"] not in TEST_STATES:
            _fail(f"The test of {what} is in a state this version does not know.")
        _text(test["reason"], f"reason for the test state of {what}", 1000)
        _trial(test["trial"], f"trial of {what}", ("reference", "affected", "fixed", "accept-all"))
        if test["state"] == "ready":
            if test["design_sha256"] not in by_hash or by_hash[test["design_sha256"]]["advisory"] != a["id"] or test["design_sha256"] in used:
                _fail(f"The test of {what} is not among the pack's tests.")
            if reading is None or test["trial"] is None or test["trial"]["outcome"] != "supported" or not test["trial"]["replayed"]:
                _fail(f"The test of {what} is offered without a trial that held on public copies.")
            used.add(test["design_sha256"])
        elif test["design_sha256"] is not None and (not isinstance(test["design_sha256"], str) or not _HEX64.match(test["design_sha256"])):
            _fail(f"The test of {what} names a design in a form this version does not know.")
        fix = _keys(a["fix"], {"state", "reason", "kind", "library", "version", "quote", "summary", "trial"}, f"fix of {what}")
        if fix["state"] not in FIX_STATES:
            _fail(f"The fix of {what} is in a state this version does not know.")
        _text(fix["reason"], f"reason for the fix state of {what}", 1000)
        _trial(fix["trial"], f"fix trial of {what}", ("affected", "fixed", "affected-again"))
        if fix["kind"] is None:
            if fix["state"] != "none" or any(fix[k] is not None for k in ("library", "version", "quote", "summary")):
                _fail(f"The fix of {what} is not in the shape this version knows.")
        else:
            if fix["kind"] != "update":
                _fail(f"The fix of {what} is of a kind this version does not know.")
            _text(fix["library"], f"library of the fix of {what}", 60)
            _text(fix["version"], f"version of the fix of {what}", 40)
            _text(fix["summary"], f"summary of the fix of {what}", 700)
            _quote(fix["quote"], f"quote of the fix of {what}")
        if fix["state"] == "proven" and (test["state"] != "ready" or fix["trial"] is None or fix["trial"]["outcome"] != "supported"
                                         or not fix["trial"]["replayed"]):
            _fail(f"The fix of {what} is called proven without a test and a trial that held on public copies.")
        steps = a["steps"]
        if not isinstance(steps, list) or len(steps) > 12:
            _fail(f"The Claude steps of {what} are not a list.")
        for step in steps:
            s = _keys(step, {"step", "source", "model", "prompt_sha256", "answer", "answer_sha256", "input_tokens", "output_tokens",
                             "cost_nano_usd", "at", "how", "outcome", "refusal", "claim"}, f"Claude step of {what}")
            if s["source"] not in ("recorded", "live") or s["outcome"] not in ("used", "refused") \
                    or not all(isinstance(s[k], str) and _HEX64.match(s[k]) for k in ("prompt_sha256", "answer_sha256")) \
                    or not isinstance(s["claim"], str) or not _RECORD.match(s["claim"]) \
                    or (s["model"] is not None and (not isinstance(s["model"], str) or len(s["model"]) > 80)):
                _fail(f"A Claude step of {what} is not in the shape this version knows.")
            _text(s["step"], f"Claude step of {what}", 40)
            _text(s["answer"], f"answer of a Claude step of {what}", 20000)
            if sha256_hex_text(s["answer"]) != s["answer_sha256"]:
                _fail(f"An answer of a Claude step of {what} does not match its fingerprint.")
            _text(s["at"], f"time of a Claude step of {what}", 40)
            _text(s["how"], f"source line of a Claude step of {what}", 300)
            if s["refusal"] is not None:
                _text(s["refusal"], f"refusal of a Claude step of {what}", 300)
            for name in ("input_tokens", "output_tokens", "cost_nano_usd"):
                _count(s[name], f"figures of a Claude step of {what}")
        entries = a["ledger"]
        if not isinstance(entries, list) or len(entries) > 200:
            _fail(f"The Otto ledger entries of {what} are not a list.")
        for entry in entries:
            e = _keys(entry, {"seq", "kind", "id", "at", "what"}, f"Otto ledger entry of {what}")
            _count(e["seq"], f"Otto ledger entry of {what}")
            if not isinstance(e["id"], str) or not _RECORD.match(e["id"]):
                _fail(f"An Otto ledger entry of {what} has no id.")
            _text(e["kind"], f"Otto ledger entry of {what}", 30)
            _text(e["at"], f"Otto ledger entry of {what}", 40)
            _text(e["what"], f"Otto ledger entry of {what}", 300)
    if used != set(by_hash):
        _fail("The pack holds a test that no advisory in it offers.")
    return top   # type: ignore[return-value]


def sha256_hex_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- reading one pack file

def read_envelope(raw: bytes, keys: dict[str, tuple[str, bool]]) -> Pack:
    """One pack from the bytes of its file. Raises PackError with a plain sentence when it can't be used."""
    if len(raw) > MAX_BYTES:
        _fail("The pack file is larger than this version takes.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise PackError("The pack file is not valid JSON.") from None
    if not isinstance(data, dict) or set(data) != {"pack", "fingerprint", "public_key", "signature"}:
        _fail("The file is not a signed test pack.")
    fingerprint, public_key, signature = data["fingerprint"], data["public_key"], data["signature"]
    if not (isinstance(fingerprint, str) and _HEX64.match(fingerprint) and isinstance(public_key, str) and _HEX64.match(public_key)
            and isinstance(signature, str) and _HEX128.match(signature)):
        _fail("The pack's fingerprint, key or signature is not in the form it must have.")
    try:
        same = sha256_hex(data["pack"]) == fingerprint and canonical_bytes(data) == raw.rstrip(b"\n")
    except (TypeError, ValueError):
        raise PackError("The pack holds values this version can't read.") from None
    if not same:
        _fail("The pack was changed after it was signed (its fingerprint does not match).")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(bytes.fromhex(signature), SIGNING_CONTEXT + fingerprint.encode("ascii"))
    except (InvalidSignature, ValueError):
        raise PackError("The pack's signature does not hold.") from None
    if public_key not in keys:
        _fail("The pack is signed by a key this installation does not trust.")
    label, made_here = keys[public_key]
    return Pack(pack=check_pack(data["pack"]), fingerprint=fingerprint, public_key=public_key, signature=signature, made_here=made_here, signer=label)


def read_file(path: Path, keys: dict[str, tuple[str, bool]]) -> Pack:
    try:
        if path.stat().st_size > MAX_BYTES:
            _fail("The pack file is larger than this version takes.")
        raw = path.read_bytes()
    except OSError:
        raise PackError("The pack file can't be opened.") from None
    return read_envelope(raw, keys)


def follows(pack: Pack, newest_installed: Pack | dict | None) -> str | None:
    """Why this pack can't be installed next, or None when it can: packs install in order, each naming the one before."""
    before = None if newest_installed is None else (newest_installed.fingerprint if isinstance(newest_installed, Pack) else newest_installed["fingerprint"])
    before_version = None if newest_installed is None else (newest_installed.version if isinstance(newest_installed, Pack) else newest_installed["version"])
    if before_version is not None and version_key(pack.version) <= version_key(before_version):
        return f"Pack {pack.version} is not newer than the installed pack {before_version}."
    if pack.pack["previous"] != before:
        if before is None:
            return f"Pack {pack.version} follows an earlier pack that is not installed. Packs install in order."
        return f"Pack {pack.version} does not follow the installed pack {before_version}. Packs install in order."
    return None


def found_in(folder: Path, keys: dict[str, tuple[str, bool]]) -> tuple[list[Pack], list[dict]]:
    """Every pack file in an updates folder: (the usable ones, oldest first; the refused ones as {"file", "reason"}).
    Only files named <version>.json are looked at. Nothing is downloaded: the folder is on this computer."""
    good, refused = [], []
    try:
        names = sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix == ".json" and _VERSION.match(p.stem))
    except OSError:
        return [], []
    for name in names[:200]:
        try:
            pack = read_file(folder / name, keys)
            if pack.version != Path(name).stem:
                raise PackError("The pack's version is not the one its file name gives.")
            good.append(pack)
        except PackError as exc:
            refused.append({"file": name, "reason": str(exc)})
    good.sort(key=lambda p: version_key(p.version))
    return good, refused
