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
import re
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


# ---------------------------------------------------------------- the migration demo (phase 4a)
# The answer key demo/expected-migration.json is read as it is and never written. Its parts: "verify" (MV1-MV7),
# "status" (MS1-MS7), "recommendation" (MR1-MR7), "roadmap" (MP1-MP7), each a list of {"id", "system", "expected",
# ...}; "fixes" (the text-only suggestions expected in Fixes) and "controls". Anything in the key this command
# does not understand is reported as a mismatch, so nothing is passed over silently.

MIGRATION_PARTS = ("verify", "status", "recommendation", "roadmap")
MIGRATION_OTHER_KEYS = ("_about", "fixes", "controls", "acme_pay_unchanged")
# How the key words a recommendation -> (the option, is it already in place today?)
RECOMMENDATION_WORDS = {
    "hybrid": ("hybrid", False), "hybrid, already in place": ("hybrid", True), "hybrid (sign with both)": ("hybrid", False),
    "keep classical for now": ("keep", False), "wrap the connection": ("wrap", False),
    "full post-quantum": ("full_pq", False), "full post-quantum, already in place": ("full_pq", True),
    "no recommendation": (None, None),
}
SETTING_WORDS = {"internet-facing": ("exposure", "internet"), "internal": ("exposure", "internal"),
                 "long-lived": ("lifespan", "long"), "short-lived": ("lifespan", "short"),
                 "can be changed": ("can_change", "yes"), "can't be changed": ("can_change", "no")}
REVIEW_DATE_RULE = "12 months from the measurement, not later than 31 Dec 2030"


