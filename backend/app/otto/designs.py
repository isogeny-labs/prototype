"""Advisory check designs: what a signed test pack carries for one advisory, and the locked test made from it.

A design is DATA. It can't carry code: it picks one building block the runner and the reviewer already know, and
names published test cases for it. In this version there is one block, "signature_cases": signatures from the
pinned Project Wycheproof file for ECDSA P-256, each with its published right answer, run on the program and on the
accept-everything control, and judged by the same rule as the Independent exam (every answer right, or Failed).

    design (in the pack)  ->  check_design()            is it a shape and a selection this version can run?
    design + one program  ->  spec_for()                the locked test for that program (kind "advisory_cases")
    a model's design note ->  compile_note()            the design it describes, or the plain reason it can't be one

Nothing here decides a result, and nothing here runs anything.
"""

from __future__ import annotations

import re

from app.canonical import sha256_hex
from app.engine import research, vectors

DESIGN_SCHEMA = "isogeny.advisory-design/1"
NOTE_SCHEMA = "isogeny.otto-design-note/1"
BLOCK = "signature_cases"
CASE_SET = "ecdsa_p256"
CONTROL = "accept_all_verifier"
RULE = "all_cases_match"
PROPOSED_BY = "isogeny.otto-pack/1"  # who proposed an advisory check: the pack, never the rule engine or the reviewer
MAX_CASES = 484
MAX_TEXT = 400
MAX_REASON = 700  # "one or two plain sentences": why no test fits, or what a fix does
_ADVISORY_ID = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,39}$")
_CASE_ID = re.compile(r"^[0-9]{1,5}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

BLOCKS: dict[str, dict] = {
    BLOCK: {
        "title": "Published signature cases",
        "what": (
            "Hands the program published ECDSA P-256 signatures (Project Wycheproof, pinned by SHA-256), one at a time, and "
            "compares its accept or reject with the published right answer."
        ),
        "fits": "A program or library that checks ECDSA P-256 signatures over SHA-256, in DER form.",
        "controls": {
            CONTROL: "A deliberately broken checker that accepts every signature. It must get every must-reject case wrong, "
            "so the selection needs at least one must-reject case."
        },
        "rule": "Passed only if every answer is right. Any wrong answer means Failed.",
        "cannot": [
            "timing or other side channels",
            "signing (only checking)",
            "any other curve, hash or signature scheme",
            "a crash that the program turns into a plain rejection",
        ],
    },
}


class DesignError(ValueError):
    """This design can't be used. str(exc) is one plain sentence."""


def _text(value: object, name: str, limit: int = MAX_TEXT) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(ch) < 32 and ch not in "\n\t" for ch in value)
    ):
        raise DesignError(f"The design's {name} is not a short piece of plain text.")
    return value.strip()


def case_index() -> dict:
    """What the published file says about its own cases: for each kind of case (flag), its published note, how many
    cases carry it, how many must be rejected, and a few of their descriptions. This is what a designer may choose from."""
    cases = vectors.load_wycheproof(CASE_SET).cases
    pin = vectors.WYCHEPROOF[CASE_SET]
    notes = _published_notes()
    kinds: dict[str, dict] = {}
    for case in cases:
        for flag in case.flags:
            kind = kinds.setdefault(flag, {"cases": 0, "must_reject": 0, "must_accept": 0, "examples": []})
            kind["cases"] += 1
            kind["must_reject" if case.expected == "invalid" else "must_accept"] += 1
            if len(kind["examples"]) < 5 and case.comment not in kind["examples"]:
                kind["examples"].append(case.comment)
    for flag, kind in kinds.items():
        note = notes.get(flag) or {}
        kind["note"] = {k: note[k] for k in ("bugType", "description", "effect", "cves") if k in note}
    return {
        "set": CASE_SET,
        "file": pin["file"],
        "sha256": pin["sha256"],
        "commit": vectors.WYCHEPROOF_COMMIT,
        "source_url": vectors.WYCHEPROOF_SOURCE_URL,
        "cases": len(cases),
        "kinds": {k: kinds[k] for k in sorted(kinds)},
    }


def _published_notes() -> dict:
    import json

    path = vectors.load_wycheproof(CASE_SET).path  # (loading checks the pin first)
    notes = json.loads(path.read_bytes()).get("notes")
    return notes if isinstance(notes, dict) else {}


