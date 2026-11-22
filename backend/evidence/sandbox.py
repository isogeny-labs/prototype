"""The sandbox part of a test pack in an evidence file (sandbox research, a prototype), checked by the verify command.

A pack of the second format carries, for a test that was tried on sandbox copies, the copy set (every file with its
fingerprints), both pieces of asking code as text, both known-answer checks and the registration of the trial. This
module reads that as data and checks it apart from the app's own pack reader (`app/otto/packs.py`); the rules are
written out a second time here on purpose. Nothing a pack holds is run: the asking code is text, and it stays text.

  1. A pack that carries asking code is not signed by a key shipped with the app. It is only ever made on the
     computer that uses it, so a shipped key under one would mean the pack did not come about the way it must.
  2. Each piece of asking code matches its SHA-256, and the second author's code is not the first one over again.
  3. The copy set's id is the fingerprint of its content, and its image is named after that id. So the image name a
     run record holds names exactly these files and this asking code.
  4. Every file's fingerprint is the registry's own, where the registry gives a SHA-256.
  5. The trial's own counts bear out what the pack says of the test. "Ready" only if the affected copy got at least
     one case wrong, the fixed copy and every further fixed version none, the control every case that must be
     rejected, every further affected version at least one, and the second author's code handed back the same answer
     as the first on every case of both copies.
  6. The asking code passed the known-answer check on the affected and on the fixed version, and the check refused
     its own two dummy controls.
  7. The registration is earlier in the pack's own list of ledger entries than the first run of the trial, and it
     froze what it must: the design, each copy set, each known-answer file and the two pinned scripts.

What can't be checked from a file: that the bytes on the registry were what the publisher meant (the first fetch
trusts the registry), and that the image on the computer that made the pack held those files. docs/LIMITS.md says so.
"""
from __future__ import annotations

import hashlib
import re

from app.canonical import canonical_bytes

PACK_SCHEMA_2 = "isogeny.test-pack/2"
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_ARM = re.compile(r"\A(affected-b|fixed-b|more-affected-[12]|more-fixed-[12])\Z")
SCRIPTS = ("trial_sandbox.py", "qualify.py")


class SandboxProblem(Exception):
    """A pack's sandbox part does not hold. str(exc) is one plain sentence, safe to print."""


def _plain(value: object, limit: int = 80) -> str:
    text = " ".join("".join(ch if ch.isprintable() else "?" for ch in str(value)).split())
    return text if len(text) <= limit else text[:limit] + "..."


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content(record: dict) -> dict:
    """What a copy set's id is the fingerprint of (written out a second time; `app/sandbox/copies.py` has the first)."""
    return {"library": record["library"], "registry": record["registry"], "package": record["package"], "language": record["language"],
            "versions": [{"version": v["version"], "files": [{"file": f["file"], "sha256": f["sha256"]} for f in v["files"]],
                          "tree_sha256": v["tree_sha256"]} for v in record["versions"]],
            "asking": {"kind": record["asking"]["kind"], "sha256": record["asking"]["sha256"], "template_sha256": record["asking"]["template_sha256"]},
            "harness_sha256": record["harness_sha256"], "base_images": dict(record["base_images"])}


