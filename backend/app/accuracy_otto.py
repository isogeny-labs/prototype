"""Accuracy check, fifth part (phase 5c): Otto's loop against demo/expected-otto.json.

Called by `python -m app.accuracy` (or alone with `--only otto`). It goes down the same path as the buttons, on a
scratch database, and writes down what the app answers as a flat list of named questions (docs/OTTO-KEY.md lists
every question and the values an answer can take):

  - the two shipped test packs: their order, each advisory's test and fix state, the trial figures the packs carry,
    and that a changed pack, a pack signed by an unknown key and a pack installed out of order are refused;
  - the Acme Pay demo file: Check for updates, Install, Add new checks, Run all; the fix for the failed advisory
    check (whether Otto's own change is offered, and what is connected), its proof, approval, merge and Retest now;
    the second pack; the evidence file and the verify command on it and on changed copies, and --previous;
  - the Real libraries file (isolated mode only): every advisory check on every library, the fixes Otto proposes, and
    the three retests. In demo mode a real library's advisory check must read "Couldn't run (needs isolated mode)".

The answer key is written independently of the build (it is not in the repository until its author adds it) and is
never written here. With no key, the answers are printed and nothing is graded. Otto must be installed: without the
pinned harness an advisory check can't be added, so there is nothing to grade.
"""
from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import tempfile
from pathlib import Path

from sqlalchemy import select

from app.canonical import canonical_bytes
from app.config import DEMO_DIR, Settings, load_settings
from app.db import OttoStepRow, ReviewRow
from app.errors import Conflict
from app.evidence.export import sign_envelope
from app.lab.hub import Lab
from app.otto import harness, packs

EXPECTED_OTTO_JSON = DEMO_DIR / "expected-otto.json"   # the fifth answer key: read-only, never written by the app
REAL_FILE = DEMO_DIR / "real-libraries.csv"
WAIT_SECONDS = 1500.0
RETESTS = (("openjdk", "17.0.3"), ("python-ecdsa", "0.13.3"), ("elliptic", "6.5.7"))
NO_OTTO, NO_KEY = 3, 2
BANNED = ("secure", "score", "severity", "critical", "time to hack")


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


def _wrong(lab: Lab, result: dict | None) -> list[str]:
    """The cases a reviewed run got wrong, from the reviewer's own detail (only while the stored review stands)."""
    if not result:
        return []
    with lab.db() as db:
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == result["run_id"])).first()
    if review is None or review.code != result["code"]:
        return []
    return [str(w.get("id")) for w in (review.detail or {}).get("wrong") or []]


def _assessment_id(lab: Lab, plan_id: int) -> int:
    row = lab.assessment_for(plan_id=plan_id)
    if row is None:
        raise RuntimeError("the plan belongs to no assessment")
    return row.id


def _own_change(fix: dict | None) -> str:
    """Whether the change Otto wrote for the customer's own code is offered, and if not, which of the app's reasons applies."""
    if fix is None:
        return "no code fix"
    if fix.get("otto"):
        return "offered"
    note = str(fix.get("otto_note") or "")
    if "byte for byte" in note:
        return "not offered: the program it gives is not one of our registered demo programs"
    if "No recorded answer" in note:
        return "not offered: no recorded answer"
    return "not offered: the answer was not a clean change" if note else "not asked"


def _advisory_rows(lab: Lab, plan_id: int) -> dict[tuple[str, str], dict]:
    """{(program label, advisory id): the Evidence Lab row} for the advisory checks of one plan."""
    view = lab.lab_view(plan_id)
    label = {g["key"]: g["heading"].split(": ", 1)[-1] for g in view.get("groups") or []}
    out = {}
    for row in view["rows"]:
        if row["kind"] != "advisory_cases":
            continue
        shown = row.get("after") or row.get("result")
        advisory = (((shown or row.get("result") or {}).get("advisories") or {}).get("items") or [{}])[0].get("id")
        if advisory is None:
            advisory = row["title"].rsplit("(", 1)[-1].rstrip(")")
        out[(label.get(row.get("group"), view.get("component") or "the program"), advisory)] = row
    return out


def _verify(args: list[str]) -> tuple[int, str]:
    """The verify command, run in this process: (its exit code, what it printed)."""
    from evidence.__main__ import main
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = main(args)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, out.getvalue()