def collect_migration(settings: Settings | None = None) -> dict:
    """Run the migration demo once through the same path as the buttons (Import, tick the boxes, Verify, Measure
    status) and return the app's answers for each system, read from the same views the screens draw."""
    from . import migration_rules, migration_servers
    from .db import TestRunRow, TestSpecRow
    from .testlab import read_spec, run_record
    settings = settings or load_settings()
    out: dict = {"mode_line": None, "notes": [], "systems": {}, "fixes": [], "control_misread_reads": None, "stopped": None}
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        lab = Lab(dataclasses.replace(settings, data_dir=Path(scratch) / "data"), allow_external_demo_server=True)
        lab.start()
        try:
            out["mode_line"] = lab.mode.line
            imp = lab.import_file("migration-demo.csv", migration_servers.file_for(settings.migration_ports))
            out["notes"] += list(imp.get("notices") or [])
            for address in imp["addresses"]:
                lab.confirm_address(imp["id"], address["address"], True)
            claims = {c["location"]: c for c in imp["claims"]}
            # When the test servers were moved to other ports (the automated tests do that), the answers still go by
            # the addresses written in the demo file, which are the ones the answer key names.
            as_in_file = {f"localhost:{port}": f"localhost:{default}"
                          for port, default in zip(settings.migration_ports, migration_servers.DEFAULT_PORTS)}
            verify = {r["claim"]["location"]: r["result"] for r in lab.verify(imp["id"])["results"]}
            plan = lab.ensure_plan(imp["id"])
            lab.measure_migration(plan["id"])
            lab.wait_until_measured(plan["id"], WAIT_SECONDS)
            view = lab.migration_view(plan["id"])
            place = {row["system_key"]: band["title"] for band in view["roadmap"]["bands"] for row in band["rows"]}
            measured = next((p["v"] for p in view["subline"] if p["t"] == "time"), None)
            for system in view["systems"]:
                facts = {f["label"]: "".join(p["v"] for p in f["value"] if p["t"] != "tag").strip() for f in system["today"]["facts"]}
                fields = {f["field"]: f for f in system["settings"]["fields"]}
                recommended = next((o for o in system["options"] if "Recommended" in o["tags"]), None)
                planned = next((o for o in system["options"] if o["highlighted"]), None)
                blockers = [] if planned is None else [
                    "".join(p["v"] for p in line["text"] if p["t"] != "tag").replace(" .", ".").strip()
                    for section in planned["sections"] if section["title"] == "Blockers" for line in section["lines"]]
                client = facts.get("A classical-only client connects")
                keep = next((o for o in system["options"] if o["key"] == "keep" and o["choose"]), None)
                result = system["today"]["result"]
                here = system["name"]
                name = as_in_file.get(here, here)   # answers are keyed by the names in demo/migration-demo.csv
                out["systems"][name] = {
                    "claimed": claims[here]["claimed_value"] if here in claims else None,
                    "verify": verify.get(here), "status": system["status"]["label"], "algorithm": facts.get("It signs with"),
                    "classical_client": None if client is None else True if client.startswith("Yes") else False if client.startswith("No") else "not clear",
                    "tls_versions": facts.get("TLS versions"),
                    "settings": {f: (fields[f]["value"], fields[f]["source"]) for f in fields},
                    "recommended": recommended["key"] if recommended else None,
                    "in_place": ("In place today" in recommended["tags"]) if recommended else None,
                    "recommendation_title": system["recommendation"]["title"],
                    "review_date": keep["choose"]["review_date"]["value"] if keep and keep["choose"]["review_date"] else None,
                    "measured_on": str(measured)[:10] if measured else None,
                    "roadmap": place.get(system["key"]),
                    "blockers": [b for b in blockers if not b.startswith("None")],
                    "control": result["control"]["outcome"] if result else None, "run_id": result["run_id"] if result else None}
            for fix in lab.fixes_view(plan["id"])["fixes"]:
                suggestion = next((sec["suggestion"] for sec in fix["sections"] if sec.get("suggestion")), {})
                rows = (suggestion.get("where") or {}).get("rows") or []
                title = fix["title"]
                for here, name in as_in_file.items():
                    title = title.replace(here, name)
                out["fixes"].append({"title": title, "kind": fix["kind"], "status": fix["status"]["key"],
                                     "buttons": len(fix["actions"]["buttons"]), "proof": fix["proof"]["text"],
                                     "nginx": next((f"{r['lead']} {r['code']}" for r in rows if r["place"] == "nginx"), None)})
            # The control, tried for real: take one stored measurement that gave a status, make its record say the
            # classical control server was read as offering hybrid, and have the reviewer review that record.
            sample = next((s for s in out["systems"].values() if s["status"] in ("Hybrid", "Classical", "Post-quantum only")
                           and s["tls_versions"] is not None and s["run_id"]), None)
            if sample is not None:
                with lab.db() as db:
                    run = db.get(TestRunRow, sample["run_id"])
                    spec_row = db.get(TestSpecRow, run.spec_hash)
                    spec, _ = read_spec(spec_row)
                    record = json.loads(json.dumps(run_record(run)))
                    proposed_by = spec_row.proposed_by
                record["raw"]["control"]["classical"]["probes"]["hybrid"] = dict(record["raw"]["control"]["hybrid"]["probes"]["hybrid"])
                review = lab.reviewer.review({"spec": spec, "spec_hash": run.spec_hash, "proposed_by": proposed_by, "run": record})
                code = review["verdict"]["code"]
                out["control_misread_reads"] = "a status" if code in ("classical", "hybrid", "pq_only") else "Couldn't check"
            out["latest_review"] = migration_rules.LATEST_REVIEW.isoformat()
        except Exception as exc:
            out["stopped"] = f"The check stopped early: {str(exc) or exc.__class__.__name__}"
        finally:
            lab.stop()
    return out


def _twelve_months_after(day: str | None, latest: str) -> str | None:
    from datetime import date
    from . import migration_rules
    try:
        return min(migration_rules.default_review_date(date.fromisoformat(str(day))), date.fromisoformat(latest)).isoformat()
    except (TypeError, ValueError):
        return None


