"""Accuracy check, fifth part (phase 5c): Otto's loop against demo/expected-otto.json.

Called by `python -m app.accuracy` (or alone with `--only otto`). It goes down the same path as the buttons, on a
scratch database, and writes down what the app answers as a flat list of named questions (docs/OTTO-KEY.md lists
every question and the values an answer can take):

  - the two shipped test packs: their order, each advisory's test and fix state, the trial figures the packs carry,
    and that a changed pack, a pack signed by an unknown key and a pack installed out of order are refused;
  - the Acme Pay demo file: Check for updates, Install; Otto's proposed checks, each decided by itself (accept,
    reject with a reason, undo, reconsider; accepting runs nothing); Run all; Otto's proposed fix for the failed
    advisory check (refused before its accept; then accepted, connected, proven, approved, merged, Retest now);
    Otto's proposed change to the migration plan; the second pack and the check it proposes; the demo dependency
    list, the libraries an advisory names and Otto's proposed updates (one accepted, one rejected with a reason); the
    evidence file with every decision in it, and the verify command on it and on changed copies, and --previous;
  - the Real libraries file (isolated mode only): every advisory check on every library, the fixes Otto proposes with
    their two proof rows, and the three retests. In demo mode a real library's advisory check must read
    "Couldn't run (needs isolated mode)".

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
DEPENDENCIES_FILE = DEMO_DIR / "dependencies-demo.cdx.json"      # the Acme Pay demo's dependency list (Demo data)
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


def _proposed(lab: Lab, plan_id: int, kind: str) -> list[dict]:
    """Otto's proposals of one kind in this assessment, as the app works them out now."""
    return [p for p in lab.otto_proposals(plan_id, (kind,)) if p["current"]]


def _status(lab: Lab, plan_id: int, proposal_id: str) -> str:
    """The word a screen shows for where one proposal stands ("Proposed", "Added", "Accepted", "Not added (reason)")."""
    return next(p["status"]["word"] for p in lab.otto_proposals_view(plan_id)["proposals"] if p["id"] == proposal_id)


def _accept_each_check(lab: Lab, plan_id: int) -> int:
    """Accept every proposed check, one decision at a time (there is no button that decides several). Returns how many."""
    waiting = [p for p in _proposed(lab, plan_id, "check") if p["state"] == "proposed"]
    for proposal in waiting:
        lab.otto_decide(plan_id, proposal["id"], "accept")
    return len(waiting)