def _packs_part(settings: Settings, answers: dict, notes: list[str]) -> list[packs.Pack]:
    found, refused = packs.found_in(settings.otto_updates, packs.trusted_keys(settings.data_dir))
    for bad in refused:
        notes.append(f"A file in the updates folder was refused: {bad['file']}: {bad['reason']}")
    answers["packs.order"] = [p.version for p in found]
    for pack in found:
        for advisory in pack.pack["advisories"]:
            key = f"pack.{pack.version}.{advisory['id']}"
            answers[f"{key}.test"] = advisory["test"]["state"]
            answers[f"{key}.fix"] = advisory["fix"]["state"]
            trial = advisory["test"]["trial"]
            if trial is not None:
                arms = trial["arms"]
                answers[f"trial.{advisory['id']}.outcome"] = trial["outcome"]
                answers[f"trial.{advisory['id']}.replayed"] = bool(trial["replayed"])
                answers[f"trial.{advisory['id']}.affected_wrong"] = arms["affected"].get("wrong")
                answers[f"trial.{advisory['id']}.fixed_wrong"] = arms["fixed"].get("wrong")
                control, total = arms["accept-all"].get("wrong"), arms["accept-all"].get("total")
                answers[f"trial.{advisory['id']}.control_wrong_on_every_case"] = control is not None and control == total
            fix_trial = advisory["fix"]["trial"]
            if fix_trial is not None:
                answers[f"fixtrial.{advisory['id']}.outcome"] = fix_trial["outcome"]
                answers[f"fixtrial.{advisory['id']}.failing_before"] = fix_trial["arms"]["affected"].get("failing")
                answers[f"fixtrial.{advisory['id']}.failing_after"] = fix_trial["arms"]["fixed"].get("failing")
    if found:
        first = found[0]
        raw = canonical_bytes(first.envelope)
        marker = b'"plain_name":"'
        at = raw.find(marker) + len(marker)
        changed = raw[:at] + bytes([raw[at] ^ 0x01]) + raw[at + 1:]
        for name, data, keys in (("pack.refused.one_byte_changed", changed, packs.trusted_keys(settings.data_dir)),
                                 ("pack.refused.unknown_key", raw, {})):
            try:
                packs.read_envelope(data, keys)
                answers[name] = "accepted"
            except packs.PackError:
                answers[name] = "refused"
    return found