def compare_migration(expected: object, answers: dict) -> dict:
    """One line per answer in the key: {"id", "what", "expected", "actual", "match", "why"}."""
    lines: list[dict] = []
    systems = answers.get("systems") or {}

    def add(id_: str, what: str, want: object, got: object, match: bool, why: str | None = None) -> None:
        lines.append({"id": id_, "what": what, "expected": want, "actual": got, "match": bool(match), "why": why})

    if not isinstance(expected, dict):
        add("?", "the answer key", "a JSON object", type(expected).__name__, False, "the answer key is not in the layout this command reads")
        return {"lines": lines, "matched": 0, "total": 1}
    for key in expected:
        if key not in MIGRATION_PARTS and key not in MIGRATION_OTHER_KEYS:
            add("?", f"the part {key!r} of the answer key", "(a part this command knows)", None, False, "this command doesn't know that part of the answer key")
    for part in MIGRATION_PARTS:
        entries = expected.get(part)
        if not isinstance(entries, list) or not entries:
            add("?", f"the part {part!r} of the answer key", "a list of answers", None, False, "missing from the answer key")
            continue
        for entry in entries:
            id_, name, want = str(entry.get("id", "?")), entry.get("system"), entry.get("expected")
            got = systems.get(name)
            if got is None:
                add(id_, f"{part}: {name}", want, None, False, "the app has no answer for this system")
                continue
            problems: list[str] = []
            unknown = [k for k in entry if k not in ("id", "system", "expected", "because", "claim", "note", "settings", "review_date",
                                                     "classical_only_client_connects")]
            problems += [f"the key's field {k!r} is not one this command knows" for k in unknown]
            if part == "verify":
                actual = got["verify"]
                ok = actual == want
                claim = str(entry.get("claim") or "")
                if claim and str(got["claimed"] or "").lower() not in claim.lower():
                    problems.append(f"the file's claim reads {got['claimed']!r}, the key says {claim!r}")
            elif part == "status":
                actual = got["status"] + (f" ({got['algorithm']})" if got["algorithm"] and "(" in str(want) else "")
                ok = actual == want
                if "classical_only_client_connects" in entry and got["classical_client"] is not entry["classical_only_client_connects"]:
                    problems.append(f"a classical-only client connects: the key says {entry['classical_only_client_connects']}, the app measured {got['classical_client']}")
                note = str(entry.get("note") or "")
                if note == "no TLS 1.3":
                    if "1.3" in str(got["tls_versions"]):
                        problems.append(f"the key notes no TLS 1.3, the app measured TLS versions {got['tls_versions']}")
                elif note:
                    problems.append(f"the key's note {note!r} is not one this command can check")
            elif part == "recommendation":
                wanted = RECOMMENDATION_WORDS.get(str(want).lower())
                actual = got["recommendation_title"].removeprefix("Recommended: ") if got["recommended"] else "No recommendation"
                ok = wanted is not None and (got["recommended"], got["in_place"]) == wanted
                if wanted is None:
                    problems.append("this command doesn't know that recommendation wording")
                for token in [t.strip() for t in str(entry.get("settings") or "").split(",") if t.strip()]:
                    field = SETTING_WORDS.get(token.lower())
                    if field is None:
                        problems.append(f"the key's setting {token!r} is not one this command knows")
                    elif got["settings"][field[0]][0] != field[1]:
                        problems.append(f"setting {field[0]}: the key says {token!r}, the app has {got['settings'][field[0]][0]!r} ({got['settings'][field[0]][1]})")
                if "review_date" in entry:
                    if entry["review_date"] != REVIEW_DATE_RULE:
                        problems.append("the key's review date rule is not one this command knows")
                    else:
                        should = _twelve_months_after(got["measured_on"], answers.get("latest_review") or "2030-12-31")
                        if not should or got["review_date"] != should:
                            problems.append(f"review date: measured {got['measured_on']}, so {should} was expected; the app proposes {got['review_date']}")
            else:
                actual = got["roadmap"]
                ok = actual == want
            add(id_, f"{part}: {name}", want, actual, ok and not problems, "; ".join(problems) or None)
    # the Fixes entries: exactly the suggestions the key lists, each text only
    fixes = list(answers.get("fixes") or [])
    wanted_fixes = (expected.get("fixes") or {}).get("expected_text_only_suggestions")
    if not isinstance(wanted_fixes, list):
        add("fixes", "the suggestions expected in Fixes", "a list", None, False, "missing from the answer key")
        wanted_fixes = []
    found_titles = []
    for n, text in enumerate(wanted_fixes, start=1):
        name, _, rest = str(text).partition(": ")
        if rest.startswith("how to turn on hybrid key exchange"):
            fix = next((f for f in fixes if f["title"] == f"Turn on hybrid key exchange on {name}"), None)
            checked = bool(fix and str(fix["nginx"] or "").startswith("Checked on nginx "))
            ok, why = bool(fix) and fix["kind"] == "text" and checked, None if checked or not fix else "its nginx setting is not marked as checked on real nginx"
        elif rest.startswith("can't make post-quantum signatures"):
            fix = next((f for f in fixes if f["title"] == f"{name} can't make post-quantum signatures"), None)
            ok, why = bool(fix) and fix["kind"] == "text", None
            if fix and not any("can't make post-quantum signatures" in b for b in (systems.get(name) or {}).get("blockers", [])):
                ok, why = False, "the app does not list it as a blocker for that system"
        else:
            fix, ok, why = None, False, "this command doesn't know that suggestion wording"
        if fix:
            found_titles.append(fix["title"])
        add(f"fix {n}", f"in Fixes: {text}", "a text-only suggestion", fix["title"] if fix else None, ok, why if fix or why else "the app shows no such suggestion")
    extra = [f["title"] for f in fixes if f["title"] not in found_titles]
    text_only = all(f["kind"] == "text" and f["status"] == "text_only" and f["buttons"] == 0 and "has not applied it" in f["proof"] for f in fixes)
    add("fixes", str((expected.get("fixes") or {}).get("never") or "every suggestion is text only, and there are no others"),
        "text only, nothing else listed", "text only" + (f", but also: {', '.join(extra)}" if extra else ", nothing else listed") if text_only else "not all text only",
        text_only and not extra)
    # the controls
    with_status = [s for s in systems.values() if s["status"] in ("Hybrid", "Classical", "Post-quantum only")]
    read_right = bool(with_status) and all(s["control"] == "as_expected" for s in with_status)
    misread = answers.get("control_misread_reads")
    add("controls", str((expected.get("controls") or {}).get("expected") or "the controls"), "controls read correctly; a misread control reads Couldn't check",
        f"controls {'read correctly' if read_right else 'NOT all read correctly'}; a misread control reads {misread}", read_right and misread == "Couldn't check")
    return {"lines": lines, "matched": sum(1 for line in lines if line["match"]), "total": len(lines)}


