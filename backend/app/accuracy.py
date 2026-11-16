"""Accuracy check: does the app's answer for every demo claim and test match demo/expected.json?

Run from the backend folder:  .venv/bin/python -m app.accuracy [--mode auto|demo|isolated]

It goes down the same path as the buttons, on a fresh scratch database: import the demo file, verify the
claims, propose and lock the plan, add the post-quantum readiness test, Run all (through the job runner),
then Retest on acme-sign 1.4.3. Answers are read only from reviewed results (the Evidence Lab view).

18 answers: V1-V3 (Verify), T1-T5 (tests on 1.4.2), R1-R5 (the same tests on 1.4.3), the controls, A1
(post-quantum readiness), and since phase 4b S1-S3: the server TLS fix (SPEC 7c) tried on a test copy, approved,
applied to the demo server, then Verify and the server test again (rolled back at the end, in the check's own data).
It only READS the answer keys; it never writes them. Any mismatch or missing answer is printed and makes the command
exit with code 1.

Then the migration demo against demo/expected-migration.json (47 answers), and since phase 4c the real libraries
against demo/expected-real-libraries.json (accuracy_real.py), and since phase 4d the dependency lists against
demo/expected-dependencies.json (accuracy_deps.py). `--only acme|migration|real|dependencies` runs one of the four.
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

from app.config import EXPECTED_JSON, Settings, load_settings
from app.db import ReviewRow
from app.lab.hub import Lab

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
            answers["server_fix"] = _server_fix(lab, imp["id"], plan["id"], notes)
        except Exception as exc:  # shown, never hidden: every answer not reached counts as a mismatch
            answers["stopped"] = f"The check stopped early: {str(exc) or exc.__class__.__name__}"
        finally:
            lab.stop()
    return answers


def _server_fix(lab: Lab, import_id: int, plan_id: int, notes: list[str]) -> dict:
    """S1 to S3 (SPEC 7c): the server TLS fix, through the same path as the buttons in Fixes: Try on a test copy,
    Ask for approval, Approve, Apply, then Verify again. Rolled back at the end (the check's own data only)."""
    out: dict = {}
    key = f"tls:server:{lab.settings.demo_address}"
    fixes = lab.fixes_view(plan_id)["fixes"]
    box = next((f["change_box"] for f in fixes if (f.get("change_box") or {}).get("id") == key), None)
    if box is None:
        notes.append("The server TLS fix has no change box, so S1 to S3 could not be answered.")
        return out
    try_button = next(b for b in box["buttons"] if b["action"] == "try")
    if not try_button["enabled"]:
        notes.append(f"Try on a test copy is off for the server TLS fix: {try_button['reason']}")
        return out
    lab.try_change(plan_id, key)
    lab.wait_until_changes_idle(plan_id, WAIT_SECONDS)
    with lab.db() as db:
        plan = lab._plan(db, plan_id)
        change = lab._change_by_key(db, plan, key)
        rec = lab._change_records(db, plan, change)
    copy = next((c for c in rec["try_copies"] if c["phase"] == "try"), None)
    measured = (copy or {}).get("measured")
    if measured and measured.get("result"):
        out["S1"] = {"label": measured["result"]["label"], "summary": measured["result"]["summary"]}
    if (rec.get("try_outcome") or {}).get("code") != "passed":
        notes.append("The try on a test copy did not pass, so the server TLS fix was not applied (S2 and S3 have no answer).")
        return out
    lab.ask_approval(plan_id, key, ["you"])
    lab.approve_change(plan_id, key, "you")
    notes.append("Approved the server TLS fix as You, automatically, for this check. In the app, a person approves and presses Apply.")
    lab.apply_change(plan_id, key)
    lab.wait_until_changes_idle(plan_id, WAIT_SECONDS)
    run = lab.verify(import_id)
    v1 = next((r for r in run["results"] if DEMO_CLAIM_IDS.get((r["claim"]["ref"], r["claim"]["kind"])) == "V1"), None)
    if v1 is not None:
        out["S2"] = {"label": v1["result"], "summary": v1.get("summary")}
    row = next((r for r in lab.lab_view(plan_id)["rows"] if r["kind"] == "tls_versions"), None)
    shown = (row["after"] or row["result"]) if row else None      # the newest column holds the measurement after Apply
    if shown:
        out["S3"] = {"label": shown["label"], "summary": shown["summary"]}
    lab.rollback_change(plan_id, key)
    lab.wait_until_changes_idle(plan_id, WAIT_SECONDS)
    notes.append("Rolled the server TLS fix back at the end of this check.")
    return out


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
    # S1 to S3 (SPEC 7c, phase 4b): the server TLS fix tried on a test copy, applied to the demo server, and checked after.
    fix = answers.get("server_fix") or {}
    for entry in (expected.get("after_server_fix") or {}).get("entries") or []:
        got = fix.get(entry["id"])
        lines.append({"id": entry["id"], "what": entry.get("test") or entry.get("claim"), "expected": entry["expected"],
                      "actual": got["label"] if got else NO_ANSWER, "match": got is not None and got["label"] == entry["expected"],
                      "found": (got or {}).get("summary"), "reason": None, "app_claim_text": None})
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


# ---------------------------------------------------------------- the migration demo (phases 4a and 4b)
# The answer key demo/expected-migration.json is read as it is and never written. Its parts (revised for phase 4b):
# "verify" (MV), "tracks" (MT), "never_done", "recommendation" (MR), "roadmap" (MP), "tests_step" (MQ),
# "change_8452_to_hybrid" and "change_8451_to_full_post_quantum" (MC), "rules", "controls". Prose answers are split into
# clauses, and each clause must match one of the patterns below; a clause this command does not understand is a
# mismatch, so nothing in the key is passed over silently.

MIGRATION_PARTS = ("verify", "tracks", "never_done", "recommendation", "roadmap", "tests_step", "change_8452_to_hybrid",
                   "change_8451_to_full_post_quantum", "rules", "controls")
MIGRATION_OTHER_KEYS = ("_about", "acme_pay_unchanged")   # the second is graded by the Acme Pay half of this command
REVIEW_DATE_RULE = "12 months from the measurement and not later than 31 Dec 2030"
TRACK_KEYS = {"key_exchange": "kex", "authentication": "auth", "signatures": "signatures"}


def _norm(value: object) -> str:
    if isinstance(value, bool):
        value = "yes" if value else "no"
    return re.sub(r"\s+", " ", re.sub(r"[‘’'\"“”]", "", str(value if value is not None else "none"))).strip().lower()


def _words_in(fragment: str, text: str) -> bool:
    """Every meaningful word of the key's fragment appears in the app's text (loose, for prose next steps)."""
    stop = {"a", "an", "the", "it", "its", "for", "to", "of", "and", "or", "by", "on", "in", "is", "be", "once", "after", "until"}
    words = [w for w in re.findall(r"[a-z0-9\-]+", _norm(fragment)) if w not in stop]
    have = set(re.findall(r"[a-z0-9\-]+", _norm(text)))
    return bool(words) and all(w in have for w in words)


def _choice_phrase(choice: dict | None) -> str | None:
    if not choice:
        return None
    first, second = choice.get("hybrid_first"), choice.get("classical_first")
    if first == "hybrid" and second == "classical":
        return "follows the client's order: hybrid when listed first, classical when listed first"
    if first == "hybrid" and second == "hybrid":
        return "always hybrid, whichever the client lists first"
    return f"hybrid listed first: {first}; classical listed first: {second}"


def _copy_facts(measured: dict | None) -> dict:
    """The facts of one reviewed measurement that the key's clauses talk about."""
    from app.present.tracks import TRACK_LABELS, hybrid_client
    if not measured:
        return {}
    detail = measured.get("detail") or {}
    auth = detail.get("auth") or {}
    sizes = detail.get("sizes") or {}
    pick = sizes.get("hybrid") if measured["code"] == "hybrid" else sizes.get("pure") if measured["code"] == "pq_only" else sizes.get("classical")
    pick = pick or {}
    return {"kex": TRACK_LABELS.get(measured["code"], measured["code"]),
            "auth": f"{TRACK_LABELS.get(auth.get('status'), 'Couldn’t check')} ({auth.get('certificate')})" if auth.get("certificate") else None,
            "classical_client": detail.get("classical_client"), "hybrid_client": hybrid_client(detail),
            "shares": (pick.get("client_share_bytes"), pick.get("server_share_bytes")), "signature_bytes": pick.get("signature_bytes"),
            "certificate": auth.get("certificate")}


def _system_answers(view: dict, verify: dict) -> dict:
    out = {}
    rows = [(band["title"], row) for band in view["roadmap"]["bands"] for row in band["rows"]]
    for system in view["systems"]:
        tracks = {t["key"]: t for t in system["tracks"]}
        fields = {f["field"]: f for f in system["settings"]["fields"]}
        kex = tracks.get("kex")
        tls_off = any(f["label"] == "TLS versions" and "1.3" not in "".join(p["v"] for p in f["value"]) for f in system["today"]["facts"])
        out[system["name"]] = {
            "verify": verify.get(system["name"]),
            "kex": (kex["status"]["label"] + (" (no TLS 1.3)" if tls_off and kex["status"]["code"] == "classical" else "")) if kex else None,
            "auth": None, "signatures": None,
            "classical_client": None, "default_choice": None,
            "next": {k: "".join(p["v"] for p in t["next"]) for k, t in tracks.items()},
            "why": {k: "".join(p["v"] for p in t["why"]) for k, t in tracks.items()},
            "recommended": next((o["key"] for o in system["options"] if "Recommended" in o["tags"]), None),
            "in_place": next(("In place today" in o["tags"] for o in system["options"] if "Recommended" in o["tags"]), None),
            "recommendation_title": system["recommendation"]["title"],
            "review_date": next((o["choose"]["review_date"]["value"] for o in system["options"] if o["key"] == "keep" and o["choose"]
                                 and o["choose"]["review_date"]), None),
            "can_change": fields["can_change"]["value"],
            "roadmap": {row["track"]: title for title, row in rows if row["system_key"] == system["key"]},
            "blockers": [l["text"] for o in system["options"] if "Recommended" in o["tags"] for s in o["sections"] if s["title"] == "Blockers"
                         for l in s["lines"]],  # noqa: E741
            "change_badge": (system.get("change") or {}).get("badge", {}).get("label"),
        }
        a = out[system["name"]]
        auth = tracks.get("auth") or tracks.get("signatures")
        if auth is not None:
            cert = next(("".join(p["v"] for p in f["value"] if p["t"] != "tag").split(",")[0].strip() for f in auth["facts"]
                         if f["label"] in ("Certificate key", "It signs with")), None)
            label = auth["status"]["label"] + (f" ({cert})" if cert else "")
            a["auth" if "auth" in tracks else "signatures"] = label
        if kex:
            client = next(("".join(p["v"] for p in f["value"] if p["t"] != "tag") for f in kex["facts"] if f["label"] == "Classical-only clients"), "")
            a["classical_client"] = True if client.startswith("Still connect") else False if client.startswith("Can't") else None
        a["_raw"] = system
    return out


def collect_migration(settings: Settings | None = None) -> dict:
    """Run the migration demo through the same path as the buttons: Import, tick the boxes, Verify, Tests (Run all),
    Measure status, then the two changes of the key (8452 to Hybrid, 8451 to Full post-quantum): Try on a test copy, Ask for
    approval, Approve, Apply, Verify again, Roll back. Also one server that is not ours (a throwaway local server this
    check starts), the evidence download, and the control tried for real. Returns the app's answers, read from the views."""
    from app.servers import migration_servers
    from app.checks import pqtls
    from app.db import TestRunRow, TestSpecRow
    from app.errors import Conflict
    from app.lab.testlab import read_spec, run_record
    settings = settings or load_settings()
    out: dict = {"mode_line": None, "notes": [], "systems": {}, "tests": {}, "changes": {}, "rules": {}, "never_done": {},
                 "control_misread_reads": None, "stopped": None}
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        lab = Lab(dataclasses.replace(settings, data_dir=Path(scratch) / "data"), allow_external_demo_server=True)
        lab.start()
        try:
            out["mode_line"] = lab.mode.line
            ports = settings.migration_ports
            as_in_file = {f"localhost:{p}": f"localhost:{d}" for p, d in zip(ports, migration_servers.DEFAULT_PORTS)}  # noqa: B905
            named = lambda name: as_in_file.get(name, name)  # noqa: E731
            here = {v: k for k, v in as_in_file.items()}
            imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
            out["notes"] += list(imp.get("notices") or [])
            for address in imp["addresses"]:
                lab.confirm_address(imp["id"], address["address"], True)

            def verify_now() -> dict:
                return {named(r["claim"]["location"]): r["result"] for r in lab.verify(imp["id"])["results"]}
            verify = verify_now()
            plan = lab.ensure_plan(imp["id"])
            pid = plan["id"]
            pv = lab.plan_view(pid)
            out["tests"] = {"count": len(pv["tests"]), "kinds": [t["kind"] for t in pv["tests"]],
                            "groups": [t["group"] for t in pv["tests"]], "not_tested": (pv["not_tested"] or {}).get("items", [])}
            lab.run_all(pid)
            lab.wait_until_idle(pid, WAIT_SECONDS)
            out["tests"]["readiness"] = {named(r["group"].split(":", 1)[1]): r["result"]["label"] for r in lab.lab_view(pid)["rows"]
                                         if r["kind"] == "pq_readiness" and r["result"]}
            lab.measure_migration(pid)
            lab.wait_until_measured(pid, WAIT_SECONDS)
            view = lab.migration_view(pid)
            answers = _system_answers(view, {here.get(name, name): result for name, result in verify.items()})   # by the names on screen
            for name, a in answers.items():
                a.pop("_raw")
                out["systems"][named(name)] = a
            measured = next((p["v"] for p in view["subline"] if p["t"] == "time"), None)
            out["measured_on"] = str(measured)[:10] if measured else None
            # the default choice, from the stored measurement (it is in the track facts as words)
            with lab.db() as db:
                plan_row = lab._plan(db, pid)
                for state in lab._migration_states(db, plan_row):
                    if state["name"] in answers and state.get("detail"):
                        out["systems"][named(state["name"])]["default_choice"] = _choice_phrase(state["detail"].get("default_choice"))
            text = json.dumps(view)
            out["never_done"] = {"already_there_shown": "Already there" in text,
                                 "tracks_without_next_or_why": [f"{s['name']} {t['short_title']}" for s in view["systems"] for t in s["tracks"]
                                                                if t["status"]["code"] not in ("couldnt_check", "not_measured")
                                                                and not ("".join(p["v"] for p in t["next"]).strip() and "".join(p["v"] for p in t["why"]).strip())],
                                 "target_tracks_not_keep": [f"{s['name']} {t['short_title']}" for s in view["systems"] for t in s["tracks"]
                                                            if t["status"]["code"] in ("pq_only", "post_quantum")
                                                            and "keep it there" not in "".join(p["v"] for p in t["next"])]}
            # ---- the two changes of the key
            for system_name, option, reviewers in (("localhost:8452", None, ["you", "a"]), ("localhost:8451", "full_pq", ["you"])):
                address = here.get(system_name, system_name)
                key = f"migration:server:{address}"
                rec_out: dict = {"refused_before_try": None, "refused_with_some_approvals": None}
                if option:
                    lab.choose_migration_option(pid, f"server:{address}", option, "The accuracy check tries Full post-quantum.", None)
                try:
                    lab.apply_change(pid, key)
                    rec_out["refused_before_try"] = False
                except Conflict as exc:
                    rec_out["refused_before_try"] = str(exc)
                lab.try_change(pid, key)
                lab.wait_until_changes_idle(pid, WAIT_SECONDS)

                def records():
                    with lab.db() as db:
                        p = lab._plan(db, pid)
                        change = lab._change_by_key(db, p, key)  # noqa: B023
                        return change, lab._change_records(db, p, change)
                change, rec = records()
                copy = next((c for c in rec["try_copies"] if c["phase"] == "try"), {})
                rec_out["try"] = (rec.get("try_outcome") or {}).get("code")
                rec_out["before"] = _copy_facts(rec.get("try_before"))
                rec_out["copy"] = _copy_facts(copy.get("measured"))
                lab.ask_approval(pid, key, reviewers)
                lab.approve_change(pid, key, "you")
                if len(reviewers) > 1:
                    try:
                        lab.apply_change(pid, key)
                        rec_out["refused_with_some_approvals"] = False
                    except Conflict as exc:
                        rec_out["refused_with_some_approvals"] = str(exc)
                    for r in reviewers[1:]:
                        lab.approve_change(pid, key, r)
                lab.apply_change(pid, key)
                lab.wait_until_changes_idle(pid, WAIT_SECONDS)
                change, rec = records()
                rec_out["after_apply"] = (rec.get("apply_outcome") or {}).get("code")
                after_view = {s["name"]: s for s in lab.migration_view(pid)["systems"]}[address]
                rec_out["after_apply_badge"] = (after_view.get("change") or {}).get("badge", {}).get("label")
                fix = next((f for f in lab.fixes_view(pid)["fixes"] if (f.get("change_box") or {}).get("id") == key), None)
                rec_out["fix_after_apply"] = fix["status"]["word"] if fix else None
                rec_out["roadmap_after_apply"] = _system_answers({"systems": [after_view], "roadmap": lab.migration_view(pid)["roadmap"]}, {})[address]["roadmap"]
                rec_out["verify_after_apply"] = verify_now()
                lab.rollback_change(pid, key)
                lab.wait_until_changes_idle(pid, WAIT_SECONDS)
                change, rec = records()
                back_view = {s["name"]: s for s in lab.migration_view(pid)["systems"]}[address]
                rec_out["after_rollback"] = _copy_facts(rec.get("rollback_after"))
                rec_out["rollback"] = (rec.get("rollback_outcome") or {}).get("code")
                fix = next((f for f in lab.fixes_view(pid)["fixes"] if (f.get("change_box") or {}).get("id") == key), None)
                rec_out["fix_after_rollback"] = fix["status"]["word"] if fix else None
                rec_out["roadmap_after_rollback"] = _system_answers({"systems": [back_view], "roadmap": lab.migration_view(pid)["roadmap"]}, {})[address]["roadmap"]
                rec_out["choice_after_rollback"] = next((o["key"] for o in back_view["options"] if "Your choice" in o["tags"]), None)
                lab.verify(imp["id"])   # leave Verify as the server is now
                out["changes"][system_name] = rec_out
            # ---- the rules
            export = lab.export_evidence(pid)
            _, raw, _ = lab.evidence_file(export["id"], "json")
            _, report, _ = lab.evidence_file(export["id"], "html")
            downloads = [lab.change_download(pid, c["id"])[1] for c in (s.get("change") for s in lab.migration_view(pid)["systems"]) if c]
            blob = raw + report + b"".join(downloads)
            evidence = json.loads(raw)["evidence"]
            entry = next((e for e in evidence.get("changes") or [] if (e.get("change") or {}).get("system_key") == f"server:{here.get('localhost:8452')}"), {})
            out["rules"] = {"keys_in_evidence": b"PRIVATE KEY" in blob or b"BEGIN EC" in blob,
                            "records": {"try": bool(entry.get("try")), "approvals": bool((entry.get("approval_request") or {}).get("approvals")),
                                        "apply": bool(entry.get("applies")), "re_measure": bool((entry.get("after_apply") or {}).get("run_id")),
                                        "rollback": bool((entry.get("rollback") or {}).get("run_id"))}}
            # ---- a server that is not ours: a throwaway classical TLS server on this computer, imported and measured
            cert, key_pem, _ = pqtls.test_certificate("ecdsa-p256", "not-ours")
            other = pqtls.Server(groups="X25519:P-256", certificate_pem=cert, key_pem=key_pem)
            try:
                o_imp = lab.import_file("other.csv", f"location,type,claim,value\nlocalhost:{other.port},tls,post_quantum,classical\n".encode())
                for address in o_imp["addresses"]:
                    lab.confirm_address(o_imp["id"], address["address"], True)
                o_plan = lab.ensure_plan(o_imp["id"])
                lab.measure_migration(o_plan["id"])
                lab.wait_until_measured(o_plan["id"], WAIT_SECONDS)
                o_change = lab.migration_view(o_plan["id"])["systems"][0].get("change") or {}
                buttons = {b["action"]: b for b in o_change.get("buttons") or []}
                out["rules"]["other_server"] = {"apply_enabled": (buttons.get("apply") or {}).get("enabled"),
                                                "reason": (buttons.get("apply") or {}).get("reason"),
                                                "download": (buttons.get("download") or {}).get("enabled")}
            finally:
                other.close()
            # ---- the control, tried for real: a stored measurement whose classical control server is made to look hybrid
            sample = next((s for s in out["systems"].values() if s["kex"]), None)
            with lab.db() as db:
                run = db.scalars(select(TestRunRow).where(TestRunRow.plan_id == pid, TestRunRow.phase == "migration")
                                 .order_by(TestRunRow.id.desc()).limit(1)).first()
                if sample and run is not None and isinstance(run.raw.get("control"), dict) and "classical" in run.raw["control"]:
                    spec_row = db.get(TestSpecRow, run.spec_hash)
                    spec, _ = read_spec(spec_row)
                    record = json.loads(json.dumps(run_record(run)))
                    record["raw"]["control"]["classical"]["probes"]["hybrid"] = dict(record["raw"]["control"]["hybrid"]["probes"]["hybrid"])
                    review = lab.reviewer.review({"spec": spec, "spec_hash": run.spec_hash, "proposed_by": spec_row.proposed_by, "run": record})
                    out["control_misread_reads"] = "a status" if review["verdict"]["code"] in ("classical", "hybrid", "pq_only") else "Couldn't check"
            with lab.db() as db:
                plan_row = lab._plan(db, pid)
                states = lab._migration_states(db, plan_row)
                out["controls_read_right"] = all((s.get("result") or {}).get("control", {}).get("outcome") == "as_expected"
                                                 for s in states if s["status"])
            out["latest_review"] = "2030-12-31"
        except Exception as exc:
            out["stopped"] = f"The check stopped early: {str(exc) or exc.__class__.__name__}"
        finally:
            lab.stop()
    return out


def _twelve_months_after(day: str | None, latest: str) -> str | None:
    from datetime import date
    from app.migration import rules as migration_rules
    try:
        return min(migration_rules.default_review_date(date.fromisoformat(str(day))), date.fromisoformat(latest)).isoformat()
    except (TypeError, ValueError):
        return None


# ---- the clause grader for prose answers

def _band_words(text: str) -> str:
    return _norm(text).strip(" .")


def _grade_clause(clause: str, ctx: dict) -> tuple[bool | None, str]:
    """(matches?, what the app shows). None = this command doesn't understand the clause."""
    c = _norm(clause).rstrip(".")
    ch, sysa = ctx.get("change") or {}, ctx.get("system") or {}
    before, copy = ch.get("before") or {}, ch.get("copy") or {}
    m = re.fullmatch(r"passed: key exchange (.+?) -> (.+)", c)
    if m:
        got = f"{ch.get('try')}: {before.get('kex')} -> {copy.get('kex')}"
        return ch.get("try") == "passed" and _norm(before.get("kex")).startswith(m.group(1)) and _norm(copy.get("kex")) == m.group(2), got
    m = re.fullmatch(r"authentication unchanged, (.+)", c)
    if m:
        return _norm(before.get("auth")) == _norm(copy.get("auth")) == m.group(1), f"{before.get('auth')} -> {copy.get('auth')}"
    m = re.fullmatch(r"authentication (.+?) -> (.+)", c)
    if m:
        return (_norm(before.get("auth")).startswith(m.group(1)) and _norm(copy.get("auth")) == m.group(2)), f"{before.get('auth')} -> {copy.get('auth')}"
    if c == "classical-only clients still connect":
        return copy.get("classical_client") == "connects", f"classical-only clients on the copy: {copy.get('classical_client')}"
    if c == "classical-only and hybrid-only clients cant connect":
        return (copy.get("classical_client"), copy.get("hybrid_client")) == ("cannot", "cannot"), \
            f"classical-only: {copy.get('classical_client')}, hybrid-only: {copy.get('hybrid_client')}"
    m = re.fullmatch(r"key shares (?:become )?([\d,]+) and ([\d,]+) bytes(?: \(fips 203\))?", c)
    if m:
        want = (int(m.group(1).replace(",", "")), int(m.group(2).replace(",", "")))
        return tuple(copy.get("shares") or ()) == want, f"key shares on the copy: {copy.get('shares')}"
    m = re.fullmatch(r"handshake signature ([\d,]+) bytes(?: \(fips 204\))?", c)
    if m:
        return copy.get("signature_bytes") == int(m.group(1).replace(",", "")), f"handshake signature on the copy: {copy.get('signature_bytes')}"
    if c == "off until the try passed and every chosen reviewer approved":
        ok = bool(ch.get("refused_before_try")) and (ch.get("refused_with_some_approvals") is None or bool(ch.get("refused_with_some_approvals")))
        return ok, f"before the try: {ch.get('refused_before_try')}; with one approval: {ch.get('refused_with_some_approvals')}"
    if c in ("after apply the automatic re-measure matches the try", "re-measure matches the try"):
        return ch.get("after_apply") == "matches", f"after Apply: {ch.get('after_apply')}"
    if c == "fixes entry closed":
        return ch.get("fix_after_apply") == "In place (measured)", f"Fixes entry after Apply: {ch.get('fix_after_apply')}"
    if c == "fixes entry reopened":
        return ch.get("fix_after_rollback") not in (None, "In place (measured)"), f"Fixes entry after Roll back: {ch.get('fix_after_rollback')}"
    m = re.fullmatch(r"roadmap key exchange (.+?) and authentication (.+?)(?:, because the full post-quantum choice stays recorded: "
                     r"roll back undoes the server change, not the persons choice)?", c)
    if m:
        which = ch.get("roadmap_after_rollback") if ctx.get("step") == "Roll back" else ch.get("roadmap_after_apply")
        got = (_band_words((which or {}).get("Key exchange", "")), _band_words((which or {}).get("Authentication", "")))
        ok = got == (_band_words(m.group(1)), _band_words(m.group(2)))
        if "because" in c:
            ok = ok and ch.get("choice_after_rollback") == "full_pq"
            return ok, f"roadmap: {which}; the choice after Roll back: {ch.get('choice_after_rollback')}"
        return ok, f"roadmap: {which}"
    m = re.fullmatch(r"roadmap key exchange (?:back to )?(.+)", c)
    if m:
        which = ch.get("roadmap_after_rollback") if "back to" in c else ch.get("roadmap_after_apply")
        return _band_words((which or {}).get("Key exchange", "")) == _band_words(m.group(1)), f"roadmap: {which}"
    if c == "both tracks at the target":
        r = ch.get("roadmap_after_apply") or {}
        return r.get("Key exchange") == r.get("Authentication") == "At the target", f"roadmap after Apply: {r}"
    m = re.fullmatch(r"roadmap back to (.+) and (.+)", c)
    if m:
        r = ch.get("roadmap_after_rollback") or {}
        return (_band_words(r.get("Key exchange", "")), _band_words(r.get("Authentication", ""))) == (_band_words(m.group(1)), _band_words(m.group(2))), f"roadmap after Roll back: {r}"
    m = re.fullmatch(r"verifying the file again makes (mv\d) (true|false)", c)
    if m:
        system = {"mv1": "localhost:8451", "mv2": "localhost:8452"}.get(m.group(1))
        got = (ch.get("verify_after_apply") or {}).get(system)
        return _norm(got) == m.group(2), f"{m.group(1).upper()} after Apply: {got}"
    if c == "key exchange classical again":
        return (ch.get("after_rollback") or {}).get("kex") == "Classical" and ch.get("rollback") == "as_before", f"after Roll back: {(ch.get('after_rollback') or {}).get('kex')}"
    if c.startswith("hybrid plus classical key exchange and an ecdsa p-256 certificate again"):
        back = ch.get("after_rollback") or {}
        return (back.get("kex") == "Hybrid (interim)" and back.get("certificate") == "ECDSA P-256" and ch.get("rollback") == "as_before"), \
            f"after Roll back: {back.get('kex')}, certificate {back.get('certificate')}"
    # recommendation clauses
    rec_phrases = {"stay on hybrid (in place)": ("hybrid", True), "hybrid": ("hybrid", False), "keep classical for now": ("keep", False),
                   "wrap the connection": ("wrap", False), "full post-quantum, in place: keep it there": ("full_pq", True),
                   "full post-quantum, in place": ("full_pq", True), "hybrid: sign with both": ("hybrid", False),
                   "no recommendation: it couldnt be measured": (None, None), "no recommendation": (None, None)}
    if c in rec_phrases:
        option, place = rec_phrases[c]
        got = (sysa.get("recommended"), sysa.get("in_place"))
        ok = got == (option, place) if option else sysa.get("recommended") is None
        if c.endswith("keep it there"):
            ok = ok and all("keep it there" in v for v in (sysa.get("next") or {}).values())
        return ok, f"recommended {sysa.get('recommended')}, in place {sysa.get('in_place')}"
    m = re.fullmatch(r"next for (key exchange|authentication): (.+)", c)
    if m:
        track = "kex" if m.group(1) == "key exchange" else "auth"
        text = (sysa.get("next") or {}).get(track, "") + " " + (sysa.get("why") or {}).get(track, "")
        return _words_in(m.group(2), text), f"next: {(sysa.get('next') or {}).get(track)}"
    m = re.fullmatch(r"review date (.+)", c)
    if m and m.group(1) == _norm(REVIEW_DATE_RULE):
        should = _twelve_months_after(ctx.get("measured_on"), "2030-12-31")
        return sysa.get("review_date") == should, f"review date {sysa.get('review_date')} (expected {should})"
    if c == "(it cant be changed)" or c == "it cant be changed":
        return sysa.get("can_change") == "no", f"can it be changed: {sysa.get('can_change')}"
    if c == "blocked until the library can make post-quantum signatures":
        return any("post-quantum signatures" in "".join(p["v"] for p in l) for l in sysa.get("blockers") or []), "blockers listed"  # noqa: E741
    return None, ""


def _clauses(text: str) -> list[str]:
    """Split a prose answer into clauses: at "; ", and "X, Y" when X is a known recommendation phrase."""
    out = []
    for part in [p.strip() for p in str(text).split(";") if p.strip()]:
        m = re.fullmatch(r"(Keep classical for now), (review date .+)", part)
        if m:
            out += [m.group(1), m.group(2)]
            continue
        m = re.fullmatch(r"(Wrap the connection) (\(it can't be changed\))", part)
        if m:
            out += [m.group(1), m.group(2)]
            continue
        m = re.fullmatch(r"(Hybrid: sign with both), (blocked until .+)", part)
        if m:
            out += [m.group(1), m.group(2)]
            continue
        out.append(part)
    return out


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
        if part not in expected:
            add("?", f"the part {part!r} of the answer key", "(present)", None, False, "missing from the answer key")
    for entry in expected.get("verify") or []:
        got = (systems.get(entry.get("system")) or {}).get("verify")
        add(entry["id"], f"verify: {entry['system']}", entry["expected"], got, got == entry["expected"])
    for entry in expected.get("tracks") or []:
        got = systems.get(entry.get("system")) or {}
        problems, shown = [], []
        for field, want in entry.items():
            if field in ("id", "system"):
                continue
            if field in TRACK_KEYS:
                have = got.get(TRACK_KEYS[field])
            elif field == "classical_only_client_connects":
                have = got.get("classical_client")
            elif field == "default_choice":
                have = got.get("default_choice")
            else:
                problems.append(f"the key's field {field!r} is not one this command knows")
                continue
            shown.append(f"{field}: {have}")
            if _norm(have) != _norm(want):
                problems.append(f"{field}: the key says {want!r}, the app shows {have!r}")
        add(entry["id"], f"tracks: {entry['system']}", {k: v for k, v in entry.items() if k not in ("id", "system")}, "; ".join(shown),
            not problems, "; ".join(problems) or None)
    if "never_done" in expected:
        nd = answers.get("never_done") or {}
        ok = not nd.get("already_there_shown") and not nd.get("tracks_without_next_or_why") and not nd.get("target_tracks_not_keep")
        add("never_done", "No system is ever done", expected["never_done"],
            f"'Already there' shown: {nd.get('already_there_shown')}; tracks without Next or Why: {nd.get('tracks_without_next_or_why')}; "
            f"target tracks not saying keep it there: {nd.get('target_tracks_not_keep')}", ok)
    for entry in expected.get("recommendation") or []:
        sysa = systems.get(entry.get("system")) or {}
        results = [(cl, *_grade_clause(cl, {"system": sysa, "measured_on": answers.get("measured_on")})) for cl in _clauses(entry["expected"])]
        results = results or [("(empty)", None, "")]
        problems = [f"{cl!r}: " + ("this command doesn't understand this clause" if ok is None else f"the app shows {got}") for cl, ok, got in results if not ok]
        add(entry["id"], f"recommendation: {entry['system']}", entry["expected"], sysa.get("recommendation_title"), not problems, "; ".join(problems) or None)
    for entry in expected.get("roadmap") or []:
        got = (systems.get(entry.get("system")) or {}).get("roadmap") or {}
        problems = []
        for field, want in entry.items():
            if field in ("id", "system"):
                continue
            label = {"key_exchange": ["Key exchange", "Both tracks"], "authentication": ["Authentication", "Both tracks"],
                     "signatures": ["Signatures"]}.get(field)
            if label is None:
                problems.append(f"the key's field {field!r} is not one this command knows")
                continue
            have = next((got[l] for l in label if l in got), None)  # noqa: E741
            if have != want:
                problems.append(f"{field}: the key says {want!r}, the app places it in {have!r}")
        add(entry["id"], f"roadmap: {entry['system']}", {k: v for k, v in entry.items() if k not in ("id", "system")}, got, not problems,
            "; ".join(problems) or None)
    tests = answers.get("tests") or {}
    for entry in expected.get("tests_step") or []:
        if "readiness" in entry:
            got = (tests.get("readiness") or {}).get(entry["system"])
            add(entry["id"], f"Tests: Post-quantum readiness on {entry['system']}", entry["readiness"], got, got == entry["readiness"])
            continue
        want = _norm(entry.get("expected"))
        m = re.match(r"(\d+) suggested tests", want)
        ok = bool(m) and tests.get("count") == int(m.group(1))
        ok = ok and tests.get("kinds", []).count("pq_readiness") == 5 and tests.get("kinds", []).count("official_vectors") == 1
        ok = ok and any("acme-sign 9.9" in line for line in tests.get("not_tested") or []) and not any("9.9" in g for g in tests.get("groups") or [])
        if not m or "post-quantum readiness on each of the five servers" not in want or "acme-sign 9.9 only in not tested, and why" not in want:
            add(entry["id"], "Tests step", entry.get("expected"), tests.get("count"), False, "this command doesn't understand this answer")
        else:
            add(entry["id"], "Tests step", entry["expected"], f"{tests.get('count')} tests: {tests.get('kinds')}", ok)
    for part, system in (("change_8452_to_hybrid", "localhost:8452"), ("change_8451_to_full_post_quantum", "localhost:8451")):
        change = (answers.get("changes") or {}).get(system) or {}
        for entry in expected.get(part) or []:
            parts = [p.strip() for p in re.split(r";\s*", str(entry["expected"])) if p.strip()]
            results = [(cl, *_grade_clause(cl, {"change": change, "system": systems.get(system), "step": entry.get("step")})) for cl in parts]
            problems = [f"{cl!r}: " + ("this command doesn't understand this clause" if ok is None else f"the app shows {got}") for cl, ok, got in results if not ok]
            add(entry["id"], f"{system}, {entry.get('step')}", entry["expected"], "; ".join(got for _, _, got in results if got), not problems,
                "; ".join(problems) or None)
    rules = answers.get("rules") or {}
    for name, text in (expected.get("rules") or {}).items():
        if name == "apply_gate":
            ch = (answers.get("changes") or {}).get("localhost:8452") or {}
            ok = bool(ch.get("refused_before_try")) and bool(ch.get("refused_with_some_approvals"))
            got = f"before the try: {ch.get('refused_before_try')}; with one of two approvals: {ch.get('refused_with_some_approvals')}"
        elif name == "other_servers":
            other = rules.get("other_server") or {}
            ok = other.get("apply_enabled") is False and "connector" in str(other.get("reason")) and other.get("download") is True
            got = f"Apply enabled: {other.get('apply_enabled')}; reason: {other.get('reason')}; Download: {other.get('download')}"
        elif name == "test_keys":
            ok, got = rules.get("keys_in_evidence") is False, f"a key found in the evidence, report or downloads: {rules.get('keys_in_evidence')}"
        elif name == "records":
            rec = rules.get("records") or {}
            ok, got = bool(rec) and all(rec.values()), f"in the signed evidence: {rec}"
        else:
            add(f"rule {name}", text, text, None, False, "this command doesn't know that rule")
            continue
        add(f"rule {name}", text, "holds", got, ok)
    if "controls" in expected:
        misread = answers.get("control_misread_reads")
        ok = bool(answers.get("controls_read_right")) and misread == "Couldn't check"
        add("controls", (expected.get("controls") or {}).get("expected", "the controls"), "controls read correctly; a misread control reads Couldn't check",
            f"controls {'read correctly' if answers.get('controls_read_right') else 'NOT all read correctly'}; a misread control reads {misread}", ok)
    return {"lines": lines, "matched": sum(1 for line in lines if line["match"]), "total": len(lines)}


def print_migration_report(settings: Settings | None, say=print) -> int:
    """The migration demo against demo/expected-migration.json. Exit code 0 only if the key is there and all match."""
    from app import config
    say("")
    say("Migration demo accuracy check against demo/expected-migration.json (Verify, two tracks, recommendations, roadmap, Tests, "
        "try, Apply, Roll back, rules, controls)")
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
    parser.add_argument("--only", choices=("acme", "migration", "real", "dependencies"), default=None,
                        help="acme = only the Acme Pay demo (demo/expected.json); migration = only the migration demo "
                             "(demo/expected-migration.json); real = only the real libraries "
                             "(demo/expected-real-libraries.json); dependencies = only the dependency lists "
                             "(demo/expected-dependencies.json). Default: all four.")
    parser.add_argument("--mode", choices=("auto", "demo", "isolated"), default=None,
                        help="demo = local processes; isolated = containers (needs Docker and the prepared images); "
                             "auto = isolated when it is available. Default: the EVIDENCE_LAB_MODE setting, else auto.")
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.mode is not None:
        settings = dataclasses.replace(settings, force_mode=None if args.mode == "auto" else args.mode)
    codes = []
    if args.only in (None, "acme"):
        codes.append(print_report(run_accuracy(settings)))
    if args.only in (None, "migration"):
        codes.append(print_migration_report(settings))
    if args.only in (None, "real"):
        from app.accuracy_real import print_real_report   # phase 4c: the real libraries (isolated mode; in demo mode only RD1 applies)
        codes.append(print_real_report(settings))
    if args.only in (None, "dependencies"):
        from app.accuracy_deps import print_dependencies_report   # phase 4d: the dependency lists (both modes)
        codes.append(print_dependencies_report(settings))
    return max(codes)


if __name__ == "__main__":
    sys.exit(main())