def _acme_walk(settings: Settings, answers: dict, notes: list[str], found: list[packs.Pack], progress) -> None:
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        lab = Lab(dataclasses.replace(settings, data_dir=Path(scratch) / "data"), allow_external_demo_server=True)
        lab.start()
        try:
            imp = lab.import_demo()
            for address in imp["addresses"]:
                lab.confirm_address(imp["id"], address["address"], True)
            lab.verify(imp["id"])
            pid = lab.ensure_plan(imp["id"])["id"]
            if len(found) > 1:
                try:
                    lab.install_pack(found[1].version)
                    answers["pack.refused.out_of_order"] = "accepted"
                except Conflict:
                    answers["pack.refused.out_of_order"] = "refused"
            progress("  ... Acme Pay: Check for updates, Install, Add new checks, Run all")
            update = lab.check_pack_updates()["packs"]["update"]
            answers["acme.update_found"] = update["version"] if update else None
            lab.install_pack(found[0].version)
            view = lab.add_new_checks(pid)
            answers["acme.checks_added_from_first_pack"] = sum(1 for r in view["rows"] if r["result"]["key"] == "not_run")
            lab.run_all(pid)
            lab.wait_until_idle(pid, WAIT_SECONDS)
            first = _advisory_rows(lab, pid)
            for (program, advisory), row in first.items():
                answers[f"acme.first.{advisory}.result"] = (row["result"] or {}).get("label")
                answers[f"acme.first.{advisory}.wrong_cases"] = _wrong(lab, row["result"])
                answers[f"acme.first.{advisory}.program"] = (row["result"] or {}).get("component") or program
            shown = [t for r in first.values() for t in _texts(r["result"])]
            answers["acme.wording.no_banned_words"] = not any(w in t.lower() for t in shown for w in BANNED)
            progress("  ... Acme Pay: the fix (connect the code, proof, pull request, approvals, merge, Retest now)")
            fix = next((f for f in lab.fix_states(pid) if f["kind"] == "code"), None)
            answers["acme.fix.written_by_before_connect"] = "otto" if fix and fix.get("otto") else "fix_template" if fix else None
            answers["acme.fix.ottos_own_change"] = _own_change(fix)
            if fix is not None:
                lab.connect_code(pid)
                lab.wait_until_idle(pid, WAIT_SECONDS)
                fix = next(f for f in lab.fix_states(pid) if f["kind"] == "code")
                fix_id = fix["id"]
                answers["acme.fix.written_by"] = fix["change"]["written_by"]
                answers["acme.fix.label"] = next(f for f in lab.fixes_view(pid)["fixes"] if f["id"] == fix_id)["labels"]
                answers["acme.fix.changed_code_is"] = (fix["change"]["built"]["matches"] or {}).get("version")
                review = (fix.get("proof") or {}).get("review") or {}
                answers["acme.fix.offered_after_proof"] = bool(review.get("offered"))
                answers["acme.fix.proof_reran_advisory_checks"] = sum(1 for t in review.get("tests") or [] if t["kind"] == "advisory_cases")
                answers["acme.fix.proof_advisory_checks_ok"] = all(t["ok"] for t in review.get("tests") or [] if t["kind"] == "advisory_cases")
                answers["acme.fix.status"] = fix["status"]
                with lab.db() as db:    # what was kept of Claude's step when the person connected the code
                    answers["acme.fix.ottos_step_kept_as"] = [s.outcome for s in db.scalars(select(OttoStepRow).order_by(OttoStepRow.id))]
                if fix["status"] == "ready":
                    lab.open_pull_request(pid, fix_id, ["a", "you"])
                    lab.approve(pid, fix_id, "you")
                    lab.approve(pid, fix_id, "a")
                    lab.merge(pid, fix_id)
                    lab.retest_now(pid, fix_id)
                    lab.wait_until_idle(pid, WAIT_SECONDS)
                    for (_, advisory), row in _advisory_rows(lab, pid).items():
                        answers[f"acme.after_merge.{advisory}.result"] = (row["after"] or {}).get("label")
                        answers[f"acme.after_merge.{advisory}.program"] = (row["after"] or {}).get("component")
                        answers[f"acme.after_merge.{advisory}.same_locked_test"] = bool(
                            row["result"] and row["after"] and row["result"]["locked_test"]["fingerprint"] == row["after"]["locked_test"]["fingerprint"])
            older_raw = lab.evidence_file(lab.export_evidence(pid)["id"], "json")[1]
            if len(found) > 1:
                progress("  ... Acme Pay: the second pack")
                lab.install_pack(found[1].version)
                # every earlier step has a result by now, so the Overview's next step is the new pack's checks
                answers["acme.second_pack.next_step_page"] = lab.assessment_view(_assessment_id(lab, pid))["next_step"]["page"]
                answers["acme.second_pack.checks_ready_to_add"] = lab.otto_new_checks(pid)
                before = set(_advisory_rows(lab, pid))
                lab.add_new_checks(pid)
                added = [key for key in _advisory_rows(lab, pid) if key not in before]
                answers["acme.checks_added_from_second_pack"] = len(added)
                lab.run_all(pid)
                lab.wait_until_idle(pid, WAIT_SECONDS)
                rows = _advisory_rows(lab, pid)
                for key in added:
                    answers[f"acme.second_pack.{key[1]}.result"] = (rows[key]["result"] or {}).get("label")
                    answers[f"acme.second_pack.{key[1]}.program"] = (rows[key]["result"] or {}).get("component")
            progress("  ... Acme Pay: Download evidence, and the verify command on it and on changed copies")
            folder = Path(scratch) / "files"
            folder.mkdir()
            newer_raw = lab.evidence_file(lab.export_evidence(pid)["id"], "json")[1]
            (folder / "older.json").write_bytes(older_raw)
            (folder / "newer.json").write_bytes(newer_raw)
            data = ["--data-dir", str(lab.settings.data_dir)]
            answers["evidence.fresh_download"] = _verify(["verify", str(folder / "newer.json"), *data])[0]
            changed = bytearray(newer_raw)
            changed[newer_raw.index(b'"otto"') + 60] ^= 0x01
            (folder / "byte.json").write_bytes(bytes(changed))
            answers["evidence.one_byte_changed"] = _verify(["verify", str(folder / "byte.json"), *data])[0]

            def resigned(change) -> int:
                evidence = json.loads(newer_raw)["evidence"]
                change(evidence["otto"])
                (folder / "changed.json").write_bytes(sign_envelope(evidence, lab.settings.data_dir))
                return _verify(["verify", str(folder / "changed.json"), *data])[0]

            def line_changed(otto: dict) -> None:
                otto["ledger"]["lines"][1] = otto["ledger"]["lines"][1].replace('"phase":"first"', '"phase":"retest"', 1).replace(
                    '"advisory":"', '"advisory":"X', 1)

            def line_removed(otto: dict) -> None:
                del otto["ledger"]["lines"][1]
                otto["ledger"]["height"] -= 1

            def pack_swapped(otto: dict) -> None:
                otto["packs"] = [json.loads(canonical_bytes(found[-1].envelope))] if len(found) > 1 else []
                otto["packs"] = otto["packs"][:1] if len(otto["packs"]) > 1 else otto["packs"]

            answers["evidence.ledger_line_changed_and_signed_again"] = resigned(line_changed)
            answers["evidence.ledger_line_removed_and_signed_again"] = resigned(line_removed)
            answers["evidence.pack_swapped_and_signed_again"] = resigned(pack_swapped)
            answers["evidence.previous_later_download"] = _verify(["verify", str(folder / "newer.json"), "--previous", str(folder / "older.json"), *data])[0]
            answers["evidence.previous_with_a_shorter_ledger"] = _verify(["verify", str(folder / "older.json"), "--previous", str(folder / "newer.json"), *data])[0]
        finally:
            lab.stop()


