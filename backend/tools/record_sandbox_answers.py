"""Write the recorded answers of the sandbox demo into research/recorded (run during the build, never by the app).

    cd backend && .venv/bin/python tools/record_sandbox_answers.py [--check]

The sandbox demo (tools/research_demo.py --sandbox) shows one real advisory, CVE-2021-43572 in starkbank-ecdsa, taken
all the way with no internet and no key. Its five Claude steps replay recorded answers: the reading, the design note,
the asking code by two authors, and the publisher's fix. A recorded answer belongs to exactly one prompt (by SHA-256),
and three of these prompts hold text that lives in the repository (our asking program, the library's public files as the
recorded registry names them). So when one of those changes, this tool writes the same answers for the new prompts.

The answers below were written during the build, not through the API, and each is labelled so. They are data: every one
goes through the same checks as a live answer would (the quotes must stand in the publisher's text, the design must
select published cases, the asking code must pass the fixed screen and the known-answer check in a container), and none
decides a result.

--check only says whether research/recorded holds an answer for each of today's prompts (exit code 1 if not).
The library's public files are fetched once (tools/research_demo.py does it) and kept in data/downloads.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import REPO_ROOT  # noqa: E402
from app.otto import lookup, model  # noqa: E402
from app.sandbox import maker, registries  # noqa: E402
from ottolab import asking, prompts  # noqa: E402
from tools import research_demo  # noqa: E402

RECORDED = REPO_ROOT / "research" / "recorded"
AT = "2026-11-22T09:30:00Z"
HOW = "Recorded during the build, not through the API"
FIXED = "2.0.1"

READING = {
    "plain_name": "Zero signature accepted",
    "weakness": ("When it checks an ECDSA signature, the affected library does not check that the signature's two numbers are not zero. "
                 "A signature made of zeros is then accepted for any message, so a signature can be made up without the signing key."),
    "weakness_quote": {"source": "S1", "text": ("The `verify` function in the Stark Bank Python ECDSA library (starkbank-ecdsa) 2.0.0 fails to check "
                                               "that the signature is non-zero, which allows attackers to forge signatures on arbitrary messages.")},
    "kind": "accepts_bad_signature",
    "area": "ecdsa_signature_check",
    "affected": {"versions": "starkbank-ecdsa 2.0.0 in the publisher's text; the source's version list names every release before 2.0.1",
                 "quote": {"source": "S1", "text": "\"introduced\": \"0\""}},
    "fixed": {"version": "2.0.1", "quote": {"source": "S1", "text": "\"fixed\": \"2.0.1\""}},
    "notes": ("The text names version 2.0.0 only, while the source's version list starts at the first release (\"introduced\": \"0\") and "
              "ends before 2.0.1. The two do not say the same about releases older than 2.0.0, so the text alone does not show whether "
              "an older release has this weakness."),
}

DESIGN = {
    "decision": "test",
    "block": "signature_cases",
    "question": "Does {program} refuse an ECDSA signature whose two numbers, r and s, are zero or another value outside the allowed range?",
    "why": ("Why it matters: a checker that accepts a signature made of zeros accepts it for any message and any key, so a signature can be "
            "made up without the signing key."),
    "select": {"flags": ["InvalidSignature"], "ids": []},
    "control": "accept_all_verifier",
    "expect": ("I expect the affected version to accept case 168, the signature with r=0 and s=0, which must be rejected: the advisory says "
               "the check that the signature is not zero is missing, and the file's own note for this kind describes signatures with "
               "special values such as r=0 and s=0 that a checker without a boundary check may accept. The other cases of the kind pair "
               "zero with further values outside the allowed range, so they ask the same question from each side. The kinds left out "
               "change the encoding or the arithmetic, so a wrong answer on them could come from a different fault."),
}

FIX = {
    "fix": "update",
    "version": "2.0.1",
    "quote": {"source": "S1", "text": "\"fixed\": \"2.0.1\""},
    "summary": ("Update starkbank-ecdsa from 2.0.0 to 2.0.1, the version the source's own version list names as fixed; the publisher's text "
                "says 2.0.0 does not check that a signature is not zero."),
}

ASKING = {
    "a": {"asking_code": '''"""Asking code for starkbank-ecdsa: it passes one question to the library's own functions and hands its answer back."""
from ellipticcurve.curve import prime256v1
from ellipticcurve.ecdsa import Ecdsa
from ellipticcurve.publicKey import PublicKey
from ellipticcurve.signature import Signature

OWN_REFUSALS = ()


def check_signature(public_key, message, signature):
    key = PublicKey.fromString(public_key[1:].hex(), curve=prime256v1)
    return Ecdsa.verify(message.decode("utf-8"), Signature.fromDer(signature), key)
''',
          "notes": ("The library takes the message as text, so the message is passed decoded as UTF-8. It raises plain exceptions for "
                    "input it can't read; it has no error class of its own for a signature that is not valid, so the refusal list is "
                    "empty.")},
    "b": {"asking_code": '''"""Asking code for starkbank-ecdsa (second author): one question, passed on to the library, and its own answer back."""
from ellipticcurve import Ecdsa, PublicKey, Signature
from ellipticcurve.curve import p256

