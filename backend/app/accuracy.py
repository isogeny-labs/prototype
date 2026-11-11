"""Accuracy check: does the app's answer for every demo claim and test match demo/expected.json?

Run from the backend folder:  .venv/bin/python -m app.accuracy [--mode auto|demo|isolated]

It goes down the same path as the buttons, on a fresh scratch database: import the demo file, verify the
claims, propose and lock the plan, add the post-quantum readiness test, Run all (through the job runner),
then Retest on acme-sign 1.4.3. Answers are read only from reviewed results (the Evidence Lab view).

15 answers: V1-V3 (Verify), T1-T5 (tests on 1.4.2), R1-R5 (the same tests on 1.4.3), the controls, and A1
(post-quantum readiness). It only READS the answer key; it never writes it. Any mismatch or missing answer
is printed and makes the command exit with code 1.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

from .config import EXPECTED_JSON, Settings, load_settings
from .db import ReviewRow
from .lab import Lab

# Which claim in demo/acme-pay-cbom.json answers which entry of the answer key: (bom-ref, kind) -> id.
DEMO_CLAIM_IDS = {
    ("proto-tls13", "protocol_versions"): "V1",
    ("cert-server", "certificate"): "V2",
    ("lib-acme-sign", "signature_algorithm"): "V3",
}
# Which test answers which entry: id -> (kind of test, first run or retest).
TEST_IDS = {
    "T1": ("tls_versions", "first"), "T2": ("certificate", "first"), "T3": ("official_vectors", "first"),
    "T4": ("bad_signatures", "first"), "T5": ("speed_size", "first"),
    "R1": ("tls_versions", "retest"), "R2": ("certificate", "retest"), "R3": ("official_vectors", "retest"),
    "R4": ("bad_signatures", "retest"), "R5": ("speed_size", "retest"),
    "A1": ("pq_readiness", "first"),
}
RETEST_VERSION = "1.4.3"
CHECKER_TOO_OLD = "checker_too_old"  # the only recorded reason that lets A1 match the answer key's alternative
NO_ANSWER = "(no answer)"
WAIT_SECONDS = 600.0


def _answer(lab: Lab, result: dict | None) -> dict | None:
    """What the accuracy check reads from one reviewed result (None when the test has no reviewed run)."""
    if not result:
        return None
    with lab.db() as db:
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == result["run_id"])).first()
    return {"label": result["label"], "code": result["code"], "summary": result["summary"],
            "control": result["control"]["outcome"], "mode": result["mode"],
            # the reason is the reviewer's own, and only counts while the shown result is still that verdict
            "reason_code": review.reason_code if review is not None and review.code == result["code"] else None}


def collect(settings: Settings | None = None) -> dict:
    """Run the whole demo once through the Lab service path and return the app's answers."""
    settings = settings or load_settings()
    answers: dict = {"notes": [], "mode_line": None, "verify": {}, "unmapped_claims": [], "tests": {}, "stopped": None}
    notes = answers["notes"]
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        # Own scratch database (so the app's saved work is untouched); same demo test certificate as the app.
        lab = Lab(settings, db_path=Path(scratch) / "accuracy.sqlite3", allow_external_demo_server=True)
        lab.start()
        try:
            answers["mode_line"] = lab.mode.line
            if lab.demo.running:
                notes.append(f"Started the demo server on {settings.demo_address} for this check.")
            elif lab.demo.port_in_use:
                notes.append(f"Port {settings.demo_tls_port} is already in use (normally by the running app). Using it "
                             "only if its certificate is this app's demo test certificate. Timings are cleaner with "
                             "the app stopped.")
            else:
                notes.append(f"The demo server could not start: {lab.demo.error}")
            imp = lab.import_demo()
            for address in imp["addresses"]:
                lab.confirm_address(imp["id"], address["address"], True)
                notes.append(f"Confirmed {address['address']} automatically for this check (it is the app's own demo "
                             "server on this computer). In the app, you tick this box yourself.")
            run = lab.verify(imp["id"])
            for res in run["results"]:
                key = DEMO_CLAIM_IDS.get((res["claim"]["ref"], res["claim"]["kind"]))
                if key:
                    answers["verify"][key] = res
                else:
                    answers["unmapped_claims"].append(res["claim"]["text"])
            # Tests: exactly what the Tests and Evidence Lab buttons do.
            plan = lab.ensure_plan(imp["id"])                       # propose and lock
            lab.add_test(plan["id"], "pq_readiness")                # + Add test
            lab.run_all(plan["id"])                                 # Run all (job runner)
            lab.wait_until_idle(plan["id"], WAIT_SECONDS)
            first = lab.lab_view(plan["id"])                        # reviewed results only
            for row in first["rows"]:
                answers["tests"][(row["kind"], "first")] = _answer(lab, row["result"])
            lab.start_retest(plan["id"], RETEST_VERSION)            # Retest new version
            lab.wait_until_idle(plan["id"], WAIT_SECONDS)
            after = lab.lab_view(plan["id"])
            for row in after["rows"]:
                answers["tests"][(row["kind"], "retest")] = _answer(lab, row["after"])
        except Exception as exc:  # shown, never hidden: every answer not reached counts as a mismatch
            answers["stopped"] = f"The check stopped early: {str(exc) or exc.__class__.__name__}"
        finally:
            lab.stop()
    return answers