def _runs(lab: Lab, plan_id: int) -> int:
    from sqlalchemy import func

    from app.db import TestRunRow
    with lab.db() as db:
        return int(db.scalar(select(func.count(TestRunRow.id)).where(TestRunRow.plan_id == plan_id)) or 0)


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
            progress("  ... Acme Pay: Check for updates, Install, Otto's proposed checks (accept, reject, undo, reconsider), Run all")
            update = lab.check_pack_updates()["packs"]["update"]
            answers["acme.update_found"] = update["version"] if update else None
            lab.install_pack(found[0].version)
            answers["acme.import.checks_that_may_apply"] = lab.import_json_for(imp["id"])["otto"]["count"]
            runs_before = _runs(lab, pid)
            proposed = _proposed(lab, pid, "check")
            answers["acme.proposals.checks_proposed_from_first_pack"] = len(proposed)
            answers["acme.proposals.every_check_says_why_it_applies"] = all(p["why"].strip() for p in proposed)
            answers["acme.waiting_for_you.before_any_decision"] = lab.assessment_view(_assessment_id(lab, pid))["waiting"]["total"]
            if len(proposed) >= 2:
                first_id, second_id = proposed[0]["id"], proposed[1]["id"]
                lab.otto_decide(pid, first_id, "accept")
                answers["acme.decision.accept.status"] = _status(lab, pid, first_id)
                lab.otto_decide(pid, second_id, "reject", "Not this quarter")
                answers["acme.decision.reject.status"] = _status(lab, pid, second_id)
                answers["acme.decision.reject.kept_on_record"] = any(p["id"] == second_id for p in lab.otto_proposals(pid, ("check",)))
                lab.otto_decide(pid, first_id, "undo")
                answers["acme.decision.undo.status"] = _status(lab, pid, first_id)
                answers["acme.decision.undo.check_left_the_plan"] = not any(t["kind"] == "advisory_cases" for t in lab.plan_view(pid)["tests"])
                lab.otto_decide(pid, first_id, "accept")
                lab.otto_decide(pid, second_id, "reconsider")
                answers["acme.decision.reconsider.status"] = _status(lab, pid, second_id)
                lab.otto_decide(pid, second_id, "accept")
            _accept_each_check(lab, pid)
            view = lab.advisories_view(pid)
            answers["acme.checks_added_from_first_pack"] = sum(1 for r in view["rows"] if r["result"]["key"] == "not_run")
            answers["acme.decision.accepting_ran_nothing"] = _runs(lab, pid) == runs_before
            answers["acme.checks.marked_from_otto"] = sum(1 for t in lab.plan_view(pid)["tests"] if t.get("from_otto") == "From Otto")
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
            # after the first run an accepted check can no longer be undone
            ran = next((p for p in _proposed(lab, pid, "check") if p["state"] == "accepted"), None)
            answers["acme.decision.undo_after_a_run"] = "refused" if ran is not None and ran["actions"].get("undo") else "allowed"
            fix_proposal = next((p for p in _proposed(lab, pid, "fix")), None)
            answers["acme.fix.proposal.status_before_a_decision"] = _status(lab, pid, fix_proposal["id"]) if fix_proposal else None
            # A change to a system's plan needs a plan: nothing is proposed until Measure status has placed the system.
            answers["acme.plan.proposal.made_before_the_status_is_measured"] = next((p for p in _proposed(lab, pid, "plan")), None) is not None
            lab.measure_migration(pid)                       # the Measure status button
            lab.wait_until_measured(pid, 300)
            plan_proposal = next((p for p in _proposed(lab, pid, "plan")), None)
            answers["acme.plan.proposal.made_after_the_failed_check"] = plan_proposal is not None
            if fix is not None and fix_proposal is not None:
                try:
                    lab.connect_code(pid)
                    answers["acme.fix.connect_before_accept"] = "connected"
                except Conflict:
                    answers["acme.fix.connect_before_accept"] = "refused"
                lab.otto_decide(pid, fix_proposal["id"], "accept")
                answers["acme.fix.proposal.status_after_accept"] = _status(lab, pid, fix_proposal["id"])
            if plan_proposal is not None:
                lab.otto_decide(pid, plan_proposal["id"], "accept")
                answers["acme.plan.proposal.status_after_accept"] = _status(lab, pid, plan_proposal["id"])
            if fix is not None and next((f for f in lab.fix_states(pid) if f["kind"] == "code"), {}).get("change") is None:
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
                    if plan_proposal is not None:      # the accepted plan change reads done once the check passes on the fixed code
                        after = lab.otto_proposal(pid, plan_proposal["id"])
                        answers["acme.plan.proposal.done_after_the_retest"] = bool(after["facts"].get("done"))
            older_raw = lab.evidence_file(lab.export_evidence(pid)["id"], "json")[1]
            if len(found) > 1:
                progress("  ... Acme Pay: the second pack")
                lab.install_pack(found[1].version)
                # every earlier step has a result by now, so the Overview's next step is the new pack's checks
                answers["acme.second_pack.next_step_page"] = lab.assessment_view(_assessment_id(lab, pid))["next_step"]["page"]
                answers["acme.second_pack.checks_ready_to_add"] = lab.otto_new_checks(pid)
                before = set(_advisory_rows(lab, pid))
                _accept_each_check(lab, pid)
                added = [key for key in _advisory_rows(lab, pid) if key not in before]
                answers["acme.checks_added_from_second_pack"] = len(added)
                lab.run_all(pid)
                lab.wait_until_idle(pid, WAIT_SECONDS)
                rows = _advisory_rows(lab, pid)
                for key in added:
                    answers[f"acme.second_pack.{key[1]}.result"] = (rows[key]["result"] or {}).get("label")
                    answers[f"acme.second_pack.{key[1]}.program"] = (rows[key]["result"] or {}).get("component")
            progress("  ... Acme Pay: the dependency list, the libraries an advisory names, and Otto's proposed updates")
            lab.add_dependency_list(pid, DEPENDENCIES_FILE.name, DEPENDENCIES_FILE.read_bytes())

            def libraries() -> dict[str, dict]:
                return {row["label"]: row for group in lab.dependencies_view(pid)["groups"] for row in group["rows"]}

            def blockers() -> list:
                return [system["blocker_lines"] for system in lab.dependencies_view(pid)["systems"]]
            listed = libraries()
            answers["acme.dependencies.named_by_an_advisory"] = sorted(label for label, row in listed.items() if row.get("advisories"))
            for label, row in sorted(listed.items()):
                if row.get("advisories"):
                    answers[f"acme.dependencies.{label}.named"] = [f"{a['id']}: {a['state']['label']}" for a in row["advisories"]]
            updates = sorted((u for u in _proposed(lab, pid, "dependency") if u["state"] == "proposed"), key=lambda u: u["title"])
            answers["acme.dependencies.updates_proposed"] = [u["title"] for u in updates]
            if len(updates) >= 2:
                blockers_before, runs_then = blockers(), _runs(lab, pid)
                accepted, rejected = (f"{u['about']['library']} {u['about']['version']}" for u in updates[:2])
                lab.otto_decide(pid, updates[0]["id"], "accept")
                lab.otto_decide(pid, updates[1]["id"], "reject", "Moves with the platform team")
                now = libraries()
                answers["acme.dependency.accept.proposal_status"] = _status(lab, pid, updates[0]["id"])
                answers["acme.dependency.accept.library_status"] = (now[accepted].get("otto_status") or {}).get("label")
                answers["acme.dependency.reject.proposal_status"] = _status(lab, pid, updates[1]["id"])
                answers["acme.dependency.reject.library_status"] = (now[rejected].get("otto_status") or {}).get("label")
                answers["acme.dependency.deciding_changed_no_blocker_and_ran_nothing"] = blockers() == blockers_before and _runs(lab, pid) == runs_then
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
                # one entry's content, changed: the first entry that names an advisory (a lock entry)
                lines = otto["ledger"]["lines"]
                place = next(n for n, line in enumerate(lines) if '"advisory":"' in line)
                lines[place] = lines[place].replace('"advisory":"', '"advisory":"X', 1)

            def line_removed(otto: dict) -> None:
                del otto["ledger"]["lines"][1]
                otto["ledger"]["height"] -= 1

            def pack_swapped(otto: dict) -> None:
                otto["packs"] = [json.loads(canonical_bytes(found[-1].envelope))] if len(found) > 1 else []
                otto["packs"] = otto["packs"][:1] if len(otto["packs"]) > 1 else otto["packs"]

            def decision_changed(otto: dict) -> None:
                decided = next(p for p in otto["proposals"] if p["decisions"])
                decided["decisions"][0]["by"] = "Someone else"

            def decision_removed(otto: dict) -> None:
                decided = next(p for p in otto["proposals"] if len(p["decisions"]) == 1)
                decided["decisions"], decided["state"] = [], "proposed"

            otto_part = json.loads(newer_raw)["evidence"]["otto"]
            answers["evidence.decisions_in_the_file"] = sum(len(p["decisions"]) for p in otto_part["proposals"])
            answers["evidence.every_decision_names_who_and_when"] = all(d["by"] and d["at"] for p in otto_part["proposals"] for d in p["decisions"])
            answers["evidence.rejected_proposal_with_its_reason"] = any(d["decision"] == "reject" and d["reason"] == "Not this quarter"
                                                                        for p in otto_part["proposals"] for d in p["decisions"])
            answers["evidence.decision_changed_and_signed_again"] = resigned(decision_changed)
            answers["evidence.decision_removed_and_signed_again"] = resigned(decision_removed)
            answers["evidence.ledger_line_changed_and_signed_again"] = resigned(line_changed)
            answers["evidence.ledger_line_removed_and_signed_again"] = resigned(line_removed)
            answers["evidence.pack_swapped_and_signed_again"] = resigned(pack_swapped)
            answers["evidence.previous_later_download"] = _verify(["verify", str(folder / "newer.json"), "--previous", str(folder / "older.json"), *data])[0]
            answers["evidence.previous_with_a_shorter_ledger"] = _verify(["verify", str(folder / "older.json"), "--previous", str(folder / "newer.json"), *data])[0]
            # Phase 6d: Change watch, on the same assessment and after everything above (so no earlier answer moves).
            progress("  ... Acme Pay: Change watch (both demo changes, the picked tests of the one that undoes the fix, the evidence)")
            _change_watch_part(lab, pid, answers, folder, data)
        finally:
            lab.stop()