OWN_REFUSALS = ()


def check_signature(public_key, message, signature):
    point = PublicKey.fromString("00" + public_key.hex(), curve=p256)
    parsed = Signature.fromDer(signature)
    return Ecdsa.verify(message=str(message, "utf-8"), signature=parsed, publicKey=point)
''',
          "notes": ("The public key is passed in the library's own long form, which starts with 0004; the library takes that start off "
                    "itself. The message is passed as UTF-8 text because the library's verify takes text.")},
}


def advisory() -> dict:
    """The advisory exactly as a look at the demo's recorded source (day 2: the record as published) gives it."""
    with tempfile.TemporaryDirectory(prefix="record-sandbox-") as folder:
        source = lookup.RecordedSource(research_demo.sandbox_source(Path(folder), 2))
        package = lookup.Package(library=research_demo.SANDBOX_LIBRARY, ecosystem="PyPI", name=research_demo.SANDBOX_LIBRARY)
        found = lookup.read_source(source, [package])["found"]
    return next(f.advisory for f in found if research_demo.SANDBOX_ADVISORY in (f.record_id, *f.advisory["aliases"]))


def asking_prompts() -> dict[str, str]:
    """The two authors' prompts, built as the research step builds them: from the library's own public files."""
    with tempfile.TemporaryDirectory(prefix="record-sandbox-") as folder:
        registry = research_demo.sandbox_registry(Path(folder) / "registry")
        if registry is None:
            raise SystemExit("The library's public files could not be had (files.pythonhosted.org). Nothing was written.")
        tree, readme, _ = maker.library_files(Path(folder) / "store", registries.RecordedRegistry(registry), "pypi",
                                              research_demo.SANDBOX_LIBRARY, FIXED)
    template = (maker.TEMPLATES / "python" / maker.LANGUAGE_FILES["python"][0]).read_text(encoding="utf-8")
    material = asking.material(tree, readme, "python")
    return {author: asking.prompt(library=research_demo.SANDBOX_LIBRARY, package=research_demo.SANDBOX_LIBRARY, registry_words="PyPI",
                                  language="python", template=template, library_material=material, author=author)
            for author in asking.AUTHORS}


def answers() -> list[tuple[str, str, str]]:
    """(step, prompt, answer) for the five steps, each answer checked the way the research step checks it."""
    adv = advisory()
    out = []
    reading_answer = json.dumps(READING, indent=2, ensure_ascii=False) + "\n"
    reading = prompts.check_reading(reading_answer, adv)
    out.append(("read_advisory", prompts.read_advisory_prompt(adv), reading_answer))
    design_answer = json.dumps(DESIGN, indent=2, ensure_ascii=False) + "\n"
    prompts.check_design_note(design_answer, adv, reading, {"prompt_sha256": "0" * 64, "answer_sha256": "0" * 64})
    out.append(("design_test", prompts.design_test_prompt(adv, reading), design_answer))
    fix_answer = json.dumps(FIX, indent=2, ensure_ascii=False) + "\n"
    prompts.check_fix(fix_answer, adv)
    out.append(("propose_fix", prompts.propose_fix_prompt(adv, reading), fix_answer))
    for author, text in asking_prompts().items():
        answer = json.dumps(ASKING[author], indent=2, ensure_ascii=False) + "\n"
        asking.check_answer(answer, "python", {"ellipticcurve"})
        out.append(("write_wrapper", text, answer))
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    missing = 0
    made = answers()
    for step, prompt, answer in made:
        have = model.read_recorded(model.recorded_path(RECORDED, step, model.sha256_text(prompt)))
        if have is not None and have["prompt"] == prompt and have["answer"] == answer:
            print(f"there      {step}  {model.sha256_text(prompt)[:16]}")
        elif "--check" in args:
            missing += 1
            print(f"MISSING    {step}  {model.sha256_text(prompt)[:16]}")
        else:
            path = model.write_recorded(RECORDED, step, prompt, answer, AT, HOW)
            print(f"written    {step}  {path.name}")
    # An answer of this demo that stands under a prompt nobody asks any more (a text of ours changed since) is taken away:
    # the same answer stands under today's prompt, and a stale file would only look like one more recorded answer.
    current = {(step, model.sha256_text(prompt)) for step, prompt, _ in made}
    mine = {answer for _, _, answer in made}
    stale = []
    for path in sorted(RECORDED.glob("*.json")):
        data = model.read_recorded(path)
        if data is not None and data["answer"] in mine and (data["step"], data["prompt_sha256"]) not in current:
            stale.append(path)
    for path in stale:
        if "--check" in args:
            print(f"STALE      {path.name}")
        else:
            path.unlink()
            print(f"removed    {path.name}  (its prompt is no longer asked)")
    if missing or (stale and "--check" in args):
        print(f"{missing} of the sandbox demo's prompts have no recorded answer, and {len(stale)} recorded {'answer stands' if len(stale) == 1 else 'answers stand'} "
              "under a prompt that is no longer asked. Run this tool without --check.")
    return 1 if missing or (stale and "--check" in args) else 0


if __name__ == "__main__":
    sys.exit(main())