def compare(expected: dict, answers: dict) -> dict:
    """Line up the app's answers with the answer key. Pure: no app, no files."""
    lines, verify, tests = [], answers.get("verify") or {}, answers.get("tests") or {}
    for entry in expected["verify"]:
        res = verify.get(entry["id"])
        got = res["result"] if res else "(no answer: the demo file produced no claim for this entry)"
        lines.append({"id": entry["id"], "what": entry["claim"], "expected": entry["expected"], "actual": got,
                      "match": res is not None and got == entry["expected"], "found": (res or {}).get("found"),
                      "reason": (res or {}).get("reason"), "app_claim_text": (res or {}).get("claim", {}).get("text")})
    for entry in expected["tests_on_1_4_2"] + expected["tests_on_1_4_3"]:
        got = tests.get(TEST_IDS[entry["id"]])
        lines.append({"id": entry["id"], "what": entry["test"], "expected": entry["expected"],
                      "actual": got["label"] if got else NO_ANSWER, "match": got is not None and got["label"] == entry["expected"],
                      "found": (got or {}).get("summary"), "reason": None, "app_claim_text": None})
    # Controls: every test and retest has a reviewed run, none is "Couldn't trust this run", and every run that
    # reached a verdict had its control behave as expected.
    wanted = [key for tid, key in TEST_IDS.items()]
    missing = [f"{kind} ({phase})" for kind, phase in wanted if not tests.get((kind, phase))]
    untrusted = [f"{kind} ({phase})" for (kind, phase), got in tests.items() if got and got["code"] == "couldnt_trust"]
    misbehaved = [f"{kind} ({phase})" for (kind, phase), got in tests.items()
                  if got and got["code"] not in ("couldnt_run", "couldnt_trust") and got["control"] != "as_expected"]
    reached = [got for got in tests.values() if got and got["code"] not in ("couldnt_run", "couldnt_trust")]
    controls_ok = not (missing or untrusted or misbehaved) and bool(reached)
    if controls_ok:
        actual = f"all {len(reached)} runs that reached a result had their control behave as expected; none is Couldn't trust this run"
    else:
        parts = ([f"no reviewed result for: {', '.join(missing)}"] if missing else []) + \
                ([f"Couldn't trust this run: {', '.join(untrusted)}"] if untrusted else []) + \
                ([f"control did not behave as expected: {', '.join(misbehaved)}"] if misbehaved else [])
        actual = "; ".join(parts) or "no test reached a result"
    lines.append({"id": "controls", "what": "Built-in controls", "expected": expected["controls"]["expected"], "actual": actual,
                  "match": controls_ok, "found": None, "reason": None, "app_claim_text": None})
    for entry in expected["add_on"]:
        got = tests.get(TEST_IDS[entry["id"]])
        alternative = entry.get("or_if_checker_too_old")
        label = got["label"] if got else NO_ANSWER
        match = got is not None and (label == entry["expected"]
                                     or (alternative is not None and label == alternative and got["reason_code"] == CHECKER_TOO_OLD))
        reason = None
        if got is not None and alternative is not None and label == alternative:
            reason = ("matched the answer key's alternative: the recorded reason is that this computer's checker is too old"
                      if match else "the label is the alternative, but the recorded reason is not the checker version")
        lines.append({"id": entry["id"], "what": entry["test"], "expected": entry["expected"], "actual": label, "match": match,
                      "found": (got or {}).get("summary"), "reason": reason, "app_claim_text": None})
    return {"lines": lines, "matched": sum(bool(line["match"]) for line in lines), "total": len(lines),
            "notes": list(answers.get("notes") or []), "mode_line": answers.get("mode_line"), "stopped": answers.get("stopped"),
            "unmapped_claims": list(answers.get("unmapped_claims") or [])}


def run_accuracy(settings: Settings | None = None) -> dict:
    expected = json.loads(EXPECTED_JSON.read_text(encoding="utf-8"))
    return compare(expected, collect(settings))


def print_report(report: dict, say=print) -> int:
    say("Demo accuracy check against demo/expected.json (Verify, the tests, the retest, the controls)")
    if report["mode_line"]:
        say(f"  mode: {report['mode_line']}")
    for note in report["notes"]:
        say(f"  note: {note}")
    if report["stopped"]:
        say(f"  PROBLEM  {report['stopped']}")
    for line in report["lines"]:
        say(f"  {line['id']}  {'MATCH   ' if line['match'] else 'MISMATCH'}  expected {line['expected']!r}, "
            f"app says {line['actual']!r}  -  {line['what']}")
        if line["found"]:
            say(f"        found: {line['found']}")
        if line["reason"]:
            say(f"        reason: {line['reason']}")
        if line["app_claim_text"] and line["app_claim_text"] != line["what"]:
            say(f"        (the app words this claim as: {line['app_claim_text']})")
    for text in report["unmapped_claims"]:
        say(f"  EXTRA   the demo file produced a claim the answer key does not list: {text}")
    say(f"Demo accuracy: {report['matched']} of {report['total']} match")
    return 0 if report["matched"] == report["total"] and not report["unmapped_claims"] and not report["stopped"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.accuracy", description="Compare the app's demo answers with demo/expected.json.")
    parser.add_argument("--mode", choices=("auto", "demo", "isolated"), default=None,
                        help="demo = local processes; isolated = containers (needs Docker and the prepared images); "
                             "auto = isolated when it is available. Default: the EVIDENCE_LAB_MODE setting, else auto.")
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.mode is not None:
        settings = dataclasses.replace(settings, force_mode=None if args.mode == "auto" else args.mode)
    return print_report(run_accuracy(settings))


if __name__ == "__main__":
    sys.exit(main())