CHANGE_BRANCHES = {"revert-range-check": "dev/revert-range-check", "allow-tls-1-0": "dev/allow-tls-1-0-for-partner"}


def _change_watch_part(lab: Lab, pid: int, answers: dict, folder: Path, data: list[str]) -> None:
    """Change watch through the same path as its buttons: Bring in a demo change (twice), what is picked for each and
    why it can or cannot run, Run the picked tests for the change that undoes the merged fix, what Fixes then lists,
    and the verify command on a download and on two changed copies."""
    def own() -> str:        # the assessment's own results, as Evidence and Advisories read them
        return json.dumps([lab.lab_view(pid)["rows"], lab.advisories_view(pid)["rows"]], sort_keys=True, default=str)

    def change(key: str) -> dict | None:
        return next((c for c in lab.change_watch_view(pid)["changes"] if c["branch"] == CHANGE_BRANCHES[key]), None)
    runs_before, own_before = _runs(lab, pid), own()
    for key in CHANGE_BRANCHES:
        offered = next(m for m in lab.change_watch_view(pid)["menu"]["items"] if m["key"] == key)
        answers[f"change.{key}.offered"] = bool(offered["can"])
        if offered["can"]:
            lab.bring_in_demo_change(pid, key)
    answers["change.bringing_in_ran_nothing"] = _runs(lab, pid) == runs_before and not lab.jobs.busy(pid)
    state = {c["branch"]: c for c in lab.change_watch_state(pid)["changes"]}
    for key, branch in CHANGE_BRANCHES.items():
        shown, raw = change(key), state.get(branch)
        if shown is None or raw is None:
            continue
        # (two answers, so that "none" is never read as "its code is not ours" for a change that leaves the program alone)
        answers[f"change.{key}.edits_the_program"] = bool(raw.get("touches_program"))
        answers[f"change.{key}.code_is"] = (raw.get("gives") or {}).get("version")
        answers[f"change.{key}.picked"] = [t["title"] for t in shown["panel"]["picked"]]
        answers[f"change.{key}.not_picked"] = [t["title"] for t in shown["panel"]["not_picked"]]
        answers[f"change.{key}.status_before_a_run"] = shown["status"]["word"]
        answers[f"change.{key}.can_run"] = bool(shown["panel"]["run"]["can"])
        answers[f"change.{key}.flags"] = [f"{f['file']} line {f['line']}: {f['word']}" for f in raw["flags"]]
    revert = change("revert-range-check")
    if revert is None or not revert["panel"]["run"]["can"]:
        return
    lab.run_picked_tests(pid, revert["id"])              # the Run the picked tests button
    lab.wait_until_idle(pid, WAIT_SECONDS)
    done = change("revert-range-check") or revert
    answers["change.revert-range-check.status_after_the_run"] = done["status"]["word"]
    for result in done["panel"]["results"]:
        answers[f"change.revert-range-check.{result['title']}.before"] = (result["before"] or {}).get("label")
        answers[f"change.revert-range-check.{result['title']}.on_the_change"] = (result["now"] or {}).get("label")
        answers[f"change.revert-range-check.{result['title']}.reads"] = result["differs"]
    answers["change.revert-range-check.own_results_unchanged"] = own() == own_before
    answers["change.revert-range-check.fixes_entry"] = next(
        (f["title"] for f in lab.fixes_view(pid)["fixes"] if f["id"] == f"fix-{done['id']}"), None)
    entry = next((f for f in lab.fixes_view(pid)["fixes"] if f["id"] == f"fix-{done['id']}"), None)
    answers["change.revert-range-check.fixes_entry_status"] = entry["status"]["word"] if entry else None
    raw_file = lab.evidence_file(lab.export_evidence(pid)["id"], "json")[1]
    (folder / "watch.json").write_bytes(raw_file)
    answers["evidence.change_watch.fresh_download"] = _verify(["verify", str(folder / "watch.json"), *data])[0]

    def resigned(alter) -> int:
        evidence = json.loads(raw_file)["evidence"]
        alter(evidence)
        (folder / "watch-changed.json").write_bytes(sign_envelope(evidence, lab.settings.data_dir))
        return _verify(["verify", str(folder / "watch-changed.json"), *data])[0]

    def word_changed(evidence: dict) -> None:
        evidence["change_watch"]["runs"][-1]["review"]["status"] = "no_difference"

    def run_record_changed(evidence: dict) -> None:
        evidence["change_watch"]["runs"][-1]["tests"][0]["now"]["record"]["duration_ms"] += 1

    def part_removed(evidence: dict) -> None:
        del evidence["change_watch"]
    answers["evidence.change_watch.reviewers_word_changed_and_signed_again"] = resigned(word_changed)
    answers["evidence.change_watch.run_record_changed_and_signed_again"] = resigned(run_record_changed)
    answers["evidence.change_watch.part_removed_and_signed_again"] = resigned(part_removed)


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
            answers["real.proposals.checks_proposed"] = len(_proposed(lab, pid, "check"))
            _accept_each_check(lab, pid)
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

            def proof_rows() -> dict[str, dict[str, str]]:
                """{the fix's title: {"public": the first row's word, "here": the second row's word}} for Otto's library fixes."""
                return {f["title"]: {row["key"]: row["badge"]["label"] for row in f.get("proof_rows") or []}
                        for f in lab.fixes_view(pid)["fixes"] if f.get("proof_rows")}
            for title, rows in proof_rows().items():
                answers[f"real.fix.{title}.proven_on_public_copies"] = rows.get("public")
                answers[f"real.fix.{title}.proven_on_your_system_before_a_retest"] = rows.get("here")
            # each of Otto's fixes is a proposal: accepted here one by one, which runs nothing
            waiting = [p for p in _proposed(lab, pid, "fix") if p["state"] == "proposed"]
            answers["real.fix.proposals_waiting"] = len(waiting)
            for proposal in waiting:
                lab.otto_decide(pid, proposal["id"], "accept")
            # a failed advisory check on a program the advisory is not about: the pack holds no fix for it
            answers["real.failed_checks_with_no_fix_from_otto"] = sorted(
                str(f.get("list_source")) for f in lab.fixes_view(pid)["fixes"]
                if str(f.get("title", "")).startswith("Advisory check:") and "From Otto" not in (f.get("labels") or []))
            for name, version in RETESTS:
                progress(f"  ... Real libraries: Retest new version: {name} {version}")
                lab.start_retest(pid, version, name)
                lab.wait_until_idle(pid, WAIT_SECONDS)
                for (program, advisory), row in _advisory_rows(lab, pid).items():
                    if program.startswith(name + " "):
                        answers[f"real.retest.{name} {version}.{advisory}.result"] = (row["after"] or {}).get("label")
                        answers[f"real.retest.{name} {version}.{advisory}.wrong_cases"] = _wrong(lab, row["after"])
                for title, rows in proof_rows().items():
                    if title == f"Update {name} to {version}":
                        answers[f"real.fix.{title}.proven_on_your_system_after_the_retest"] = rows.get("here")
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