def _slug(library: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", library.lower()).strip("-.") or "library"


def _n(arm: dict, name: str) -> int:
    value = arm.get(name) if isinstance(arm, dict) else None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SandboxProblem("a trial on sandbox copies holds a count that is not a whole number.")
    return value


def _one(advisory: dict, design: dict | None) -> None:
    what = f"the test for {_plain(advisory.get('id'), 40)}"
    test = advisory["test"]
    block, trial = test["sandbox"], test.get("trial")
    try:
        record, versions, registered = block["set"], block["versions"], block["registered"]
        asking, second = record["asking"], block["second"]
        # 2. the asking code
        if _sha_text(asking["source"]) != asking["sha256"]:
            raise SandboxProblem(f"the asking code of {what} does not match its fingerprint.")
        written = asking["kind"] == "written"
        if written != (second is not None):
            raise SandboxProblem(f"the asking code of {what} was written for it, and a second author's code must stand beside it (and only then).")
        if second is not None and (_sha_text(second["source"]) != second["sha256"] or second["sha256"] == asking["sha256"]):
            raise SandboxProblem(f"the second asking code of {what} does not match its fingerprint, or is the first one over again.")
        # 3. the copy set is named by the fingerprint of its content
        the_id = hashlib.sha256(canonical_bytes(_content(record))).hexdigest()[:16]
        if record["id"] != the_id or record["image"]["tag"] != f"evidence-lab-sandbox-{_slug(record['library'])}:{the_id}":
            raise SandboxProblem(f"the copy set of {what} is not named by the fingerprint of its content.")
        # 4. every file's fingerprint is the registry's own
        for version in record["versions"]:
            for f in version["files"]:
                given = str(f["registry_fingerprint"])
                if not _HEX64.match(str(f["sha256"])) or (given.startswith("sha256:") and given != "sha256:" + f["sha256"]) \
                        or not given.startswith(("sha256:", "sha512:")):
                    raise SandboxProblem(f"a file of a public copy of {what} does not carry the registry's own fingerprint.")
        in_set = {v["version"] for v in record["versions"]}
        affected, fixed = versions["affected"], versions["fixed"]
        if not {affected, fixed, *versions["more_affected"], *versions["more_fixed"]} <= in_set:
            raise SandboxProblem(f"a version {what} was tried on is not in its copy set.")
        # 6. the known-answer check
        for known in (block["known"], block["second_known"]):
            if known is None:
                if known is block["known"] or second is not None:
                    raise SandboxProblem(f"the known-answer check of {what} is missing.")
                continue
            for version in (affected, fixed):
                marks = known["versions"].get(version) or {}
                if marks.get("accepted_valid") != known["valid"] or marks.get("rejected_spoiled") != known["spoiled"] or not known["valid"]:
                    raise SandboxProblem(f"the asking code of {what} did not pass the known-answer check on {_plain(version, 30)}.")
            if written and known.get("controls_refused") is not True:
                raise SandboxProblem(f"the known-answer check of {what} did not refuse its own two controls.")
        # 7. registered before the first run, with everything frozen
        if not isinstance(trial, dict) or registered["hypothesis"] != trial.get("hypothesis"):
            raise SandboxProblem(f"the registration of {what} is not of its own trial.")
        pins = registered["pins"]
        if not isinstance(pins, dict) or not all(isinstance(k, str) and isinstance(v, str) and _HEX64.match(v) for k, v in pins.items()):
            raise SandboxProblem(f"the registration of {what} does not give the fingerprints of what it froze.")
        needed = ["designs/", "/set-a-", "/known-a-", "/versions-", "/arms-"] + (["/set-b-", "/known-b-"] if second is not None else [])
        if not all(script in pins for script in SCRIPTS) or not all(any(part in name for name in pins) for part in needed):
            raise SandboxProblem(f"the registration of {what} did not freeze everything a trial on sandbox copies rests on.")
        entries = [e for e in advisory.get("ledger") or [] if isinstance(e, dict) and isinstance(e.get("seq"), int)]
        place = next((e["seq"] for e in entries if e.get("id") == registered["hypothesis"] and e.get("kind") == "hypothesis"), None)
        if place is None:
            raise SandboxProblem(f"the registration of {what} is not among its ledger entries.")
        later = sorted(e["seq"] for e in entries if e.get("kind") == "hypothesis" and e["seq"] > place)
        runs = [e["seq"] for e in entries if e.get("kind") == "run" and e["seq"] > place and (not later or e["seq"] < later[0])]
        if any(e.get("kind") == "run" and e["seq"] < place for e in entries):
            raise SandboxProblem(f"a trial run of {what} stands in the ledger before the trial was registered.")
        # 5. the counts bear out what the pack says of the test
        arms = trial["arms"]
        extra = sorted(name for name in arms if _ARM.match(str(name)))
        if test["state"] == "ready":
            if design is None or not runs:
                raise SandboxProblem(f"{what} is offered without its design or without a run after its registration.")
            total, reject = len(design["cases"]["ids"]), int(design["cases"]["must_reject"])
            for name in ("reference", "affected", "fixed", "accept-all", *extra):
                if _n(arms[name], "total") != total or _n(arms[name], "right") + _n(arms[name], "wrong") != total:
                    raise SandboxProblem(f"a part of the trial of {what} did not answer exactly the cases of its design.")
            ok = (_n(arms["reference"], "wrong") == 0 and _n(arms["affected"], "wrong") >= 1 and _n(arms["fixed"], "wrong") == 0
                  and _n(arms["accept-all"], "wrong") == reject)
            ok = ok and all(_n(arms[name], "wrong") >= 1 for name in extra if name.startswith("more-affected"))
            ok = ok and all(_n(arms[name], "wrong") == 0 for name in extra if name.startswith("more-fixed"))
            if second is not None:
                ok = ok and all(name in arms and _n(arms[name], "agree") == total for name in ("affected-b", "fixed-b"))
            more = len(versions["more_affected"]) + len(versions["more_fixed"]) + (2 if second is not None else 0)
            if not ok or len(extra) != more or trial.get("outcome") != "supported" or trial.get("replayed") is not True:
                raise SandboxProblem(f"the counts of the trial of {what} do not bear out that it is offered.")
    except (KeyError, TypeError, AttributeError, ValueError):
        raise SandboxProblem(f"the sandbox part of {what} is not in the form this version writes.") from None


_IMAGE = re.compile(r"evidence-lab-sandbox-[a-z0-9][a-z0-9._-]{0,80}:[0-9a-f]{16}")


def sandbox_images(value: object) -> set[str]:
    """Every sandbox image a run record names (in the command it ran): found without recursion, as text."""
    found: set[str] = set()
    todo = [value]
    while todo:
        item = todo.pop()
        if isinstance(item, str):
            found.update(_IMAGE.findall(item))
        elif isinstance(item, dict):
            todo.extend(item.values())
        elif isinstance(item, list):
            todo.extend(item)
    return found


def check_runs(runs: list[dict], envelopes: list[dict]) -> list[str]:
    """Every run in the file that ran in a sandbox image: the image is named after a copy set, and a test pack in the
    file must hold that copy set with the version that ran. So the file itself says which public files and which asking
    code stood behind the run. Raises SandboxProblem otherwise."""
    sets: dict[str, dict] = {}
    for envelope in envelopes:
        pack = envelope.get("pack") if isinstance(envelope, dict) else None
        advisories = pack.get("advisories") if isinstance(pack, dict) and pack.get("schema") == PACK_SCHEMA_2 else None
        for advisory in advisories if isinstance(advisories, list) else []:
            test = advisory.get("test") if isinstance(advisory, dict) else None
            block = test.get("sandbox") if isinstance(test, dict) else None
            record = block.get("set") if isinstance(block, dict) else None
            if not isinstance(record, dict):
                continue
            image = record.get("image")
            if isinstance(image, dict) and isinstance(image.get("tag"), str):
                sets[image["tag"]] = record
    counted = 0
    for run in runs:
        if not isinstance(run, dict):
            continue
        inner = run.get("record")
        record = inner if isinstance(inner, dict) else run
        images = sandbox_images(record)
        if not images:
            continue
        named = record.get("component")
        component = named if isinstance(named, dict) else {}
        ran = (component.get("name"), component.get("version"))
        for image in images:
            described = sets.get(image)
            if described is None:
                raise SandboxProblem(f"a run in the file ran in the sandbox image {_plain(image, 120)}, and no test pack in the file says what "
                                     "that image holds.")
            held = described.get("versions")
            versions = [v.get("version") for v in held if isinstance(v, dict)] if isinstance(held, list) else []
            if not isinstance(ran[0], str) or not isinstance(ran[1], str) or ran[0] != described.get("library") or ran[1] not in versions:
                raise SandboxProblem(f"a run in the file ran in the sandbox image {_plain(image, 120)}, which does not hold the library version "
                                     "the run names.")
        counted += 1
    if not counted:
        return []
    return [f"Sandbox research: {counted} {'run' if counted == 1 else 'runs'} on a sandbox copy, each in an image named after a copy set that a "
            "test pack in the file describes, file by file."]


def check_packs(envelopes: list[dict], shipped_keys: set[str]) -> list[str]:
    """Every pack of the second format among these (each already whole, with a signature that holds). Returns the
    lines to print; raises SandboxProblem with the first thing that does not hold."""
    packs = tests = written = 0
    for envelope in envelopes:
        pack = envelope.get("pack") if isinstance(envelope, dict) else None
        if not isinstance(pack, dict) or pack.get("schema") != PACK_SCHEMA_2:
            continue
        packs += 1
        if envelope.get("public_key") in shipped_keys:
            raise SandboxProblem(f"test pack {_plain(pack.get('version'), 40)} carries asking code and is signed by a key shipped with the app. "
                                 "Such a pack is only ever made on the computer that uses it.")
        designs = {t.get("design_sha256"): t.get("design") for t in pack.get("tests") or [] if isinstance(t, dict)}
        for advisory in pack.get("advisories") or []:
            test = advisory.get("test") if isinstance(advisory, dict) else None
            if not isinstance(test, dict) or "sandbox" not in test:
                continue
            _one(advisory, designs.get(test.get("design_sha256")))
            tests += 1
            written += 1 if ((test["sandbox"].get("set") or {}).get("asking") or {}).get("kind") == "written" else 0
    if not packs:
        return []
    return [f"Sandbox research: {packs} test {'pack' if packs == 1 else 'packs'} made on the computer that used "
            f"{'it' if packs == 1 else 'them'}, with {tests} {'test' if tests == 1 else 'tests'} tried on sandbox copies"
            + (f" ({written} with asking code written for the library, each beside a second author's version that agreed on every case)" if written else "")
            + ": each copy set named by the fingerprint of its content, every file with the registry's own fingerprint, each trial "
              "registered before its first run, and its counts bearing out what the pack says."]
