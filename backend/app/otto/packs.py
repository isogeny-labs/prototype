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
from typing import NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.canonical import canonical_bytes, sha256_hex
from app.otto import designs

PACK_SCHEMA = "isogeny.test-pack/1"
# Sandbox research (a prototype): a pack that holds a test tried on public copies made on this computer, with the
# asking code as text. It is taken only from this computer's own key, with the switch on (see `OttoMixin.install_pack`).
PACK_SCHEMA_2 = "isogeny.test-pack/2"
SANDBOX_ARMS = re.compile(r"^(affected-b|fixed-b|more-affected-[12]|more-fixed-[12])$")
ONLY_MADE_HERE = (
    "This test pack carries code that asks a library its questions, as text. Such a pack is taken only when it was made on "
    "this computer, by its own research run."
)
NEEDS_SANDBOX = (
    "This test pack was made by Sandbox research. It can be installed only while Sandbox research is on (Settings)."
)
SIGNING_CONTEXT = b"isogeny-evidence-lab/test-pack/v1\n"
KEYS_SCHEMA = "isogeny.pack-keys/1"
TRUSTED_KEYS_FILE = Path(__file__).with_name("trusted-pack-keys.json")
LOCAL_KEY_FILE = "otto-local-pack-key.pub"  # in the data folder: the public half of a key made on this computer
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
    made_here: bool  # signed with the key made on this computer (a live research run), not the shipped one
    signer: str  # the trusted key's own label

    @property
    def version(self) -> str:
        return self.pack["version"]

    @property
    def envelope(self) -> dict:
        return {
            "pack": self.pack,
            "fingerprint": self.fingerprint,
            "public_key": self.public_key,
            "signature": self.signature,
        }

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
        if (
            isinstance(key, dict)
            and isinstance(key.get("public_key"), str)
            and _HEX64.match(key["public_key"])
            and isinstance(key.get("label"), str)
            and 0 < len(key["label"]) <= 200
        ):
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


def _fail(text: str) -> NoReturn:
    raise PackError(text)


def _keys(value: object, wanted: set, what: str, optional: frozenset | set = frozenset()) -> dict:
    if not isinstance(value, dict) or not wanted <= set(value) or set(value) - wanted - set(optional):
        _fail(f"The pack's {what} does not have exactly the fields it must have.")
    return value  # type: ignore[return-value]