def select_cases(select: object) -> list[str]:
    """The ids of the published cases a selection names: every case carrying one of its flags, plus the ids it lists.
    In file order, each once. Raises DesignError when it names a flag or an id the pinned file does not have."""
    if not isinstance(select, dict) or set(select) - {"flags", "ids"}:
        raise DesignError("The design's selection must name flags, ids or both, and nothing else.")
    flags, ids = select.get("flags", []), select.get("ids", [])
    if (
        not isinstance(flags, list)
        or not isinstance(ids, list)
        or not (flags or ids)
        or not all(isinstance(f, str) for f in flags)
        or not all(isinstance(i, str) and _CASE_ID.match(i) for i in ids)
    ):
        raise DesignError("The design's selection must name at least one flag or case id, as text.")
    cases = vectors.load_wycheproof(CASE_SET).cases
    known_flags = {flag for case in cases for flag in case.flags}
    known_ids = {case.id for case in cases}
    for flag in flags:
        if flag not in known_flags:
            raise DesignError(f"The pinned test file has no cases of the kind “{flag[:40]}”.")
    for case_id in ids:
        if case_id not in known_ids:
            raise DesignError(f"The pinned test file has no case {case_id}.")
    wanted_flags, wanted_ids = set(flags), set(ids)
    return [case.id for case in cases if case.id in wanted_ids or wanted_flags & set(case.flags)]


def _counts(ids: list[str]) -> tuple[int, int]:
    by_id = {case.id: case for case in vectors.load_wycheproof(CASE_SET).cases}
    reject = sum(1 for i in ids if by_id[i].expected == "invalid")
    accept = sum(1 for i in ids if by_id[i].expected == "valid")
    return reject, accept


def check_design(design: object) -> dict:
    """The design, if this version can run it exactly as written. Raises DesignError with one plain sentence otherwise.
    Checked every time a design is used: when a pack is read, and again when a check is added from it."""
    if not isinstance(design, dict) or design.get("schema") != DESIGN_SCHEMA:
        raise DesignError("This is not an advisory check design this version knows.")
    wanted = {"schema", "advisory", "block", "plain_name", "question", "why", "cases", "control", "rule", "model_step"}
    if set(design) != wanted:
        raise DesignError("The design has fields this version does not know, or lacks one it needs.")
    if not isinstance(design["advisory"], str) or not _ADVISORY_ID.match(design["advisory"]):
        raise DesignError("The design does not name its advisory by a plain id.")
    if design["block"] != BLOCK or design["control"] != CONTROL or design["rule"] != RULE:
        raise DesignError("The design asks for a building block, a control or a rule this version does not have.")
    _text(design["plain_name"], "plain name", 80)
    question = _text(design["question"], "question")
    _text(design["why"], "reason")
    if question.count("{program}") != 1:
        raise DesignError("The design's question must name the program once, as {program}.")
    step = design["model_step"]
    if (
        not isinstance(step, dict)
        or set(step) != {"prompt_sha256", "answer_sha256"}
        or not all(isinstance(v, str) and _HEX64.match(v) for v in step.values())
    ):
        raise DesignError("The design does not say which recorded answer it was made from.")
    cases, pin = design["cases"], vectors.WYCHEPROOF[CASE_SET]
    if not isinstance(cases, dict) or set(cases) != {
        "set",
        "file",
        "sha256",
        "commit",
        "source_url",
        "select",
        "ids",
        "must_reject",
        "must_accept",
    }:
        raise DesignError("The design's case list is not in the shape this version knows.")
    if (cases["set"], cases["file"], cases["sha256"], cases["commit"], cases["source_url"]) != (
        CASE_SET,
        pin["file"],
        pin["sha256"],
        vectors.WYCHEPROOF_COMMIT,
        vectors.WYCHEPROOF_SOURCE_URL,
    ):
        raise DesignError("The design was made for a test file other than the one pinned in this version.")
    ids = cases["ids"]
    if (
        not isinstance(ids, list)
        or not ids
        or len(ids) > MAX_CASES
        or not all(isinstance(i, str) and _CASE_ID.match(i) for i in ids)
    ):
        raise DesignError("The design names no cases, or names them in a form this version does not know.")
    if select_cases(cases["select"]) != ids:
        raise DesignError("The cases the design lists are not the ones its own selection picks from the pinned file.")
    reject, accept = _counts(ids)
    if (cases["must_reject"], cases["must_accept"]) != (reject, accept):
        raise DesignError("The design's case counts do not match the pinned file.")
    if reject < 1:
        raise DesignError(
            "The design has no case that must be rejected, so its control could never fail. It is not offered."
        )
    return design


def design_sha256(design: dict) -> str:
    return sha256_hex(design)


def title_of(design: dict) -> str:
    return f"Advisory check: {design['plain_name']} ({design['advisory']})"


