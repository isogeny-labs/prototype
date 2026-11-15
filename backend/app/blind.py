"""The blind test (phase 4c: designed and rehearsed, not yet run on a real case). See docs/BLIND-TEST.md.

    cd backend && .venv/bin/python -m app.blind seal    expected.json
    cd backend && .venv/bin/python -m app.blind run     <case>
    cd backend && .venv/bin/python -m app.blind reveal  <case> expected.json

A cryptographer holds a library version with a bug they found. They write down what they expect the tests to
show (expected.json, kept private) and SEAL it: only its SHA-256 goes into demo/blind/<case>/seal.json, together
with a fingerprint of the tests as they stand. The build then adds the library like any real library, without
being told the bug. RUN puts it through every test that fits, by the same path as the buttons, and refuses if a
test or a rule has changed since the seal. REVEAL checks that the file handed over is the sealed one and lists,
test by test: caught, missed, or found something that was not listed. A miss is written down as a miss.

Nothing here decides a test result: results come from the tests and the reviewer, as everywhere."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import components, research
from .config import COMPONENTS_DIR, DEMO_DIR, REPO_ROOT, VECTORS_DIR, load_settings
from .real_libraries import REAL_DIR

BLIND_DIR = DEMO_DIR / "blind"
APP_DIR = Path(__file__).resolve().parent
# What may not change between the seal and the run: every file of the app (the code that designs, runs, carries, judges
# and words a result), the harness and its controls, the controls of the post-quantum exams, and every test-set file.
# The one app file that may change is real_libraries.py, where the new library's version and pins go; with its own
# wrapper folder under demo/real-libraries/, that is all adding a library needs.
NOT_FROZEN = ("real_libraries.py",)
FROZEN_CONTROLS = ("openssl/pq_controls.py", "openssl/openssl_adapter.py")   # the exams' broken copies wrap this wrapper
RESULTS = ("Passed", "Failed")
RESULT_OF_CODE = {"passed": "Passed", "failed": "Failed"}   # the reviewer's own verdict, not the words on the screen
MIN_SALT = 32


class BlindError(Exception):
    """Said to the person in plain words; the command ends with exit code 1."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_fingerprint() -> str:
    """One SHA-256 over every file that must stay as it is between the seal and the run."""
    digest = hashlib.sha256()
    files = sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts and p.relative_to(APP_DIR).as_posix() not in NOT_FROZEN)
    files += [REAL_DIR / name for name in FROZEN_CONTROLS]
    files += sorted(p for folder in (COMPONENTS_DIR / "harness", COMPONENTS_DIR / "controls", VECTORS_DIR)
                    for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for path in files:
        digest.update(path.relative_to(REPO_ROOT).as_posix().encode() + b"\0" + _sha256_file(path).encode() + b"\n")
    return digest.hexdigest()


def app_commit() -> str | None:
    """The commit this copy of the app is at, read from the repository's own files (no git program needed). None if unknown."""
    try:
        head = (REPO_ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head or None
        ref = REPO_ROOT / ".git" / head[5:]
        if ref.is_file():
            return ref.read_text(encoding="utf-8").strip()
        for line in (REPO_ROOT / ".git" / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + head[5:]):
                return line.split(" ", 1)[0]
    except OSError:
        pass
    return None


def _claims(library: dict) -> list[dict]:
    kind = "key_exchange" if library["algorithm"] == research.PQ_KEY_EXCHANGE else "signature_algorithm"
    return [{"ref": "blind-1", "location": f"{library['name']} {library['version']}", "location_kind": "software", "kind": kind,
             "claimed_value": library["algorithm"],
             "detail": {"component": library["name"], "version": library["version"], "algorithm": library["algorithm"]}}]


def test_fingerprints(library: dict) -> dict[str, str]:
    """{kind of test: fingerprint of the test as it would be locked for this library}. Needs no registration: a test is
    designed from the claim alone."""
    from .canonical import canonical_bytes
    engine = research.RuleEngine()
    return {spec["kind"]: hashlib.sha256(canonical_bytes(spec)).hexdigest() for spec in engine.propose_tests(_claims(library))["tests"]}


def read_expected(path: Path) -> tuple[dict, str]:
    """The cryptographer's file, checked for shape. Returns (its content, its SHA-256)."""
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except OSError:
        raise BlindError(f"The file {path.name} could not be read.") from None
    except ValueError:
        raise BlindError(f"The file {path.name} is not valid JSON.") from None
    library = data.get("library") if isinstance(data, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("case"), str) or not data["case"].replace("-", "").isalnum():
        raise BlindError('The file needs a "case" name made of letters, digits and hyphens.')
    if not isinstance(library, dict) or not all(isinstance(library.get(k), str) and library[k] for k in ("name", "version", "algorithm")):
        raise BlindError('The file needs "library": {"name", "version", "algorithm"}.')
    expect = data.get("expect")
    if not isinstance(expect, list) or not expect or not all(
            isinstance(e, dict) and e.get("test") in research.TITLES and e.get("result") in RESULTS
            and isinstance(e.get("wrong_cases", []), list) for e in expect):
        raise BlindError(f'The file needs "expect": a list of {{"test": one of {", ".join(sorted(research.SOFTWARE_TEST_KINDS))}, '
                         f'"result": "Passed" or "Failed", "wrong_cases": [...] (optional)}}.')
    if not isinstance(data.get("salt"), str) or len(data["salt"]) < MIN_SALT:
        raise BlindError(f'The file needs a "salt" of at least {MIN_SALT} random characters, so its fingerprint can\'t be guessed.')
    return data, hashlib.sha256(raw).hexdigest()


def seal(expected_file: Path, folder: Path = BLIND_DIR, say=print) -> int:
    data, digest = read_expected(expected_file)
    target = folder / data["case"] / "seal.json"
    if target.exists():
        raise BlindError(f"The case {data['case']} is already sealed. A seal is never replaced: use another case name.")
    fingerprints = test_fingerprints(data["library"])
    if not fingerprints:
        raise BlindError("No test in this version fits that library and algorithm, so there is nothing to seal against.")
    record = {"schema": "isogeny.blind-seal/1", "case": data["case"], "library": data["library"], "expected_sha256": digest,
              "sealed_at": _now(), "app_commit": app_commit(), "frozen_sha256": frozen_fingerprint(), "tests": fingerprints,
              "note": "Only the fingerprint of the expected result is here. The file itself stays with the person who wrote it."}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    say(f"Sealed case {data['case']}: {target.relative_to(folder.parent) if folder.parent in target.parents else target}")
    say(f"  SHA-256 of your file: {digest}")
    say(f"  tests frozen: {', '.join(research.TITLES[k] for k in fingerprints)}")
    say("Commit seal.json now, before the library is added. Keep your file private until the reveal.")
    return 0


def _read_seal(case: str, folder: Path) -> dict:
    try:
        return json.loads((folder / case / "seal.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BlindError(f"There is no readable seal for case {case}.") from None


def run(case: str, folder: Path = BLIND_DIR, say=print, settings=None) -> int:
    from .lab import Lab
    sealed = _read_seal(case, folder)
    library = sealed["library"]
    if frozen_fingerprint() != sealed["frozen_sha256"] or test_fingerprints(library) != sealed["tests"]:
        raise BlindError("A test, a rule, the harness or a test-set file has changed since this case was sealed, so the run was "
                         "refused. Nothing may be tuned between the seal and the run.")
    if components.kind_of(library["name"], library["version"]) is None:
        raise BlindError(f"{library['name']} {library['version']} is not registered yet. Add it like any real library first "
                         "(docs/BLIND-TEST.md, step 3), without changing any test.")
    csv = f"location,type,claim,value\n{library['name']} {library['version']},software," \
          f"{'key_exchange' if library['algorithm'] == research.PQ_KEY_EXCHANGE else 'signature_algorithm'},{library['algorithm']}\n"
    out = folder / case
    with tempfile.TemporaryDirectory(prefix="evidence-lab-blind-") as scratch:
        import dataclasses
        lab = Lab(dataclasses.replace(settings or load_settings(), data_dir=Path(scratch) / "data"), allow_external_demo_server=True)
        lab.start()
        try:
            imp = lab.import_file(f"blind-{case}.csv", csv.encode())
            verify = [{"claim": r["claim"]["text"], "result": r["result"], "summary": r["summary"]} for r in lab.verify(imp["id"])["results"]]
            plan = lab.ensure_plan(imp["id"])
            lab.run_all(plan["id"])
            lab.wait_until_idle(plan["id"], 1500.0)
            results = []
            for row in lab.lab_view(plan["id"])["rows"]:
                shown = row["result"]
                verdict = _detail(lab, shown)
                code = _code(lab, shown)
                results.append({"test": row["kind"], "title": row["title"], "code": code,
                                "result": (RESULT_OF_CODE.get(code) or shown["label"]) if shown else None,
                                "plain": shown["plain"] if shown else None, "control": shown["control"]["outcome"] if shown else None,
                                "wrong_cases": [str(w.get("id")) for w in verdict.get("wrong") or []],
                                "also_noticed": list(shown.get("also_noticed") or []) if shown else []})
            export = lab.export_evidence(plan["id"])
            _, evidence, _ = lab.evidence_file(export["id"], "json")
            mode = lab.mode.name
        finally:
            lab.stop()
    (out / "evidence.json").write_bytes(evidence)
    record = {"schema": "isogeny.blind-run/1", "case": case, "library": library, "ran_at": _now(), "mode": mode, "app_commit": app_commit(),
              "frozen_sha256": sealed["frozen_sha256"], "verify": verify, "results": results,
              "evidence_file": "evidence.json", "evidence_sha256": hashlib.sha256(evidence).hexdigest()}
    (out / "run.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    for r in results:
        say(f"  {r['title']}: {r['result']}" + (f" (wrong: {', '.join(r['wrong_cases'])})" if r["wrong_cases"] else ""))
    say(f"Run of case {case} saved: run.json and the signed evidence.json. Commit both, then ask for the reveal.")
    return 0


def _code(lab, shown: dict | None) -> str | None:
    """The reviewer's own verdict for a shown result (None when the shown result is no longer that verdict)."""
    from sqlalchemy import select
    from .db import ReviewRow
    if not shown:
        return None
    with lab.db() as db:
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == shown["run_id"])).first()
    return review.code if review is not None and review.code == shown["code"] else None


def _detail(lab, shown: dict | None) -> dict:
    from sqlalchemy import select
    from .db import ReviewRow
    if not shown:
        return {}
    with lab.db() as db:
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == shown["run_id"])).first()
    return dict(review.detail or {}) if review is not None and review.code == shown["code"] else {}


def compare(expected: dict, ran: dict) -> list[dict]:
    """Test by test: caught, missed, agreed (both say Passed), or found something that was not listed. Pure."""
    got = {r["test"]: r for r in ran.get("results") or []}
    lines = []
    for want in expected["expect"]:
        mine = got.get(want["test"])
        wanted_cases = [str(c) for c in want.get("wrong_cases") or []]
        if mine is None or mine.get("result") not in RESULTS:
            outcome, why = "missed" if want["result"] == "Failed" else "no result", f"the app's result: {(mine or {}).get('result') or 'this test was not run'}"
        elif want["result"] == "Failed" and mine["result"] == "Failed":
            not_found = [c for c in wanted_cases if c not in mine["wrong_cases"]]
            extra = [c for c in mine["wrong_cases"] if wanted_cases and c not in wanted_cases]
            outcome = "caught" if not not_found else "caught in part"
            why = (f"expected wrong cases not found by the app: {', '.join(not_found)}. " if not_found else "") + \
                  (f"The app also found cases that were not listed: {', '.join(extra)}." if extra else "")
        elif want["result"] == "Failed":
            outcome, why = "missed", "the cryptographer expected Failed and the app says Passed"
        elif mine["result"] == "Failed":
            outcome, why = "found something not listed", f"the cryptographer expected Passed; the app's wrong cases: {', '.join(mine['wrong_cases'])}"
        else:
            outcome, why = "agreed", "both say Passed"
        lines.append({"test": want["test"], "title": research.TITLES[want["test"]], "expected": want["result"], "app": (mine or {}).get("result"),
                      "outcome": outcome, "why": why.strip()})
    listed = {want["test"] for want in expected["expect"]}
    for test, mine in got.items():
        if test not in listed and mine.get("result") == "Failed":
            lines.append({"test": test, "title": mine.get("title"), "expected": None, "app": "Failed", "outcome": "found something not listed",
                          "why": f"not in the expected file; the app's wrong cases: {', '.join(mine['wrong_cases'])}"})
    return lines


def reveal(case: str, expected_file: Path, folder: Path = BLIND_DIR, say=print) -> int:
    sealed = _read_seal(case, folder)
    expected, digest = read_expected(expected_file)
    if digest != sealed["expected_sha256"] or expected["case"] != case:
        raise BlindError("This is not the sealed file: its SHA-256 differs from the one in seal.json. Nothing was compared.")
    try:
        ran = json.loads((folder / case / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BlindError(f"Case {case} has not been run yet (there is no run.json).") from None
    if ran.get("frozen_sha256") != sealed["frozen_sha256"]:
        raise BlindError("The run on record was not made with the tests as they were sealed. Nothing was compared.")
    lines = compare(expected, ran)
    record = {"schema": "isogeny.blind-outcome/1", "case": case, "library": sealed["library"], "revealed_at": _now(),
              "expected_sha256": digest, "sealed_at": sealed["sealed_at"], "ran_at": ran.get("ran_at"), "bug": expected.get("bug"),
              "lines": lines, "missed": sum(1 for line in lines if line["outcome"] == "missed")}
    (folder / case / "outcome.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    say(f"Blind test, case {case}: {sealed['library']['name']} {sealed['library']['version']} (sealed {sealed['sealed_at']}, run {ran.get('ran_at')})")
    for line in lines:
        say(f"  {line['outcome'].upper():28} {line['title']}: expected {line['expected']}, the app says {line['app']}" + (f". {line['why']}" if line["why"] else ""))
    say(f"Missed: {record['missed']}. The outcome is saved as outcome.json; a miss stays in it as a miss.")
    return 0


def main(argv: list[str] | None = None, folder: Path = BLIND_DIR) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.blind", description="The blind test: seal, run, reveal (docs/BLIND-TEST.md).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seal", help="seal your expected result before the run").add_argument("expected")
    sub.add_parser("run", help="run a sealed case").add_argument("case")
    shown = sub.add_parser("reveal", help="check the sealed file and compare")
    shown.add_argument("case")
    shown.add_argument("expected")
    args = parser.parse_args(argv)
    try:
        if args.command == "seal":
            return seal(Path(args.expected), folder)
        if args.command == "run":
            return run(args.case, folder)
        return reveal(args.case, Path(args.expected), folder)
    except BlindError as problem:
        print(f"Blind test: {problem}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