def print_migration_report(settings: Settings | None, say=print) -> int:
    """The migration demo against demo/expected-migration.json. Exit code 0 only if the key is there and all match."""
    from . import config
    say("")
    say("Migration demo accuracy check against demo/expected-migration.json (Verify, statuses, recommendations, roadmap, Fixes, controls)")
    answers = collect_migration(settings)
    if answers.get("mode_line"):
        say(f"  mode: {answers['mode_line']}")
    for note in answers["notes"]:
        say(f"  note: {note}")
    if answers["stopped"]:
        say(f"  PROBLEM  {answers['stopped']}")
    if not config.EXPECTED_MIGRATION_JSON.exists():
        say("  NOT COMPARED  demo/expected-migration.json is not in this copy of the repository, so there is nothing to compare with.")
        say("Migration demo accuracy: not compared (answer key missing)")
        return 2
    try:
        expected = json.loads(config.EXPECTED_MIGRATION_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        say(f"  PROBLEM  the answer key could not be read ({exc.__class__.__name__}).")
        return 1
    report = compare_migration(expected, answers)
    for line in report["lines"]:
        say(f"  {line['id']}  {'MATCH   ' if line['match'] else 'MISMATCH'}  expected {line['expected']!r}, app says {line['actual']!r}  -  {line['what']}")
        if line["why"]:
            say(f"        why: {line['why']}")
    say(f"Migration demo accuracy: {report['matched']} of {report['total']} match")
    return 0 if report["matched"] == report["total"] and not answers["stopped"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.accuracy", description="Compare the app's demo answers with demo/expected.json.")
    parser.add_argument("--only", choices=("acme", "migration"), default=None,
                        help="acme = only the Acme Pay demo (demo/expected.json); migration = only the migration demo "
                             "(demo/expected-migration.json). Default: both.")
    parser.add_argument("--mode", choices=("auto", "demo", "isolated"), default=None,
                        help="demo = local processes; isolated = containers (needs Docker and the prepared images); "
                             "auto = isolated when it is available. Default: the EVIDENCE_LAB_MODE setting, else auto.")
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.mode is not None:
        settings = dataclasses.replace(settings, force_mode=None if args.mode == "auto" else args.mode)
    codes = []
    if args.only != "migration":
        codes.append(print_report(run_accuracy(settings)))
    if args.only != "acme":
        codes.append(print_migration_report(settings))
    return max(codes)


if __name__ == "__main__":
    sys.exit(main())