def spec_for(design: dict, pack: dict, program: dict, advisory: dict) -> dict:
    """The locked test of one advisory check for one program. `pack`: {"version", "fingerprint"}; `program`: the
    engine's target for a signing program ({"component", "algorithm", "claim"}); `advisory`: what the result shows
    about where the check comes from ({"plain_name", "quote", "source": {"title", "url", "published", "checked"}}).
    Like every locked test it names no version, mode or time, so the same fingerprint is rerun on a new version."""
    check_design(design)
    cases = design["cases"]
    total, reject, accept = len(cases["ids"]), cases["must_reject"], cases["must_accept"]
    name = program["component"]
    short = vectors.WYCHEPROOF_COMMIT[:7]
    parts = f"{reject} that must be rejected" + (f" and {accept} that must be accepted" if accept else "")
    return {
        "schema": research.SPEC_SCHEMA,
        "kind": research.ADVISORY_KIND,
        "title": title_of(design),
        "card": {
            "description": (
                f"Reruns the {total} published test {'case' if total == 1 else 'cases'} that match advisory {design['advisory']} "
                f"on {name}: {parts}."
            ),
            "why": design["why"],
        },
        "question": design["question"].replace("{program}", name),
        "method": "Run the verify command once per case and compare its answer with the published one.",
        "target": {"kind": "software", "component": name, "algorithm": program["algorithm"], "claim": program["claim"]},
        "inputs": {
            "advisory": {
                "id": design["advisory"],
                "plain_name": design["plain_name"],
                "quote": advisory["quote"],
                "source": dict(advisory["source"]),
                "pack": pack["version"],
                "pack_fingerprint": pack["fingerprint"],
                "design_sha256": design_sha256(design),
            },
            "files": [
                {
                    "set": cases["set"],
                    "file": cases["file"],
                    "sha256": cases["sha256"],
                    "cases": total,
                    "used_on": "component",
                }
            ],
            "cases": list(cases["ids"]),
            "must_reject": reject,
            "must_accept": accept,
            "commit": cases["commit"],
            "source_url": cases["source_url"],
        },
        "inputs_text": [
            f"{total} {'case' if total == 1 else 'cases'} from Wycheproof testvectors_v1/{cases['file']}, pinned to commit {short}: {parts}.",
            f"Chosen for advisory {design['advisory']} by test pack {pack['version']} (design fingerprint {design_sha256(design)[:12]}), "
            "and tried on public copies before the pack was signed.",
        ],
        "control": {
            "kind": CONTROL,
            "text": "The same cases run against a deliberately broken signer, which must get every invalid case wrong.",
            "must": {"wrong_on": "every invalid case"},
        },
        "rule": {"type": RULE, "valid": "accept", "invalid": "reject", "acceptable": "not counted"},
        "rule_text": f"Passed only if all {total} answers are right. Any wrong answer means Failed.",
    }


def fits(program: dict) -> bool:
    """Does this building block fit this program of the file? One that checks ECDSA P-256 signatures."""
    return "official_vectors" in research.program_kinds(program)


# ---------------------------------------------------------------- a model's design note -> a design


def compile_note(note: object, advisory_id: str, plain_name: str, step: dict) -> dict:
    """The design a design note describes. Raises DesignError with the plain reason when the note asks for something
    this version can't run. A note that says "no test fits" is not an error: see no_test_reason()."""
    if not isinstance(note, dict) or note.get("decision") != "test":
        raise DesignError("The design note does not describe a test.")
    if set(note) - {"decision", "block", "question", "why", "select", "control", "expect"}:
        raise DesignError("The design note has fields this version does not know.")
    if note.get("block") != BLOCK:
        raise DesignError("The design note asks for a building block this version does not have.")
    if note.get("control") != CONTROL:
        raise DesignError("The design note asks for a control this building block does not have.")
    ids = select_cases(note.get("select"))
    reject, accept = _counts(ids)
    pin = vectors.WYCHEPROOF[CASE_SET]
    select = {k: list(note["select"][k]) for k in ("flags", "ids") if note["select"].get(k)}
    design = {
        "schema": DESIGN_SCHEMA,
        "advisory": advisory_id,
        "block": BLOCK,
        "plain_name": _text(plain_name, "plain name", 80),
        "question": _text(note.get("question"), "question"),
        "why": _text(note.get("why"), "reason"),
        "cases": {
            "set": CASE_SET,
            "file": pin["file"],
            "sha256": pin["sha256"],
            "commit": vectors.WYCHEPROOF_COMMIT,
            "source_url": vectors.WYCHEPROOF_SOURCE_URL,
            "select": select,
            "ids": ids,
            "must_reject": reject,
            "must_accept": accept,
        },
        "control": CONTROL,
        "rule": RULE,
        "model_step": {"prompt_sha256": step["prompt_sha256"], "answer_sha256": step["answer_sha256"]},
    }
    return check_design(design)


def no_test_reason(note: object) -> str | None:
    """The plain reason a design note gives for designing no test, or None when it does describe one."""
    if isinstance(note, dict) and note.get("decision") == "no_test":
        return _text(note.get("reason"), "reason for no test", MAX_REASON)
    return None