def _real_walk(settings: Settings, answers: dict, notes: list[str], found: list[packs.Pack], progress) -> None:
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        lab = Lab(dataclasses.replace(settings, data_dir=Path(scratch) / "data"), allow_external_demo_server=True)
        lab.start()
        try:
            imp = lab.import_file(REAL_FILE.name, REAL_FILE.read_bytes())
            pid = lab.ensure_plan(imp["id"])["id"]
            for pack in found:
                lab.check_pack_updates()
                lab.install_pack(pack.version)
            lab.add_new_checks(pid)
            if lab.mode.name != "isolated":
                progress("  ... Real libraries, in demo mode: an advisory check on a real library must not run")
                item = next(t["id"] for t in lab.plan_view(pid)["tests"] if t["kind"] == "advisory_cases")
                lab.run_test(pid, item)
                lab.wait_until_idle(pid, 300.0)
                row = next(r for r in lab.lab_view(pid)["rows"] if r["item_id"] == item)
                answers["real.demo_mode.advisory_check_on_a_real_library"] = (row["result"] or {}).get("label")
                notes.append("This run is in demo mode. Real libraries run only in isolated mode (Docker), so only the demo-mode answer applies here.")
                return
            progress(f"  ... Real libraries: Run all ({len(lab.plan_view(pid)['tests'])} tests)")
            lab.run_all(pid)
            lab.wait_until_idle(pid, WAIT_SECONDS)
            for (program, advisory), row in _advisory_rows(lab, pid).items():
                answers[f"real.first.{program}.{advisory}.result"] = (row["result"] or {}).get("label")
                answers[f"real.first.{program}.{advisory}.wrong_cases"] = _wrong(lab, row["result"])
            for fix in lab.fixes_view(pid)["fixes"]:
                if "From Otto" in (fix.get("labels") or []):
                    answers[f"real.fix.{fix['title']}"] = fix["labels"]
            answers["real.fixes_from_otto"] = sorted(f["title"] for f in lab.fixes_view(pid)["fixes"] if "From Otto" in (f.get("labels") or []))
            for name, version in RETESTS:
                progress(f"  ... Real libraries: Retest new version: {name} {version}")
                lab.start_retest(pid, version, name)
                lab.wait_until_idle(pid, WAIT_SECONDS)
                for (program, advisory), row in _advisory_rows(lab, pid).items():
                    if program.startswith(name + " "):
                        answers[f"real.retest.{name} {version}.{advisory}.result"] = (row["after"] or {}).get("label")
                        answers[f"real.retest.{name} {version}.{advisory}.wrong_cases"] = _wrong(lab, row["after"])
        finally:
            lab.stop()