def _text(value: object, what: str, limit: int, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        _fail(f"The pack's {what} is not a short piece of text.")
    return value  # type: ignore[return-value]


def _count(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(f"The pack's {what} is not a whole number.")
    return value  # type: ignore[return-value]


def _quote(value: object, what: str) -> None:
    quote = _keys(value, {"source", "text"}, what)
    _text(quote["source"], what, 8)
    _text(quote["text"], what, 300)


def _trial(value: object, what: str, arms: tuple[str, ...], more: bool = False) -> None:
    """`more`: a test tried on sandbox copies may have further parts beside the four (the second author's code on the
    two copies, and up to two further versions on each side)."""
    if value is None:
        return
    trial = _keys(value, {"hypothesis", "decision", "outcome", "replayed", "arms"}, what)
    for name in ("hypothesis", "decision"):
        if not isinstance(trial[name], str) or not _RECORD.match(trial[name]):
            _fail(f"The pack's {what} does not name its Otto ledger entries.")
    if trial["outcome"] not in (
        "supported",
        "refuted",
        "inconclusive",
        "instrument_failure",
        "degenerate",
    ) or not isinstance(trial["replayed"], bool):
        _fail(f"The pack's {what} has an outcome this version does not know.")
    extra = set()
    if more and isinstance(trial["arms"], dict):
        extra = {name for name in trial["arms"] if isinstance(name, str) and SANDBOX_ARMS.match(name)}
    measured = _keys(trial["arms"], set(arms) | extra, what)
    for arm in (*arms, *sorted(extra)):
        figures = measured[arm]
        if (
            not isinstance(figures, dict)
            or not figures
            or len(figures) > 8
            or not all(
                isinstance(k, str)
                and len(k) <= 30
                and (isinstance(v, str) and len(v) <= 60 or isinstance(v, int) and not isinstance(v, bool))
                for k, v in figures.items()
            )
        ):
            _fail(f"The pack's {what} holds figures this version can't read.")


def _sandbox(
    value: object,
    trial: object,
    ledger: object,
    what: str,
    *,
    advisory_id: str,
    ready: bool,
    design: dict | None,
    scripts: dict,
) -> None:
    """What a test tried on sandbox copies adds to its entry: the copy set (held to the exact shape of a copy set's
    record: every file with its fingerprints, the asking code as text, the image), the second author's asking code, the
    two known-answer checks, the versions, and when the trial was registered. The registration must come before the
    first run of the trial, by the pack's own list of ledger entries.

    And the parts must agree with each other (`_bears_out`): a pack whose own figures do not bear out what it says of
    its test is not taken, even though this computer made it. The verify command holds an evidence file's packs to the
    same rules, written out a second time (backend/evidence/sandbox.py): change one, change the other."""
    from app.sandbox import copies

    block = _keys(
        value,
        {"set", "second", "known", "second_known", "versions", "screen_sha256", "registered"},
        f"sandbox part of {what}",
    )
    try:
        record = copies.check_set(block["set"])
    except copies.CopyError as exc:
        raise PackError(f"The copy set of {what} is not one this version knows: {exc}") from None
    written = record["asking"]["kind"] == "written"
    second = block["second"]
    if written != (second is not None):
        _fail(
            f"The asking code of {what} was written for it, and a second author's code must stand beside it (and only then)."
        )
    if second is not None:
        s = _keys(second, {"author", "source", "sha256", "lines", "set", "image"}, f"second asking code of {what}")
        _text(s["author"], f"second author of {what}", 80)
        _text(s["source"], f"second asking code of {what}", copies.MAX_SOURCE_CHARS)
        if sha256_hex_text(s["source"]) != s["sha256"] or s["sha256"] == record["asking"]["sha256"]:
            _fail(f"The second asking code of {what} does not match its fingerprint, or is the first one over again.")
        _count(s["lines"], f"second asking code of {what}")
        _text(s["set"], f"second copy set of {what}", 16)
        _text(s["image"], f"second image of {what}", 140)
    for name in ("known", "second_known"):
        known = block[name]
        if known is None:
            if name == "known" or second is not None:
                _fail(f"The known-answer check of {what} is missing.")
            continue
        k = _keys(known, {"seed", "valid", "spoiled", "versions", "controls_refused"}, f"known-answer check of {what}")
        if (
            not isinstance(k["seed"], str)
            or not _HEX64.match(k["seed"])
            or not isinstance(k["controls_refused"], bool)
            or not isinstance(k["versions"], dict)
            or len(k["versions"]) > 8
        ):
            _fail(f"The known-answer check of {what} is not in the shape this version knows.")
        for name2 in ("valid", "spoiled"):
            _count(k[name2], f"known-answer check of {what}")
        for version, counts in k["versions"].items():
            c = _keys(counts, {"accepted_valid", "rejected_spoiled"}, f"known-answer check of {what}")
            _text(version, f"known-answer check of {what}", 60)
            _count(c["accepted_valid"], f"known-answer check of {what}")
            _count(c["rejected_spoiled"], f"known-answer check of {what}")
        if written and not k["controls_refused"]:
            _fail(f"The known-answer check of {what} did not refuse its own controls.")
    versions = _keys(
        block["versions"],
        {"affected", "fixed", "more_affected", "more_fixed", "left_out", "after_last_affected"},
        f"versions of {what}",
    )
    if not isinstance(versions["after_last_affected"], bool):
        _fail(f"The versions of {what} do not say whether the publisher named the fixed version.")
    in_set = {v["version"] for v in record["versions"]}
    for name in ("affected", "fixed"):
        if versions[name] not in in_set:
            _fail(f"The {name} version of {what} is not in its copy set.")
        for known in (block["known"], block["second_known"]):
            marks = (known or {}).get("versions", {}).get(versions[name]) if known else None
            if known is not None and (
                marks is None
                or marks["accepted_valid"] != known["valid"]
                or marks["rejected_spoiled"] != known["spoiled"]
            ):
                _fail(f"The asking code of {what} did not pass the known-answer check on its {name} version.")
    for name in ("more_affected", "more_fixed"):
        if not isinstance(versions[name], list) or len(versions[name]) > 2 or not set(versions[name]) <= in_set:
            _fail(f"The further versions of {what} are not in its copy set.")
    if not isinstance(versions["left_out"], list) or len(versions["left_out"]) > 8:
        _fail(f"The versions left out of {what} are not a list.")
    for entry in versions["left_out"]:
        e = _keys(entry, {"version", "reason"}, f"a version left out of {what}")
        _text(e["version"], f"a version left out of {what}", 60)
        _text(e["reason"], f"reason a version was left out of {what}", 300)
    if block["screen_sha256"] is not None and (
        not isinstance(block["screen_sha256"], str) or not _HEX64.match(block["screen_sha256"])
    ):
        _fail(f"The screen of the asking code of {what} is not named by its fingerprint.")
    if written and block["screen_sha256"] is None:
        _fail(f"The asking code of {what} was written for it, and the pack does not name the rules it was screened by.")
    registered = _keys(block["registered"], {"hypothesis", "at", "first_run_at", "pins"}, f"registration of {what}")
    if not isinstance(trial, dict) or registered["hypothesis"] != trial.get("hypothesis"):
        _fail(f"The registration of {what} is not of its own trial.")
    pins = registered["pins"]
    if (
        not isinstance(pins, dict)
        or not 4 <= len(pins) <= 16
        or not all(
            isinstance(k, str) and len(k) <= 120 and isinstance(v, str) and _HEX64.match(v) for k, v in pins.items()
        )
    ):
        _fail(f"The registration of {what} does not give the fingerprints of what it froze.")
    for name in ("at", "first_run_at"):
        if registered[name] is not None:
            _text(registered[name], f"registration of {what}", 40)
    # registered before the first run: by the pack's own list of ledger entries, in ledger order
    entries = [e for e in ledger if isinstance(e, dict)] if isinstance(ledger, list) else []
    place = next((e.get("seq") for e in entries if e.get("id") == registered["hypothesis"]), None)
    if place is None or not isinstance(place, int):
        _fail(f"The registration of {what} is not among its ledger entries.")
    later_registrations = sorted(
        e["seq"]
        for e in entries
        if e.get("kind") == "hypothesis" and isinstance(e.get("seq"), int) and e["seq"] > place
    )
    upto = later_registrations[0] if later_registrations else None
    earlier_runs = [e for e in entries if e.get("kind") == "run" and isinstance(e.get("seq"), int) and e["seq"] < place]
    own_runs = [
        e
        for e in entries
        if e.get("kind") == "run"
        and isinstance(e.get("seq"), int)
        and e["seq"] > place
        and (upto is None or e["seq"] < upto)
    ]
    if earlier_runs or (trial.get("outcome") == "supported" and not own_runs):
        _fail(f"The trial of {what} was not registered before its first run.")
    try:
        _bears_out(
            block,
            record,
            trial,
            entries,
            place,
            own_runs,
            what,
            advisory_id=advisory_id,
            ready=ready,
            design=design,
            scripts=scripts,
        )
    except (
        KeyError,
        TypeError,
        AttributeError,
        ValueError,
    ):  # (a part that is not in its form at all: said plainly, never an error of the program)
        raise PackError(f"The sandbox part of {what} is not in the form this version writes.") from None


def _file_pin(data: dict) -> tuple[str, str]:
    """A lab file as the research command writes it (ottolab/research._write_once): the 12 characters its name holds,
    and the SHA-256 of its bytes, which is what a registration freezes."""
    text = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    return sha256_hex(data)[:12], sha256_hex_text(text)


def _whole(figures: dict, name: str, what: str) -> int:
    value = figures.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(f"The trial of {what} holds a count that is not a whole number.")
    return value


def _bears_out(
    block: dict,
    record: dict,
    trial: dict,
    entries: list[dict],
    place: int,
    own_runs: list[dict],
    what: str,
    *,
    advisory_id: str,
    ready: bool,
    design: dict | None,
    scripts: dict,
) -> None:
    """The parts of a sandbox test's proof agree with each other.

    - Each part of the trial ran on the version the proof names for it, of the library of the copy set.
    - The registration froze what it must, and what can be worked out again from the pack is the same: the copy set's
      record, the design, and the two pinned scripts.
    - The times the proof gives for the registration and the first run are the ledger's own, and in that order.
    - A test that is offered ("ready") has the counts for it: the affected copy at least one case wrong, the fixed
      copy and every further fixed version none, every further affected version at least one, the control every case
      that must be rejected, and the second author's code the same answer on every case of both copies.
    """
    versions, registered, second, arms = block["versions"], block["registered"], block["second"], trial["arms"]
    # ---- each part ran on the version the proof names
    named = {
        "reference": versions["fixed"],
        "affected": versions["affected"],
        "fixed": versions["fixed"],
        "accept-all": versions["fixed"],
    }
    named.update({f"more-affected-{n}": v for n, v in enumerate(versions["more_affected"], start=1)})
    named.update({f"more-fixed-{n}": v for n, v in enumerate(versions["more_fixed"], start=1)})
    if second is not None:
        named.update({"affected-b": versions["affected"], "fixed-b": versions["fixed"]})
    if set(arms) != set(named):
        _fail(f"The parts of the trial of {what} are not the parts its proof names.")
    for arm, version in named.items():
        if arms[arm].get("version") != version or arms[arm].get("library") != record["library"]:
            _fail(f"A part of the trial of {what} did not run on the version its proof names.")
    # ---- what was frozen
    pins = registered["pins"]
    kinds = ["designs/", "/set-a-", "/known-a-", "/versions-", "/arms-"] + (
        ["/set-b-", "/known-b-"] if second is not None else []
    )
    if not all(sum(1 for name in pins if kind in name) == 1 for kind in kinds):
        _fail(f"The registration of {what} did not freeze everything a trial on sandbox copies rests on.")
    for script in ("trial_sandbox.py", "qualify.py"):
        if script not in pins or pins[script] != scripts.get(script):
            _fail(f"The registration of {what} did not freeze the scripts the pack says were run.")
    in_name, of_file = _file_pin(record)
    if pins.get(f"sandbox/{advisory_id}/set-a-{in_name}.json") != of_file:
        _fail(f"The copy set of {what} is not the one its registration froze.")
    if design is not None:
        in_name, of_file = _file_pin(design)
        if pins.get(f"designs/{advisory_id}-{in_name}.json") != of_file:
            _fail(f"The design of {what} is not the one its registration froze.")
    # ---- the times are the ledger's own
    at_of = {e["seq"]: e.get("at") for e in entries if isinstance(e.get("seq"), int)}
    first_run = min((e["seq"] for e in own_runs), default=None)
    if registered["at"] != at_of.get(place) or registered["first_run_at"] != (
        at_of.get(first_run) if first_run is not None else None
    ):
        _fail(f"The times the proof of {what} gives are not the times of its ledger entries.")
    # ---- an offered test has the counts for it
    if not ready:
        return
    if design is None or not own_runs:
        _fail(f"The test of {what} is offered without its design or without a run after its registration.")
    total, reject = len(design["cases"]["ids"]), int(design["cases"]["must_reject"])
    for arm in named:
        if (
            _whole(arms[arm], "total", what) != total
            or _whole(arms[arm], "right", what) + _whole(arms[arm], "wrong", what) != total
        ):
            _fail(f"A part of the trial of {what} did not answer exactly the cases of its design.")
    holds = (
        _whole(arms["reference"], "wrong", what) == 0
        and _whole(arms["affected"], "wrong", what) >= 1
        and _whole(arms["fixed"], "wrong", what) == 0
        and _whole(arms["accept-all"], "wrong", what) == reject
        and all(_whole(arms[arm], "wrong", what) >= 1 for arm in named if arm.startswith("more-affected"))
        and all(_whole(arms[arm], "wrong", what) == 0 for arm in named if arm.startswith("more-fixed"))
        and all(_whole(arms[arm], "agree", what) == total for arm in ("affected-b", "fixed-b") if arm in named)
    )
    if not holds:
        _fail(f"The counts of the trial of {what} do not bear out that its test is offered.")


def check_pack(pack: object) -> dict:
    """The pack's content, if it is exactly what a pack must be and every design in it can be run here."""
    top = _keys(
        pack,
        {"schema", "version", "built_at", "previous", "signer", "research", "otto", "advisories", "tests"},
        "content",
    )
    if top["schema"] not in (PACK_SCHEMA, PACK_SCHEMA_2):
        _fail("This is not a test pack this version knows.")
    second = (
        top["schema"] == PACK_SCHEMA_2
    )  # sandbox research: a pack of the second format may hold what a test on sandbox copies adds
    if not isinstance(top["version"], str) or not _VERSION.match(top["version"]):
        _fail("The pack's version is not in the form year.month.number.")
    if not isinstance(top["built_at"], str) or not _TIME.match(top["built_at"]):
        _fail("The pack does not say when it was built.")
    if top["previous"] is not None and (not isinstance(top["previous"], str) or not _HEX64.match(top["previous"])):
        _fail("The pack does not name the pack before it by its fingerprint.")
    _text(top["signer"], "signer line", 200)
    research = _keys(top["research"], {"snapshot", "snapshot_sha256", "answers", "answers_note"}, "research part")
    if (
        not isinstance(research["snapshot"], str)
        or not _DATE.match(research["snapshot"])
        or research["answers"] not in ("recorded", "live", "mixed")
        or not isinstance(research["snapshot_sha256"], str)
        or not _HEX64.match(research["snapshot_sha256"])
    ):
        _fail("The pack's research part is not in the shape this version knows.")
    _text(research["answers_note"], "line about where its answers came from", 200)
    otto = _keys(top["otto"], {"repository", "commit", "version", "ledger", "scripts"}, "Otto part")
    ledger = _keys(otto["ledger"], {"height", "head", "root"}, "Otto ledger line")
    _count(ledger["height"], "Otto ledger height")
    if (
        not all(isinstance(ledger[k], str) and _RECORD.match(ledger[k]) for k in ("head", "root"))
        or not isinstance(otto["commit"], str)
        or not re.match(r"^[0-9a-f]{40}$", otto["commit"])
    ):
        _fail("The pack's Otto part does not name a commit and a ledger head.")
    _text(otto["repository"], "Otto repository", 100)
    _text(otto["version"], "Otto version", 40)
    scripts = otto["scripts"]
    if (
        not isinstance(scripts, dict)
        or not scripts
        or len(scripts) > (16 if second else 8)
        or not all(
            isinstance(k, str) and len(k) <= 60 and isinstance(v, str) and _HEX64.match(v) for k, v in scripts.items()
        )
    ):
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
        a = _keys(
            advisory,
            {
                "id",
                "aliases",
                "package",
                "published",
                "sources",
                "reading",
                "reading_refused",
                "test",
                "fix",
                "steps",
                "ledger",
            },
            "advisory",
        )
        if not isinstance(a["id"], str) or not _ID.match(a["id"]) or a["id"] in seen:
            _fail("An advisory in the pack has no plain id, or is there twice.")
        seen.add(a["id"])
        what = f"advisory {a['id']}"
        if (
            not isinstance(a["aliases"], list)
            or len(a["aliases"]) > 8
            or not all(isinstance(x, str) and 0 < len(x) <= 40 for x in a["aliases"])
        ):
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
            for link in (
                s["url"],
                s["read_from"],
            ):  # the page a person would open, and the address the text was read from
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
            r = _keys(
                reading,
                {"plain_name", "weakness", "weakness_quote", "kind", "area", "affected", "fixed", "notes"},
                f"reading of {what}",
            )
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
        test = _keys(
            a["test"],
            {"state", "reason", "design_sha256", "trial"},
            f"test of {what}",
            optional={"sandbox"} if second else frozenset(),
        )
        if test["state"] not in TEST_STATES:
            _fail(f"The test of {what} is in a state this version does not know.")
        _text(test["reason"], f"reason for the test state of {what}", 1000)
        _trial(
            test["trial"], f"trial of {what}", ("reference", "affected", "fixed", "accept-all"), more="sandbox" in test
        )
        if "sandbox" in test:
            _sandbox(
                test["sandbox"],
                test["trial"],
                a["ledger"],
                what,
                advisory_id=a["id"],
                ready=test["state"] == "ready",
                design=by_hash.get(test["design_sha256"]) if isinstance(test["design_sha256"], str) else None,
                scripts=scripts,
            )
        if test["state"] == "ready":
            if (
                test["design_sha256"] not in by_hash
                or by_hash[test["design_sha256"]]["advisory"] != a["id"]
                or test["design_sha256"] in used
            ):
                _fail(f"The test of {what} is not among the pack's tests.")
            if (
                reading is None
                or test["trial"] is None
                or test["trial"]["outcome"] != "supported"
                or not test["trial"]["replayed"]
            ):
                _fail(f"The test of {what} is offered without a trial that held on public copies.")
            used.add(test["design_sha256"])
        elif test["design_sha256"] is not None and (
            not isinstance(test["design_sha256"], str) or not _HEX64.match(test["design_sha256"])
        ):
            _fail(f"The test of {what} names a design in a form this version does not know.")
        fix = _keys(
            a["fix"], {"state", "reason", "kind", "library", "version", "quote", "summary", "trial"}, f"fix of {what}"
        )
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
        if fix["state"] == "proven" and (
            test["state"] != "ready"
            or fix["trial"] is None
            or fix["trial"]["outcome"] != "supported"
            or not fix["trial"]["replayed"]
        ):
            _fail(f"The fix of {what} is called proven without a test and a trial that held on public copies.")
        steps = a["steps"]
        if not isinstance(steps, list) or len(steps) > (20 if second else 12):
            _fail(f"The Claude steps of {what} are not a list.")
        for step in steps:
            s = _keys(
                step,
                {
                    "step",
                    "source",
                    "model",
                    "prompt_sha256",
                    "answer",
                    "answer_sha256",
                    "input_tokens",
                    "output_tokens",
                    "cost_nano_usd",
                    "at",
                    "how",
                    "outcome",
                    "refusal",
                    "claim",
                },
                f"Claude step of {what}",
            )
            if (
                s["source"] not in ("recorded", "live")
                or s["outcome"] not in ("used", "refused")
                or not all(isinstance(s[k], str) and _HEX64.match(s[k]) for k in ("prompt_sha256", "answer_sha256"))
                or not isinstance(s["claim"], str)
                or not _RECORD.match(s["claim"])
                or (s["model"] is not None and (not isinstance(s["model"], str) or len(s["model"]) > 80))
            ):
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
    return top  # type: ignore[return-value]


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
    if not (
        isinstance(fingerprint, str)
        and _HEX64.match(fingerprint)
        and isinstance(public_key, str)
        and _HEX64.match(public_key)
        and isinstance(signature, str)
        and _HEX128.match(signature)
    ):
        _fail("The pack's fingerprint, key or signature is not in the form it must have.")
    try:
        same = sha256_hex(data["pack"]) == fingerprint and canonical_bytes(data) == raw.rstrip(b"\n")
    except (TypeError, ValueError):
        raise PackError("The pack holds values this version can't read.") from None
    if not same:
        _fail("The pack was changed after it was signed (its fingerprint does not match).")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), SIGNING_CONTEXT + fingerprint.encode("ascii")
        )
    except (InvalidSignature, ValueError):
        raise PackError("The pack's signature does not hold.") from None
    if public_key not in keys:
        _fail("The pack is signed by a key this installation does not trust.")
    label, made_here = keys[public_key]
    pack = check_pack(data["pack"])
    if pack["schema"] == PACK_SCHEMA_2 and not made_here:
        # A pack of the second format carries asking code. No outside party can ship code into the app this way: not
        # even a key shipped with the app signs one.
        _fail(ONLY_MADE_HERE)
    return Pack(
        pack=pack,
        fingerprint=fingerprint,
        public_key=public_key,
        signature=signature,
        made_here=made_here,
        signer=label,
    )


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
    before = (
        None
        if newest_installed is None
        else (newest_installed.fingerprint if isinstance(newest_installed, Pack) else newest_installed["fingerprint"])
    )
    before_version = (
        None
        if newest_installed is None
        else (newest_installed.version if isinstance(newest_installed, Pack) else newest_installed["version"])
    )
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
        names = sorted(
            p.name for p in folder.iterdir() if p.is_file() and p.suffix == ".json" and _VERSION.match(p.stem)
        )
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