def collect_otto(settings: Settings | None = None, say=None) -> dict:
    """Walk Otto's loop once through the Lab service path and return the app's answers by question."""
    settings = settings or load_settings()
    progress = say or (lambda text: None)
    out: dict = {"mode": None, "notes": [], "stopped": None, "answers": {}}
    try:
        from app.run import runner
        out["mode"] = runner.detect_mode(settings).name
        found = _packs_part(settings, out["answers"], out["notes"])
        if not found:
            out["stopped"] = "No test pack was found in the updates folder (research/packs)."
            return out
        _acme_walk(settings, out["answers"], out["notes"], found, progress)
        _real_walk(settings, out["answers"], out["notes"], found, progress)
    except Exception as exc:  # shown, never hidden: every answer not reached counts as a mismatch
        out["stopped"] = f"The check stopped early: {str(exc) or exc.__class__.__name__}"
    return out


def compare_otto(expected: object, answers: dict) -> dict:
    """Grade the answers against the key: {"answers": {question: expected value}} (docs/OTTO-KEY.md). A question the key
    holds and the app did not answer is a mismatch. A question that applies in the other mode only is listed, not graded."""
    wanted = expected.get("answers") if isinstance(expected, dict) else None
    lines = []
    if not isinstance(wanted, dict):
        return {"lines": [{"id": "key", "match": False, "expected": "an object named answers", "actual": type(wanted).__name__,
                           "what": "the answer key is not in the form docs/OTTO-KEY.md describes"}], "matched": 0, "total": 1, "not_applicable": 0}
    skipped = 0
    for question in sorted(wanted):
        isolated_only = question.startswith(("real.first.", "real.retest.", "real.fix"))
        demo_only = question.startswith("real.demo_mode.")
        if (isolated_only and "real.demo_mode.advisory_check_on_a_real_library" in answers) or (demo_only and question not in answers):
            skipped += 1
            continue
        actual = answers.get(question, "(no answer)")
        lines.append({"id": question, "match": actual == wanted[question], "expected": wanted[question], "actual": actual, "what": ""})
    return {"lines": lines, "matched": sum(1 for line in lines if line["match"]), "total": len(lines), "not_applicable": skipped}


def print_otto_report(settings: Settings | None, say=print, required: bool = False) -> int:
    """Otto's loop against demo/expected-otto.json. `required`: the command was asked for this part alone.
    Exit code 0 only if the key is there and all match; 3 when Otto is not installed and this part was asked for."""
    say("")
    say("Otto accuracy check against demo/expected-otto.json (test packs, trials, advisory checks, the fix, the evidence file)")
    status = harness.status()
    if not status.installed:
        say(f"  NOT RUN  {status.sentence} Advisory checks can't be added without it, so Otto's answers are not graded here.")
        say("Otto accuracy: not run (Otto is not installed)")
        return NO_OTTO if required else 0
    collected = collect_otto(settings, say)
    answers = collected["answers"]
    say(f"  mode: {collected['mode']}")
    for note in collected["notes"]:
        say(f"  note: {note}")
    if collected["stopped"]:
        say(f"  PROBLEM  {collected['stopped']}")
    if not EXPECTED_OTTO_JSON.exists():
        for question in sorted(answers):
            say(f"  {question} = {json.dumps(answers[question], ensure_ascii=False)}")
        say("  NOT COMPARED  demo/expected-otto.json is not in this copy of the repository. It is written independently of the build "
            "(docs/OTTO-KEY.md lists the questions); until it is there, the answers above are shown and nothing is graded.")
        say(f"Otto accuracy: not compared (answer key missing); {len(answers)} answers collected" + ("; the walk stopped early" if collected["stopped"] else ""))
        return (NO_KEY if required else 0) if not collected["stopped"] else 1
    try:
        expected = json.loads(EXPECTED_OTTO_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        say(f"  PROBLEM  the answer key could not be read ({exc.__class__.__name__}).")
        return 1
    report = compare_otto(expected, answers)
    for line in report["lines"]:
        say(f"  {'MATCH   ' if line['match'] else 'MISMATCH'}  {line['id']}: expected {line['expected']!r}, app says {line['actual']!r}")
    if report["not_applicable"]:
        say(f"  {report['not_applicable']} questions of the key apply in the other mode only and were not graded.")
    say(f"Otto accuracy ({collected['mode']} mode): {report['matched']} of {report['total']} match")
    return 0 if report["matched"] == report["total"] and report["total"] and not collected["stopped"] else 1


__all__ = ["collect_otto", "compare_otto", "print_otto_report", "EXPECTED_OTTO_JSON"]
