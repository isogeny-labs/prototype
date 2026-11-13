"""The Fixes step as the screen gets it, and what Evidence Lab says about a fix: the view in every status, its
shape, its words, and that it never says more than the stored records and the reviewer give.

The words expected here are the approved ones (the mockups of 12 November 2026); the numbers and names in them
are worked out from the records of the plan this module runs: the five suggested tests plus the post-quantum check."""
import ast
import copy
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import changes, components, demo_repo, fixes, present, present_fixes
from app.db import PlanRow, TestRunRow
from app.execute import pq
from conftest import demo_plan, make_lab, result_of
from fixes_shapes import FIXES_VIEW, LAB_VIEW, fix as fix_of, plain, problems, section, texts
from test_catalog_tests import ALERT_40, FakeChecker
from test_changes import proved, small_plan, tamper

FIX, TLS = "fix-ecdsa-range-check", "fix-tls-versions"
SIZE = "3 lines added and 1 removed"
SERVER_LINE = "This fixes the signing program. The server finding is separate and still open."
SERVER_LINE_UNPROVEN = "This change is for the signing program only. The server finding is separate and still open."
ONE_LOGIN = "This version has one login and no separate accounts. Whoever is at the keyboard records each approval, under the name shown."
PROOF_PASSED = ("All 3 tests that run the changed code passed, every control behaved as expected, and the 3 server tests came out "
                "the same as before.")
PROOF_FAILED = "1 of the 3 tests that run the changed code did not pass: Official test vectors, Couldn't run (it took too long)."
PROOF_CHANGED = "The stored proof no longer matches its fingerprint."
# What a screen may say only once a proof has passed (the page's own subline is the one place "ready" may stand).
PROVEN_WORDS = re.compile(r"ready for review|ready to merge|fix ready|what it fixes|this fixes|proof passed|\bpassed:|why it is ready", re.I)
WHAT_AVAILABLE = ("A fix template exists for this failure: a ready-made change for a missing range check on the two signature numbers "
                  "(r and s), written for acme-sign's code. Connect the code to prepare the change and prove it.")
WHAT_CHANGES = ("Adds a range check on the two signature numbers (r and s) to acme-sign's signature check, and gives the changed "
                f"program the version number 1.4.3. {SIZE}.")
WHAT_FIXES = ("Adds the missing range check to acme-sign's signature check, so it now rejects signatures such as r = 0, s = 0, as the "
              f"proof's tests show. The changed program reports version 1.4.3. {SIZE}.")
PROOF_INTRO = ("The app applied this change on a new branch of its own copy of the code, then reran every locked test in your plan, "
               "with the old and the new version timed side by side. The runs went through the same steps as your first results: the "
               "same test runner, then the same automatic check that decides each result from what the run recorded. The fix template "
               "has no say in any result.")
RAN_ON_NOTE = ("This version of Evidence Lab only ever runs our own demo software. If a change produced anything else, the app would "
               "run nothing and would not offer the change.")


def button(action: str, label: str, primary: bool, enabled: bool = True) -> dict:
    return {"action": action, "label": label, "primary": primary, "enabled": enabled}


PATCH_BUTTON = button("download_patch", "Download patch", False)


def line(lead: str, rest: str, look: str, busy: bool = False, fix_id: str = FIX) -> dict:
    return {"fix_id": fix_id, "lead": lead, "rest": rest, "look": look, "busy": busy, "button": "View in Fixes"}


TEXT_ONLY_LINE = line("Text-only suggestion:", "a server setting", "dashed", fix_id=TLS)


@contextmanager
def too_slow(lab):
    """While this is open, the harness job that checks the 484 official cases gets next to no time, so that test
    really can't run (a time-out from the real runner). Everything else runs as it always does."""
    real = lab.component_runner.run_job

    def hurried(job, *, time_limit=120.0, on_line=None):
        if job.get("op") == "verify_batch" and len(job.get("cases") or []) > 100:
            time_limit = 0.05
        return real(job, time_limit=time_limit, on_line=on_line)

    lab.component_runner.run_job = hurried
    try:
        yield
    finally:
        lab.component_runner.run_job = real


def look(lab, plan_id: int) -> SimpleNamespace:
    """What both screens are given at this moment, and the wording-free state it was worded from."""
    return SimpleNamespace(fixes=lab.fixes_view(plan_id), lab=lab.lab_view(plan_id), states=lab.fix_states(plan_id))


def code_fix(seen) -> dict:
    return fix_of(seen.fixes, FIX)


def lab_lines(seen) -> dict:
    """The one line about a fix on each result of an Evidence Lab view: {(kind, "result" | "after"): line or None}."""
    return {(row["kind"], side): row[side]["fix_line"] for row in seen.lab["rows"] for side in ("result", "after") if row[side] is not None}


def facts(detail: dict) -> dict:
    return {fact["label"]: plain(fact["value"]) for fact in section(detail, "details")["facts"]}


def proof_rows(detail: dict) -> dict:
    return {row["kind"]: row for part in detail["sections"] if part["key"] == "proof" for table in part["tables"] for row in table["rows"]}


def state_of(seen) -> dict:
    """The code fix as changes.fix_states describes it (no wording)."""
    return next(f for f in seen.states if f["id"] == FIX)


# ---------------------------------------------------------------- the whole flow, once (the real tests, the real speed test)

@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    """One imported demo file from start to end, with both screens' views kept at every status. The first proof
    fails as in the approved picture (the official cases take too long on the changed code); it is then run again
    and passes. The post-quantum check plays back a recorded answer, so the plan is the same on every machine."""
    patch = pytest.MonkeyPatch()
    patch.setattr(pq, "find_checker", lambda mode: (FakeChecker(ALERT_40), None))
    lab = make_lab(tmp_path_factory.mktemp("fixes-view"))
    try:
        plan = demo_plan(lab)
        plan.item = {t["kind"]: t["id"] for t in lab.add_test(plan.id, "pq_readiness")["tests"]}
        seen = {"nothing": look(lab, plan.id)}
        lab.run_test(plan.id, plan.item["bad_signatures"])
        lab.wait_until_idle(plan.id, 120)
        seen["one_result"] = look(lab, plan.id)
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 300)
        seen["not_connected"] = look(lab, plan.id)
        with too_slow(lab):
            lab.connect_code(plan.id)
            deadline = time.monotonic() + 60  # the two quick server tests finish first; the speed test takes much longer
            while time.monotonic() < deadline and not all(t["proof"] for t in state_of(look(lab, plan.id))["proof"]["tests"]
                                                          if t["kind"] in ("tls_versions", "certificate")):
                time.sleep(0.05)
            seen["proving"] = look(lab, plan.id)  # taken while the proof runs
            lab.wait_until_idle(plan.id, 300)
        seen["failed"] = look(lab, plan.id)
        lab.run_proof_again(plan.id, FIX)
        lab.wait_until_idle(plan.id, 300)
        seen["ready"] = look(lab, plan.id)
        lab.open_pull_request(plan.id, FIX, ["you", "a"])
        seen["opened"] = look(lab, plan.id)
        lab.approve(plan.id, FIX, "you")
        seen["waiting"] = look(lab, plan.id)
        lab.approve(plan.id, FIX, "a")
        seen["ready_to_merge"] = look(lab, plan.id)
        lab.merge(plan.id, FIX)
        seen["merged"] = look(lab, plan.id)
        lab.retest_now(plan.id, FIX)
        seen["retesting"] = look(lab, plan.id)
        lab.wait_until_idle(plan.id, 300)
        seen["after"] = look(lab, plan.id)
        yield SimpleNamespace(lab=lab, plan=plan, **seen)
    finally:
        lab.stop()
        patch.undo()


STAGES = ("nothing", "one_result", "not_connected", "proving", "failed", "ready", "opened", "waiting", "ready_to_merge", "merged",
          "retesting", "after")
STATUS_AT = {"one_result": ("not_connected", "Code not connected"), "not_connected": ("not_connected", "Code not connected"),
             "proving": ("proving", "Proving"), "failed": ("failed", "Proof failed"), "ready": ("ready", "Ready for review"),
             "opened": ("waiting", "Waiting for approval"), "waiting": ("waiting", "Waiting for approval"),
             "ready_to_merge": ("ready_to_merge", "Ready to merge"), "merged": ("merged", "Merged"), "retesting": ("merged", "Merged"),
             "after": ("merged", "Merged")}
UNPROVEN, PROVEN = ("one_result", "not_connected", "proving", "failed"), ("ready", "opened", "waiting", "ready_to_merge", "merged", "after")


@pytest.mark.parametrize("stage", STAGES)
def test_every_view_has_exactly_the_shape_the_frontend_expects(flow, stage):
    seen = getattr(flow, stage)
    assert problems(seen.fixes, FIXES_VIEW, "fixes") == [] and problems(seen.lab, LAB_VIEW, "lab") == []


def test_the_page_itself_and_the_list_on_the_left(flow):
    for stage in STAGES:
        view = getattr(flow, stage).fixes
        assert (view["plan_id"], view["is_demo"], view["title"]) == (flow.plan.id, True, "Fixes")
        assert view["subline"] == "Fixes for the findings in Evidence Lab. A code change is ready for review only after its proof has passed."
        assert view["disclaimer"] == present.DISCLAIMER == "Passing these tests doesn't prove a system secure. It shows these specific checks passed."
        assert view["busy"] is (stage in ("proving", "retesting"))  # the screen asks again while anything runs
    nothing = flow.nothing.fixes
    assert nothing["fixes"] == [] and nothing["list_title"] == "Open findings with a fix (0)"
    assert nothing["empty_text"] == "No failed test has a fix. Fixes for failed tests show here."
    # one failed signing test is enough for its fix to be listed; the server test has not been run yet
    assert [(f["id"], f["list_source"]) for f in flow.one_result.fixes["fixes"]] == [(FIX, "Came from 1 failed test: Bad signatures")]
    assert flow.one_result.fixes["list_title"] == "Open findings with a fix (1)"
    for stage in STAGES[2:]:
        view = getattr(flow, stage).fixes
        assert view["list_title"] == "Open findings with a fix (2)" and view["empty_text"] is None
        code, server = view["fixes"]  # the code fix first, then the text-only one
        assert (code["id"], code["kind"], code["title"]) == (FIX, "code", "acme-sign accepts out-of-range signatures")
        assert code["list_source"] == "Came from 2 failed tests: Official test vectors, Bad signatures"
        assert plain(code["source"]) == "Came from 2 failed tests on signing component acme-sign 1.4.2: Official test vectors and Bad signatures."
        assert {"t": "mono", "v": "acme-sign 1.4.2"} in code["source"]
        assert code["labels"] == ["From a fix template"] and code["is_demo"] is True
        assert (server["id"], server["kind"], server["title"]) == (TLS, "text", "Server accepts TLS 1.2")
        assert server["status"] == {"key": "text_only", "word": "Text only", "busy": False}
        assert server["list_source"] == "Came from 1 failed test: Old TLS versions"


def test_the_status_is_the_one_the_records_give_and_only_proving_is_busy(flow):
    for stage, (key, word) in STATUS_AT.items():
        seen = getattr(flow, stage)
        assert code_fix(seen)["status"] == {"key": key, "word": word, "busy": key == "proving"}, stage
        assert key == state_of(seen)["status"]  # worded from the same state, never typed in


def test_code_not_connected(flow):
    detail = code_fix(flow.not_connected)
    assert detail["what"] == {"label": "What it changes", "paragraphs": detail["what"]["paragraphs"], "server_line": SERVER_LINE_UNPROVEN}
    assert [plain(p) for p in detail["what"]["paragraphs"]] == [WHAT_AVAILABLE]
    assert detail["proof"] == {"state": "not_started", "badge": None, "muted": None,
                               "text": "Not started. It starts by itself once the code is connected: every locked test in your plan is "
                                       "rerun on the changed code. This takes about a minute."}
    assert detail["pull_request"] is None and detail["patch"] is None and detail["merge_dialog"] is None
    assert detail["approvers"] == {"text": "You pick the reviewers once the proof has passed.", "options": None, "rows": None, "footnote": None}
    note = ("Connects a fresh copy of the small demo repository of acme-sign 1.4.2 that comes with the app (the source code and its "
            "history of changes, in git's format), for this imported file and every fix in it. The proof then starts by itself.")
    assert detail["actions"] == {"buttons": [button("connect", "Connect demo code", True)], "note": note}
    assert detail["sections"] == [] and detail["sections_note"] == "The change, its proof and the technical details appear below once the code is connected."
    # until every test in the plan has a result the button is switched off, and the reason stands in front of the note
    early = code_fix(flow.one_result)
    assert early["actions"] == {"buttons": [button("connect", "Connect demo code", True, enabled=False)],
                                "note": f"Run every test in the plan first, so there is a result to compare with. {note}"}
    assert early["what"]["server_line"] is None  # no server finding yet: the server test has not been run


def test_proving(flow):
    detail = code_fix(flow.proving)
    rows = proof_rows(detail)
    done = sum(1 for row in rows.values() if row["proof"] is not None)
    running = f"Running: {done} of 6 tests finished."
    assert detail["proof"] == {"state": "running", "badge": None, "text": running, "muted": "Not offered yet."}
    assert [plain(p) for p in detail["what"]["paragraphs"]] == [WHAT_CHANGES]
    assert detail["what"]["label"] == "What it changes" and detail["what"]["server_line"] == SERVER_LINE_UNPROVEN
    assert detail["approvers"] == {"text": "You pick the reviewers once the proof has passed.", "options": None, "rows": None, "footnote": None}
    assert detail["actions"] == {"buttons": [], "note": None}  # nothing to press while it proves
    assert detail["pull_request"] is None and detail["patch"] is None and detail["sections_note"] is None
    change, proof, details = detail["sections"]
    assert (change["key"], change["open"], proof["key"], proof["open"], details["key"], details["open"]) == ("change", True, "proof", False, "details", False)
    assert proof["line"] == running and proof["intro"] == PROOF_INTRO and proof["verdict"] is None
    assert len(rows) == 6 and 0 < done < 6
    for row in rows.values():
        assert row["before"] is not None  # the first result it will be compared with is already there
        if row["proof"] is None:  # still waiting or running: no result, no control sentence, and the rule check says so
            assert row["waiting"]["text"] in ("Waiting", "Running") and row["control"] == ""
            assert row["check"] == {"ok": None, "text": "Not finished yet"}
        else:  # finished, but the proof as a whole has not been reviewed: no tick and no cross yet
            assert row["waiting"] is None and row["control"].startswith("Control: ")
            assert row["check"] == {"ok": None, "text": "Not checked yet"}
    assert rows["speed_size"]["proof"] is None and rows["tls_versions"]["proof"] is not None
    assert "Proof finished" not in facts(detail) and "Evidence fingerprint of the proof (SHA-256)" not in facts(detail)
    assert details["ran_on"]["title"] == "What the tests are running on"
    assert "Download evidence" not in details["note"] and "Download patch" not in details["note"]


def test_the_change_shows_the_exact_lines_before_and_after(flow):
    for stage in ("proving", "failed", "ready", "merged", "after"):
        change = section(code_fix(getattr(flow, stage)), "change")
        assert (change["title"], change["line"], change["open"]) == ("The change", f"{SIZE}, in 1 file (acme_sign.py)", True)
        assert change["intro"] == ("Written from a fix template: a ready-made change for one known kind of bug, a missing range check when "
                                   "checking an ECDSA signature. It was not written by an AI model, and it applies only where the code has "
                                   "exactly the lines it expects.")
        check, version = change["parts"]
        assert check["title"] == "1. The check: reject a signature whose numbers are out of range"
        assert check["why"] == ("acme_sign.py, in the verify command. r and s must each be at least 1 and below n, a fixed upper limit set "
                                "by the P-256 standard.")
        assert check["before_label"] == {"lead": "Before:", "strong": "acme-sign 1.4.2", "rest": ", nothing removed here"}
        assert check["after_label"] == {"lead": "After:", "strong": "this change", "rest": ", 2 lines added (marked +)"}
        assert [(x["mark"], x["text"]) for x in check["before"]] == [
            (" ", "    try:"), (" ", '        r, s = der_decode(bytes.fromhex(req["signature"]))'), (" ", "    except ValueError:"),
            (" ", '        return {"valid": False}'), (" ", "    e = digest_int(message)")]
        # the two new lines come right after the existing "return" under "except ValueError:", as git shows them
        assert [(x["mark"], x["text"]) for x in check["after"]] == [
            (" ", "    try:"), (" ", '        r, s = der_decode(bytes.fromhex(req["signature"]))'), (" ", "    except ValueError:"),
            (" ", '        return {"valid": False}'), ("+", "    if not (1 <= r < N and 1 <= s < N):"), ("+", '        return {"valid": False}'),
            (" ", "    e = digest_int(message)")]
        assert version["title"] == "2. The version number"
        assert version["why"] == "So the changed program reports itself as 1.4.3 and can be told apart from 1.4.2."
        assert version["before_label"]["rest"] == ", 1 line removed (marked −)" and version["after_label"]["rest"] == ", 1 line added (marked +)"
        assert [(x["mark"], x["text"]) for x in version["before"]] == [(" ", 'NAME = "acme-sign"'), ("-", 'VERSION = "1.4.2"'), (" ", 'ALGORITHM = "ECDSA P-256"')]
        assert [(x["mark"], x["text"]) for x in version["after"]] == [(" ", 'NAME = "acme-sign"'), ("+", 'VERSION = "1.4.3"'), (" ", 'ALGORITHM = "ECDSA P-256"')]
        # the line numbers are those of each version of the file, counted from 1 as people count them
        old_file = components.lookup("acme-sign", "1.4.2").read_text(encoding="utf-8").split("\n")
        new_file = components.lookup("acme-sign", "1.4.3").read_text(encoding="utf-8").split("\n")
        for block, file in ((check["before"], old_file), (version["before"], old_file), (check["after"], new_file), (version["after"], new_file)):
            assert all(file[x["n"] - 1] == x["text"] for x in block)
            assert [x["n"] for x in block] == list(range(block[0]["n"], block[0]["n"] + len(block)))


def test_proof_failed(flow):
    detail = code_fix(flow.failed)
    assert detail["proof"] == {"state": "failed", "badge": {"label": "Proof did not pass", "tone": "fail"},
                               "text": f"{PROOF_FAILED} The change is not offered.", "muted": None}
    assert [plain(p) for p in detail["what"]["paragraphs"]] == [WHAT_CHANGES]
    assert detail["what"]["label"] == "What it changes" and detail["what"]["server_line"] == SERVER_LINE_UNPROVEN
    assert detail["approvers"] == {"text": "Nobody yet: a change that is not offered can't get a pull request.", "options": None,
                                   "rows": None, "footnote": None}
    assert detail["actions"] == {"buttons": [button("run_proof_again", "Run proof again", False)],
                                 "note": "Reruns all 6 tests in your plan. The change is offered only if the proof passes."}
    assert detail["pull_request"] is None and detail["patch"] is None and detail["merge_dialog"] is None
    proof = section(detail, "proof")
    assert proof["line"] == "Did not pass: 1 of the 3 tests that run the changed code did not pass." and proof["intro"] == PROOF_INTRO
    assert proof["verdict"] == {"tone": "fail", "title": "Why this change is not offered", "shows_title": None, "shows": [],
                                "checks": [{"ok": False, "text": PROOF_FAILED},
                                           {"ok": True, "text": "Every control behaved as expected in the tests that ran."},
                                           {"ok": True, "text": "The 3 server tests came out the same as before."}]}
    rows = proof_rows(detail)
    assert rows["official_vectors"]["proof"] == {"label": "Couldn't run (it took too long)", "tone": "warn", "short": "Could not run: it took too long."}
    assert rows["official_vectors"]["control"] == "Control: not run, because the test couldn't run."
    assert rows["official_vectors"]["check"] == {"ok": False, "text": "Did not pass"}
    assert rows["bad_signatures"]["check"] == {"ok": True, "text": "Passed"} and rows["speed_size"]["check"] == {"ok": True, "text": "No slowdown"}
    assert all(rows[k]["check"] == {"ok": True, "text": "Same as before"} for k in ("tls_versions", "certificate", "pq_readiness"))
    shown = facts(detail)
    assert re.fullmatch(r"\S+Z, after (\d+\.\d s|\d+ min \d+ s) measured", shown["Proof finished"])
    assert re.fullmatch(r"[0-9a-f]{64}", shown["Evidence fingerprint of the proof (SHA-256)"])


def test_ready_for_review(flow):
    detail = code_fix(flow.ready)
    assert detail["what"] == {"label": "What it fixes", "paragraphs": detail["what"]["paragraphs"], "server_line": SERVER_LINE}
    assert [plain(p) for p in detail["what"]["paragraphs"]] == [WHAT_FIXES]
    assert detail["proof"] == {"state": "passed", "badge": {"label": "Proof passed", "tone": "pass"}, "text": PROOF_PASSED, "muted": None}
    assert detail["approvers"] == {"text": None, "rows": None, "footnote": ONE_LOGIN, "options": [
        {"id": "you", "name": "You", "note": "(the person logged in)", "demo": False, "checked": True},
        {"id": "a", "name": "Demo reviewer A", "note": None, "demo": True, "checked": False},
        {"id": "b", "name": "Demo reviewer B", "note": None, "demo": True, "checked": False}]}
    assert detail["actions"] == {"buttons": [button("open_pull_request", "Open pull request", True)],
                                 "note": "Nothing goes into the main copy of the code until the reviewers you pick approve and you confirm the merge."}
    assert detail["pull_request"] is None and detail["patch"] is None and detail["merge_dialog"] is None


def test_the_proof_table_and_why_it_is_ready(flow):
    proof = section(code_fix(flow.ready), "proof")
    assert (proof["title"], proof["open"], proof["intro"]) == ("Proof", False, PROOF_INTRO)
    assert proof["line"] == "Passed: all 3 tests that run the changed code passed, every control behaved as expected, and the 3 server tests came out the same as before."
    code, server = proof["tables"]
    assert (code["heading"], code["tag"], code["need"]) == ("Tests that run the changed code", "measured",
                                                             "Each of these must pass, and its control must behave as expected.")
    assert code["columns"] == ["Test", "Before: acme-sign 1.4.2", "On the changed code", "Rule check"]
    assert (server["heading"], server["tag"]) == ("Tests that don't run this code (they test the server)", "measured")
    assert server["need"] == "A code change can't affect these. They are rerun anyway and must come out the same as before."
    assert server["columns"] == ["Test", "Before", "Rerun for this proof", "Rule check"]
    assert [r["kind"] for r in code["rows"]] == ["official_vectors", "bad_signatures", "speed_size"]
    assert [r["kind"] for r in server["rows"]] == ["tls_versions", "certificate", "pq_readiness"]
    signer = "Control: a deliberately broken signer failed this test, as expected."
    vectors, bad, speed = code["rows"]
    assert vectors == {"kind": "official_vectors", "title": "Official test vectors", "waiting": None, "control": signer,
                       "before": {"label": "Failed", "tone": "fail", "short": "3 of 484 official cases wrong (168, 171, 364), all from one missing range check."},
                       "proof": {"label": "Passed", "tone": "pass", "short": "484 of 484 official cases right."},
                       "check": {"ok": True, "text": "Passed"}}
    assert bad == {"kind": "bad_signatures", "title": "Bad signatures", "waiting": None, "control": signer,
                   "before": {"label": "Failed", "tone": "fail", "short": "Accepts the signature r=0, s=0. One cause: no range check."},
                   "proof": {"label": "Passed", "tone": "pass", "short": "Rejects r=0, s=0 and every other bad signature tried."},
                   "check": {"ok": True, "text": "Passed"}}
    # speed: the first-run numbers are labelled as such, and the proof cell names the side-by-side measurement the rule compares
    assert (speed["before"]["label"], speed["proof"]["label"], speed["check"]) == ("Measured", "No slowdown beyond measured noise", {"ok": True, "text": "No slowdown"})
    assert re.fullmatch(r"Sign [\d.]+ ms, verify [\d.]+ ms \(medians, first run\)\.", speed["before"]["short"])
    assert re.fullmatch(r"Sign [\d.]+ ms, verify [\d.]+ ms on acme-sign 1\.4\.3, against [\d.]+ ms and [\d.]+ ms on acme-sign 1\.4\.2, "
                        r"measured side by side \(medians\)\. Noise: ±[\d.]+%\.", speed["proof"]["short"])
    assert speed["control"] == "Control: a deliberately slowed signer was flagged as slower, as expected."
    tls, certificate, pq_row = server["rows"]
    assert (tls["before"]["short"], tls["proof"]["short"]) == ("Server accepted TLS 1.2.", "Server still accepts TLS 1.2. This change doesn't touch the server.")
    assert (tls["proof"]["label"], tls["proof"]["tone"]) == ("Failed", "fail")  # failed before and after: a code change does not touch the server
    assert certificate["before"] == certificate["proof"] == {"label": "Passed", "tone": "pass", "short": "ECDSA P-256, as claimed. NIST retirement note."}
    assert (pq_row["before"]["short"], pq_row["proof"]["short"]) == ("Server does not offer X25519MLKEM768.",
                                                                    "Server does not offer X25519MLKEM768. This change doesn't touch the server.")
    assert all(r["check"] == {"ok": True, "text": "Same as before"} and r["control"].startswith("Control: ") for r in server["rows"])
    assert proof["verdict"] == {
        "tone": "pass", "title": "Why it is ready for review",
        "checks": [{"ok": True, "text": "All 3 tests that run the changed code passed."}, {"ok": True, "text": "Every control behaved as expected."},
                   {"ok": True, "text": "The 3 server tests came out the same as before."}],
        "shows_title": "What this proof shows, and what it doesn't",
        "shows": ["It shows that with this change the two failed tests pass, no slowdown beyond measured noise was found, and the server "
                  "tests came out as before.",
                  "It doesn't show that the change is free of other faults, and it does nothing about the server finding."]}
    # the cells are the worded results of the very runs the proof record names
    state = state_of(flow.ready)
    with flow.lab.db() as db:
        for test in state["proof"]["tests"]:
            shown = flow.lab._result(db, db.get(TestRunRow, test["proof"]["run_id"]))
            row = next(r for r in code["rows"] + server["rows"] if r["kind"] == test["kind"])
            assert row["proof"]["label"] == shown["label"] and row["control"] == shown["control"]["line"]


def test_technical_details(flow):
    state = state_of(flow.merged)
    change, merge = state["change"], state["merge"]
    for stage in ("ready", "opened", "merged"):
        detail = code_fix(getattr(flow, stage))
        details = section(detail, "details")
        assert (details["title"], details["line"], details["open"]) == ("Technical details", "Repository, branches, commits, fingerprints and mode", False)
        shown = facts(detail)
        assert list(shown) == ["Repository", "Starting point", "Change branch", "File changed"] + (["Pull request"] if stage != "ready" else []) + [
            "Proof finished", "Mode", "Evidence fingerprint of the proof (SHA-256)"]
        assert shown["Repository"] == "acme-sign Demo data, the app's own copy. Nothing is sent anywhere else."
        assert details["facts"][0]["value"][:3] == [{"t": "mono", "v": "acme-sign"}, {"t": "text", "v": " "}, {"t": "demo", "v": "Demo data"}]
        assert shown["Starting point"] == f"branch main, commit {change['base_commit'][:7]} (acme-sign 1.4.2)"
        assert shown["Change branch"] == f"fix/ecdsa-range-check, commit {change['head_commit'][:7]}"
        assert shown["File changed"] == f"acme_sign.py: {SIZE}" and shown["Mode"] == "Demo mode, not isolated"
        assert re.fullmatch(r"\S+Z, after (\d+\.\d s|\d+ min \d+ s) measured", shown["Proof finished"])
        # the fingerprint is the reviewer's, of the proof record: the same one the download holds
        assert shown["Evidence fingerprint of the proof (SHA-256)"] == state["proof"]["review"]["record_sha256"]
        assert [f["fingerprint"] for f in details["facts"]] == [False] * (len(shown) - 1) + [True]
        note = ("A branch is a separate line of work inside the repository, so the main copy stays untouched until a merge. A commit is one "
                f"saved state of the code, named by a short id such as {change['head_commit'][:7]}."
                ' The full record of every run in this proof is in the files saved by "Download evidence", where the evidence fingerprint '
                "of the proof can be checked. That fingerprint is listed inside the evidence file; it is not the fingerprint of the file itself.")
        patch_note = ' "Download patch" saves this change as one file that a developer can apply to another copy of the code.'
        assert details["note"] == note + (patch_note if stage != "ready" else "")
        ran_on = details["ran_on"]
        assert ran_on["title"] == "What the tests ran on" and ran_on["note"] == RAN_ON_NOTE
        assert plain(ran_on["text"]) == ("Our own bundled demo component, acme-sign 1.4.3. Before running anything, the app checked that the file "
                                        "built from branch fix/ecdsa-range-check is exactly the same as that bundled component, byte for byte: "
                                        "the two fingerprints below match.")
        built = change["built"]["sha256"]
        assert ran_on["fingerprints"] == [{"label": "The built file (SHA-256)", "value": built, "tag": "measured"},
                                          {"label": "Bundled acme-sign 1.4.3 (SHA-256)", "value": built, "tag": "demo"}]
    assert facts(code_fix(flow.opened))["Pull request"].startswith("#1, opened ") and "merged" not in facts(code_fix(flow.opened))["Pull request"]
    assert re.fullmatch(rf"#1, opened \S+Z; merged \S+Z \(merge commit {merge['merge_commit'][:7]}\)", facts(code_fix(flow.merged))["Pull request"])


def test_waiting_for_approval_then_ready_to_merge(flow):
    opened, waiting, both = code_fix(flow.opened), code_fix(flow.waiting), code_fix(flow.ready_to_merge)
    for detail in (opened, waiting, both):
        assert detail["what"]["label"] == "What it fixes" and detail["what"]["server_line"] == SERVER_LINE and detail["proof"]["text"] == PROOF_PASSED
        assert detail["pull_request"]["title"] == "#1 Reject signatures whose r or s is out of range."
        assert detail["patch"] == {"url": f"/api/plans/{flow.plan.id}/fixes/{FIX}/patch", "filename": "acme-sign-pull-request-1.patch"}
        assert detail["approvers"]["text"] is None and detail["approvers"]["options"] is None and detail["approvers"]["footnote"] == ONE_LOGIN
    open_text = "Open since {time}. It stays inside the app; nothing is sent anywhere else."
    assert plain([p if p["t"] != "time" else {"t": "text", "v": "{time}"} for p in opened["pull_request"]["text"]]) == open_text
    assert [p["t"] for p in opened["pull_request"]["text"]] == ["text", "time", "text"]

    def rows(detail):
        return [(r["id"], r["name"], r["note"], r["demo"], bool(r["approved_at"]), r["approved_text"], r["approve_label"], r["primary"])
                for r in detail["approvers"]["rows"]]

    you, a = ("you", "You", "(the person logged in)", False), ("a", "Demo reviewer A", None, True)
    assert rows(opened) == [(*you, False, None, "Approve", True), (*a, False, None, "Approve as Demo reviewer A", False)]
    assert rows(waiting) == [(*you, True, "Approved", None, True), (*a, False, None, "Approve as Demo reviewer A", False)]
    assert rows(both) == [(*you, True, "Approved", None, True), (*a, True, "Approved", None, False)]
    never = "The app never merges on its own: you press the button and confirm."
    merge_off = [button("merge", "Merge pull request", True, enabled=False), PATCH_BUTTON]
    assert opened["actions"] == {"buttons": merge_off, "note": f'"Merge pull request" unlocks when every reviewer has approved: waiting for You and Demo reviewer A. {never}'}
    assert waiting["actions"] == {"buttons": merge_off, "note": f'"Merge pull request" unlocks when every reviewer has approved: waiting for Demo reviewer A. {never}'}
    assert opened["merge_dialog"] is None and waiting["merge_dialog"] is None  # no confirm box before every reviewer has approved
    assert both["actions"] == {"buttons": [button("merge", "Merge pull request", True), PATCH_BUTTON], "note": f"Every reviewer has approved. {never}"}
    assert plain([p for p in both["pull_request"]["text"] if p["t"] != "time"]) == (
        "Open since . It stays inside the app; nothing is sent anywhere else. Every reviewer has approved. Not merged yet.")
    dialog = both["merge_dialog"]
    assert (dialog["title"], dialog["confirm"], dialog["cancel"]) == ("Merge pull request #1?", "Confirm merge", "Cancel")
    assert [plain(p) for p in dialog["paragraphs"]] == [
        "This puts the change on the main branch of the app's own copy of the demo repository acme-sign. After the merge, that branch holds acme-sign 1.4.3.",
        "Every reviewer has approved. The app deploys nothing, and a merge can't be undone here."]


def test_merged(flow):
    for stage in ("merged", "after"):
        detail = code_fix(getattr(flow, stage))
        assert detail["what"]["label"] == "What it fixes" and detail["what"]["server_line"] == SERVER_LINE
        assert detail["proof"] == {"state": "passed", "badge": {"label": "Proof passed", "tone": "pass"}, "text": PROOF_PASSED, "muted": None}
        assert detail["pull_request"]["title"] == "#1 Reject signatures whose r or s is out of range."
        assert plain([p for p in detail["pull_request"]["text"] if p["t"] != "time"]) == (
            "Merged  by the person logged in, after confirming. The demo repository's main branch now holds acme-sign 1.4.3. Nothing was deployed.")
        assert [r["approve_label"] for r in detail["approvers"]["rows"]] == [None, None]  # nothing more to approve
        assert [r["approved_text"] for r in detail["approvers"]["rows"]] == ["Approved", "Approved"]
        assert detail["actions"] == {"buttons": [button("retest_now", "Retest now", True), PATCH_BUTTON],
                                     "note": 'Reruns the same locked tests on acme-sign 1.4.3, the code now on main, and shows before and '
                                             'after in Evidence Lab. It does the same as "Retest new version" there.'}
        assert detail["merge_dialog"] is None and detail["patch"]["filename"] == "acme-sign-pull-request-1.patch"
    # while the retest runs nothing new can start: the button is switched off and says why
    during = code_fix(flow.retesting)
    assert during["actions"] == {"buttons": [button("retest_now", "Retest now", True, enabled=False), PATCH_BUTTON],
                                 "note": "Tests are still running. Wait until they have finished."}


def test_the_text_only_fix_is_built_from_what_the_failed_test_recorded(flow):
    address = flow.plan.imp["addresses"][0]["address"]
    for stage in STAGES[2:]:
        detail = fix_of(getattr(flow, stage).fixes, TLS)
        assert plain(detail["source"]) == f"Came from 1 failed test on server {address}: Old TLS versions. The file claims TLS 1.3 only."
        assert detail["labels"] == [] and detail["is_demo"] is True
        assert detail["what"] == {"label": "What it suggests", "server_line": None, "paragraphs": [[{"t": "text", "v": (
            "A server setting, not a code change: stop accepting TLS 1.2, or keep it with strong settings only and correct the scanner "
            "file. The suggestion below says where the setting lives and gives two ways to do it.")}]]}
        assert detail["proof"] == {"state": "none", "badge": None, "muted": None,
                                   "text": "None. This suggestion is text only: the app has not applied it or tested it."}
        assert detail["approvers"] == {"text": "Your own server team, outside this app. The app never changes your server.",
                                       "options": None, "rows": None, "footnote": None}
        # a text-only fix has no buttons
        assert detail["actions"] == {"buttons": [], "note": None} and detail["pull_request"] is detail["patch"] is detail["merge_dialog"] is None
        (only,) = detail["sections"]
        assert (only["key"], only["title"], only["open"]) == ("suggestion", "The suggestion", True)
        assert only["line"] == "A warning first, where the setting lives, and two ways to fix it"
    given = section(fix_of(flow.ready.fixes, TLS), "suggestion")["suggestion"]
    # the version and the cipher suite are the ones the failed run recorded
    with flow.lab.db() as db:
        recorded = db.get(TestRunRow, result_of(flow.ready.lab, "tls_versions")["run_id"]).raw["subject"]["versions"]
    assert recorded["TLS 1.2"] == {"state": "accepted", "detail": "handshake completed (TLSv1.2, ECDHE-ECDSA-AES128-SHA)"}
    assert given["intro"] == ["This is usually a server setting, not a code change. The server accepted TLS 1.2, with the older cipher suite "
                              "(the set of algorithms a connection uses) `ECDHE-ECDSA-AES128-SHA`. The file claims TLS 1.3 only."]
    assert given["warning"] == {"title": "Before you switch TLS 1.2 off:",
                                "text": "older clients and partner systems that can't use TLS 1.3 will no longer be able to connect."}
    where = given["where"]
    assert (where["title"], where["note"]) == ("Where the setting lives", "Use the row that matches how TLS is handled for this server.")
    assert where["columns"] == ["Where TLS is set up", "The setting", "To accept TLS 1.3 only"]
    assert [(r["place"], r["code"]) for r in where["rows"]] == [
        ("nginx", "ssl_protocols TLSv1.3;"), ("Apache", "SSLProtocol -all +TLSv1.3"),
        ("A cloud load balancer", "ELBSecurityPolicy-TLS13-1-3-2021-06"),
        ("Your own application", "context.minimum_version = ssl.TLSVersion.TLSv1_3")]
    assert where["rows"][0]["setting"] == "the `ssl_protocols` line (often in the `http` block of `nginx.conf`)" and where["rows"][0]["lead"] == ""
    assert where["rows"][2]["lead"] == ("Choose a policy that allows TLS 1.3 only (not every provider has one), and check it in your provider's "
                                        "own list. On an AWS Application or Network Load Balancer, for example:")
    assert where["after"] == ["For either option, change every existing line, including any in a site's own block, rather than adding another "
                              "one. Make sure every site on that address is covered, then reload the server."]
    one, two = given["options"]["items"]
    assert given["options"]["title"] == "Two ways to fix it"
    assert (one["title"], one["when"], one["note"]) == ("Option 1: switch TLS 1.2 off", "Choose this when nothing still connects with TLS 1.2.", "")
    assert one["steps"] == ["Check the access logs of the server or load balancer for connections that used TLS 1.2. Many servers do not log the "
                            "TLS version until you add it (nginx: `$ssl_protocol`; Apache: `%{SSL_PROTOCOL}x`).",
                            "If the log shows only TLS 1.3 over a normal period of use, apply the setting above.", "Run this test again."]
    assert (two["title"], two["when"]) == ("Option 2: keep TLS 1.2, with strong settings only", "Choose this when some clients or partners still need TLS 1.2.")
    assert two["steps"] == ["Remove the older cipher suite this test found, `ECDHE-ECDSA-AES128-SHA`, and keep only strong ones. The exact settings are below.",
                            "Correct the scanner file so that it says TLS 1.2 and TLS 1.3.", "Import the corrected file and run the tests again."]
    assert two["note"] == "This test checks TLS versions only. It will not show whether the old cipher suite is gone."
    exact = given["exact"]
    suites = ("ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
              "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305")
    assert exact["title"] == "Option 2: the exact settings"
    assert exact["note"] == ("These keep TLS 1.2 and TLS 1.3. For TLS 1.2 they keep only cipher suites that use ECDHE with AES-GCM or "
                             "ChaCha20-Poly1305, the same kinds of encryption TLS 1.3 uses. Copy each setting exactly, as one line, even where it wraps here.")
    assert exact["blocks"] == [{"place": "nginx", "code": f"ssl_protocols TLSv1.2 TLSv1.3;\nssl_ciphers {suites};"},
                               {"place": "Apache", "code": f"SSLProtocol -all +TLSv1.2 +TLSv1.3\nSSLCipherSuite {suites}"},
                               {"place": "AWS Application or Network Load Balancer (security policy)", "code": "ELBSecurityPolicy-TLS13-1-2-Res-2021-06"}]


# ---------------------------------------------------------------- Evidence Lab: the one line, the Code item, the code notes

def test_the_evidence_lab_line_in_every_state(flow):
    size = SIZE
    expected = {"not_connected": line("Fix available,", "code not connected", "plain"),
                "proving": line("Fix prepared:", f"{size}, proof running", "plain", busy=True),
                "failed": line("Fix not offered:", "the proof did not pass", "fail"),
                "ready": line("Fix ready:", f"{size}, proof passed", "pass"), "opened": line("Fix ready:", f"{size}, proof passed", "pass"),
                "waiting": line("Fix ready:", f"{size}, proof passed", "pass"), "ready_to_merge": line("Fix ready:", f"{size}, proof passed", "pass"),
                "merged": line("Fix merged:", f"{size}, proof passed", "plain"), "retesting": line("Fix merged:", f"{size}, proof passed", "plain"),
                "after": line("Fix merged:", f"{size}, proof passed", "plain")}
    for stage, wanted in expected.items():
        lines = lab_lines(getattr(flow, stage))
        assert lines[("official_vectors", "result")] == lines[("bad_signatures", "result")] == wanted, stage
        assert lines[("tls_versions", "result")] == TEXT_ONLY_LINE
        # results that are not failures have no line and keep their "Suggested fix" text
        for kind in ("certificate", "speed_size", "pq_readiness"):
            assert lines[(kind, "result")] is None and result_of(getattr(flow, stage).lab, kind)["suggested_fix"]
    # a line stands in place of the suggested fix: never both, never neither
    for stage in STAGES:
        for row in getattr(flow, stage).lab["rows"]:
            for shown in (row["result"], row["after"]):
                if shown is not None:
                    assert bool(shown["suggested_fix"]) != bool(shown["fix_line"]) and (shown["fix_line"] is not None) == (shown["tone"] == "fail")
    # after the retest: the passed after-results need no fix; the server test failed again and still has its suggestion
    after = lab_lines(flow.after)
    assert after[("official_vectors", "after")] is None and after[("bad_signatures", "after")] is None
    assert after[("tls_versions", "after")] == TEXT_ONLY_LINE
    assert lab_lines(flow.one_result) == {("bad_signatures", "result"): line("Fix available,", "code not connected", "plain")}


def test_evidence_lab_shows_no_change_no_diff_and_no_pull_request(flow):
    for stage in STAGES:
        words = " ".join(texts(getattr(flow, stage).lab))
        for word in ("pull request #1?", "Open pull request", "Merge pull request", "VERSION =", "1 <= r < N", "Download patch", "Approve"):
            assert word not in words, (stage, word)
    # while the proof runs, Evidence Lab keeps its first results and says why nothing can be started or downloaded
    during = flow.proving.lab
    assert during["view"] == "results" and during["retest"]["running"] is False
    assert during["retest"]["blocked_reason"] == during["download"]["blocked_reason"] == "A proof is running in Fixes. Wait until it has finished."
    assert "Tests are running" not in plain(during["subline"])


def test_each_result_says_which_code_it_ran_on(flow):
    merge_commit = state_of(flow.merged)["merge"]["merge_commit"]
    merged_code = (f"the merged fix: branch main, commit {merge_commit[:7]} (pull request #1), the same byte for byte as our bundled "
                   "acme-sign 1.4.3")
    for kind in ("official_vectors", "bad_signatures", "speed_size"):
        before, after = result_of(flow.after.lab, kind), result_of(flow.after.lab, kind, "after")
        for shown, component, code in ((before, "acme-sign 1.4.2", "the bundled demo version of acme-sign 1.4.2"), (after, "acme-sign 1.4.3", merged_code)):
            meta = shown["run_record"]["meta"]
            labels = [m["label"] for m in meta]
            assert labels.index("Code") == labels.index("Component") + 1  # right after "Component"
            assert meta[labels.index("Component")] == {"label": "Component", "value": component, "tag": "demo"}
            assert meta[labels.index("Code")] == {"label": "Code", "value": code, "tag": "demo"}
    for kind in ("tls_versions", "certificate", "pq_readiness"):  # a server test runs no code of ours
        for side in ("result", "after"):
            assert "Code" not in [m["label"] for m in result_of(flow.after.lab, kind, side)["run_record"]["meta"]]
    view = flow.after.lab
    assert view["view"] == "before_after"
    assert view["columns"] == {
        "test": "Test", "before": "Before: acme-sign 1.4.2", "after": "After: acme-sign 1.4.3",
        "before_note": [{"t": "text", "v": "the bundled demo version"}],
        "after_note": [{"t": "text", "v": "the merged fix, commit "}, {"t": "mono", "v": merge_commit[:7]}],
        "before_heading": "Before: acme-sign 1.4.2, the bundled demo version",
        "after_heading": f"After: acme-sign 1.4.3, the merged fix (commit {merge_commit[:7]})"}
    assert view["code_line"] == [{"t": "text", "v": f"Code they ran on: before, the bundled demo version of acme-sign 1.4.2; after, {merged_code}."}]
    # while the retest runs there is nothing to say about the "after" side yet
    running = flow.retesting.lab
    assert running["view"] == "before_after" and running["code_line"] is None
    assert running["columns"]["after_note"] == [] and running["columns"]["after_heading"] == "After: acme-sign 1.4.3"
    assert running["columns"]["before_heading"] == "Before: acme-sign 1.4.2, the bundled demo version"
    # before any retest: no columns and no sentence
    assert flow.ready.lab["columns"] is None and flow.ready.lab["code_line"] is None


def test_the_code_words_for_every_kind_of_code(flow):
    code = {"source": "bundled", "component_name": "acme-sign", "component_version": "1.4.2", "file_sha256": "0" * 64, "repository": None,
            "branch": None, "commit": None, "change_id": None, "pull_request_number": None}
    assert present.code_words(code) == "the bundled demo version of acme-sign 1.4.2"
    main = {**code, "source": "repository", "repository": "acme-sign", "branch": "main", "commit": "3f9c2ab" + "0" * 33}
    assert present.code_words(main) == "branch main, commit 3f9c2ab, the same byte for byte as our bundled acme-sign 1.4.2"
    branch = {**main, "component_version": "1.4.3", "branch": "fix/ecdsa-range-check", "commit": "8b1d4e7" + "0" * 33, "change_id": 1}
    assert present.code_words(branch) == ("the change on branch fix/ecdsa-range-check, commit 8b1d4e7, the same byte for byte as our "
                                          "bundled acme-sign 1.4.3")
    merged = {**branch, "branch": "main", "commit": "c41f0d2" + "0" * 33, "pull_request_number": 1}
    assert present.code_words(merged) == ("the merged fix: branch main, commit c41f0d2 (pull request #1), the same byte for byte as our "
                                          "bundled acme-sign 1.4.3")
    columns = present_fixes.code_columns("Before: acme-sign 1.4.2", "After: acme-sign 1.4.3", main, branch)
    assert columns["before_note"] == [{"t": "text", "v": "branch "}, {"t": "mono", "v": "main"}, {"t": "text", "v": ", commit "}, {"t": "mono", "v": "3f9c2ab"}]
    assert plain(columns["after_note"]) == "the change on branch fix/ecdsa-range-check, commit 8b1d4e7"
    assert columns["before_heading"] == "Before: acme-sign 1.4.2, branch main (commit 3f9c2ab)"
    assert columns["after_heading"] == "After: acme-sign 1.4.3, the change on branch fix/ecdsa-range-check (commit 8b1d4e7)"
    # when the results on one side did not all run on the same code, nothing is said about that side
    mixed = present_fixes.code_columns("Before: x", "After: y", None, merged)
    assert mixed["before_note"] == [] and mixed["before_heading"] == "Before: x" and present_fixes.code_line(None, merged) is None
    # the proof's runs say "the change on branch ..." in their own run record
    state = state_of(flow.ready)
    run_id = next(t["proof"]["run_id"] for t in state["proof"]["tests"] if t["kind"] == "bad_signatures")
    with flow.lab.db() as db:
        meta = flow.lab._result(db, db.get(TestRunRow, run_id))["run_record"]["meta"]
    assert {"label": "Code", "tag": "demo", "value": f"the change on branch fix/ecdsa-range-check, commit {state['change']['head_commit'][:7]}, "
                                                     "the same byte for byte as our bundled acme-sign 1.4.3"} in meta


# ---------------------------------------------------------------- the rules of wording

def test_nothing_is_called_ready_or_a_fix_before_its_proof_has_passed(flow):
    for stage in UNPROVEN:
        seen = getattr(flow, stage)
        detail = code_fix(seen)
        assert not PROVEN_WORDS.search(" ".join(texts(detail))), stage
        assert detail["what"]["label"] == "What it changes" and detail["what"]["server_line"] in (SERVER_LINE_UNPROVEN, None)
        assert detail["proof"]["state"] != "passed" and (detail["proof"]["badge"] or {}).get("tone") != "pass"
        assert not any(row["check"]["ok"] for row in proof_rows(detail).values()) or stage == "failed"
        for shown in lab_lines(seen).values():
            assert shown is None or (shown["lead"] != "Fix ready:" and shown["look"] != "pass" and "passed" not in shown["rest"])
    for stage in PROVEN:
        detail = code_fix(getattr(flow, stage))
        assert detail["what"]["label"] == "What it fixes" and detail["what"]["server_line"] == SERVER_LINE and detail["proof"]["state"] == "passed"


def test_wording_rules_hold_in_every_view(flow, corners):
    seen = [getattr(flow, stage) for stage in STAGES] + list(vars(corners).values())
    for views in seen:
        # what Evidence Lab says about a fix and about the code: its lines, the code sentence and the column notes
        lab_words = [views.lab["disclaimer"], *texts([row[side]["fix_line"] for row in views.lab["rows"] for side in ("result", "after") if row[side]]),
                     *texts(views.lab["code_line"]), *texts(views.lab["columns"])]
        for words in (" ".join(texts(views.fixes)), " ".join(lab_words)):
            # the one allowed use of the word, and no scores or time-to-hack
            assert words.lower().count("secure") == words.count(present.DISCLAIMER) == 1
            for banned in ("score", "time to hack", "time-to-hack", "unbreakable", "guarantee", "hacker", "mockup"):
                assert banned not in words.lower(), banned
        for detail in views.fixes["fixes"]:
            if detail["kind"] == "code":  # a template change is labelled as one, and never passed off as written by an AI model
                assert detail["labels"] == ["From a fix template"]


def test_only_the_buttons_that_apply_are_sent(flow, corners):
    wanted = {"one_result": ["connect"], "not_connected": ["connect"], "proving": [], "failed": ["run_proof_again"], "ready": ["open_pull_request"],
              "opened": ["merge", "download_patch"], "waiting": ["merge", "download_patch"], "ready_to_merge": ["merge", "download_patch"],
              "merged": ["retest_now", "download_patch"], "retesting": ["retest_now", "download_patch"], "after": ["retest_now", "download_patch"]}
    for stage, actions in wanted.items():
        detail = code_fix(getattr(flow, stage))
        assert [b["action"] for b in detail["actions"]["buttons"]] == actions, stage
        assert (detail["patch"] is not None) == ("download_patch" in actions) and (detail["merge_dialog"] is not None) == (stage == "ready_to_merge")
        assert (detail["approvers"]["options"] is not None) == (stage == "ready")  # the tick list only while reviewers can be picked
        # a button is switched on exactly when its action would be accepted now
        state = state_of(getattr(flow, stage))
        for shown in detail["actions"]["buttons"]:
            assert shown["enabled"] is (state["actions"][shown["action"]] is None)
    for views in [getattr(flow, stage) for stage in STAGES] + list(vars(corners).values()):
        for detail in views.fixes["fixes"]:
            if detail["kind"] == "text":
                assert detail["actions"] == {"buttons": [], "note": None}


# ---------------------------------------------------------------- the other ways a proof can end, and tampering

@pytest.fixture(scope="module")
def corners(flow):
    """Small plans (old TLS versions, certificate strength, bad signatures) in the same lab, each brought to one
    state that the main flow does not pass through. For every one: both views, and the state they were worded from."""
    lab, seen = flow.lab, {}
    # the server tests could not run during the proof, so they did not come out the same as before
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    address = plan.imp["addresses"][0]["address"]
    lab.confirm_address(plan.imp["id"], address, False)
    lab.connect_code(plan.id)
    lab.wait_until_idle(plan.id, 120)
    seen["server_changed"] = look(lab, plan.id)
    # ... and someone then edits the stored answer so that it says "offered"
    tamper(lab, f"UPDATE proof_reviews SET offered = 1 WHERE proof_id = {seen['server_changed'].states[0]['proof']['id']}")
    seen["review_edited"] = look(lab, plan.id)
    # the proof was interrupted: its tests never ran
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(lab, "_submit", lambda *a, **k: None)
        lab.connect_code(plan.id)
    seen["interrupted"] = look(lab, plan.id)
    # the changed code is not one of our registered components: nothing runs
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    propose = lab.engine.propose_change

    def not_ours(request):
        reply = propose(request)
        reply["files"]["acme_sign.py"] += "NOT_OURS = 1\n"
        return reply

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(lab.engine, "propose_change", not_ours)
        lab.connect_code(plan.id)
    seen["not_ours"] = look(lab, plan.id)
    # the plan changed after the proof had passed
    plan = small_plan(lab)
    proved(lab, plan)
    seen["small_ready"] = look(lab, plan.id)
    lab.add_test(plan.id, "mldsa_compare")
    seen["out_of_date"] = look(lab, plan.id)
    # a stored proof run changed by hand, at three moments: before a pull request, with one open, after the merge
    plan = small_plan(lab)
    ready = proved(lab, plan)
    run_id = next(r["proof"]["run_id"] for r in ready["proof"]["tests"] if r["kind"] == "bad_signatures")
    change_run = f"""UPDATE test_runs SET raw = json_set(raw, '$.subject.answers."r0-s0"', '%s') WHERE id = {run_id}"""
    tamper(lab, change_run % "accept")
    seen["run_edited"] = look(lab, plan.id)
    tamper(lab, change_run % "reject")
    assert code_fix(look(lab, plan.id))["status"]["key"] == "ready"  # put back exactly: believed again
    lab.open_pull_request(plan.id, FIX, ["b"])
    tamper(lab, change_run % "accept")
    seen["run_edited_with_pull_request"] = look(lab, plan.id)
    tamper(lab, change_run % "reject")
    lab.approve(plan.id, FIX, "b")
    lab.merge(plan.id, FIX)
    tamper(lab, change_run % "accept")
    seen["run_edited_after_merge"] = look(lab, plan.id)
    tamper(lab, change_run % "reject")
    # no bundled repository for the component: the failed signing test gets a text-only fix of its own
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(demo_repo, "bundled", lambda name: None)
        seen["no_repository"] = look(lab, plan.id)
    return SimpleNamespace(**seen)


CORNERS = ("server_changed", "review_edited", "interrupted", "not_ours", "small_ready", "out_of_date", "run_edited",
           "run_edited_with_pull_request", "run_edited_after_merge", "no_repository")


@pytest.mark.parametrize("corner", CORNERS)
def test_every_other_state_has_the_same_shape(corners, corner):
    seen = getattr(corners, corner)
    assert problems(seen.fixes, FIXES_VIEW, "fixes") == [] and problems(seen.lab, LAB_VIEW, "lab") == []


def test_a_small_plan_gets_its_own_numbers(corners):
    detail = code_fix(corners.small_ready)
    assert detail["list_source"] == "Came from 1 failed test: Bad signatures"
    assert plain(detail["source"]) == "Came from 1 failed test on signing component acme-sign 1.4.2: Bad signatures."
    passed = "The 1 test that runs the changed code passed, every control behaved as expected, and the 2 server tests came out the same as before."
    assert detail["proof"]["text"] == passed
    proof = section(detail, "proof")
    assert proof["line"] == "Passed: the 1 test that runs the changed code passed, every control behaved as expected, and the 2 server tests came out the same as before."
    # no speed test in this plan, so nothing is said about timing
    assert "timed side by side" not in proof["intro"]
    assert proof["intro"].startswith("The app applied this change on a new branch of its own copy of the code, then reran every locked test in your plan. ")
    assert [c["text"] for c in proof["verdict"]["checks"]] == ["The 1 test that runs the changed code passed.", "Every control behaved as expected.",
                                                               "The 2 server tests came out the same as before."]
    assert proof["verdict"]["shows"] == ["It shows that with this change the one failed test passes and the server tests came out as before.",
                                         "It doesn't show that the change is free of other faults, and it does nothing about the server finding."]


def test_a_proof_whose_server_tests_changed_is_not_offered(corners):
    detail = code_fix(corners.server_changed)
    named = ("2 of the 2 server tests did not come out the same as before: Old TLS versions, Couldn't run (address not confirmed); "
             "Certificate strength, Couldn't run (address not confirmed).")
    assert detail["status"]["word"] == "Proof failed"
    assert detail["proof"] == {"state": "failed", "badge": {"label": "Proof did not pass", "tone": "fail"}, "text": f"{named} The change is not offered.", "muted": None}
    proof = section(detail, "proof")
    assert proof["line"] == "Did not pass: 2 of the 2 server tests did not come out the same as before."
    assert proof["verdict"]["checks"] == [{"ok": True, "text": "The 1 test that runs the changed code passed."},
                                          {"ok": True, "text": "Every control behaved as expected in the tests that ran."},
                                          {"ok": False, "text": named}]
    rows = proof_rows(detail)
    assert rows["tls_versions"]["check"] == rows["certificate"]["check"] == {"ok": False, "text": "Not the same as before"}
    assert rows["tls_versions"]["control"] == "Control: not run, because the test couldn't run."
    assert detail["actions"] == {"buttons": [button("run_proof_again", "Run proof again", False)],
                                 "note": "Reruns all 3 tests in your plan. The change is offered only if the proof passes."}
    assert lab_lines(corners.server_changed)[("bad_signatures", "result")] == line("Fix not offered:", "the proof did not pass", "fail")


def test_an_interrupted_proof(corners):
    detail = code_fix(corners.interrupted)
    assert detail["status"] == {"key": "failed", "word": "Proof failed", "busy": False}
    text = "The proof was interrupted before every test had run: 0 of 3 tests finished."
    assert detail["proof"] == {"state": "failed", "badge": {"label": "Proof did not finish", "tone": "warn"}, "text": f"{text} The change is not offered.", "muted": None}
    proof = section(detail, "proof")
    assert proof["line"] == "Did not finish: 0 of 3 tests finished."
    assert proof["verdict"] == {"tone": "fail", "title": "Why this change is not offered", "checks": [{"ok": False, "text": text}], "shows_title": None, "shows": []}
    assert all(row["proof"] is None and row["waiting"] is None and row["check"] == {"ok": None, "text": "Did not run"} for row in proof_rows(detail).values())
    shown = facts(detail)
    assert "Proof finished" not in shown and "Evidence fingerprint of the proof (SHA-256)" not in shown
    assert re.fullmatch(r"\S+Z\. It was interrupted before every test had run\.", shown["Proof started"])
    assert [b["action"] for b in detail["actions"]["buttons"]] == ["run_proof_again"] and detail["actions"]["buttons"][0]["enabled"] is True
    assert lab_lines(corners.interrupted)[("bad_signatures", "result")] == line("Fix not offered:", "the proof did not finish", "fail")


def test_code_that_is_not_ours_is_never_run_and_the_view_says_so(corners):
    detail = code_fix(corners.not_ours)
    assert detail["status"]["word"] == "Proof failed"
    text = "The changed code is not the same as one of our demo components, byte for byte, so nothing was run."
    assert detail["proof"] == {"state": "failed", "badge": {"label": "Nothing was run", "tone": "warn"}, "text": f"{text} The change is not offered.", "muted": None}
    # no version number is claimed for code that is not one of our versions
    assert [plain(p) for p in detail["what"]["paragraphs"]] == [
        "Adds a range check on the two signature numbers (r and s) to acme-sign's signature check. 4 lines added and 1 removed."]
    proof, details = section(detail, "proof"), section(detail, "details")
    assert proof["line"] == "Nothing was run: the changed code is not one of our demo components." and proof["tables"] == []
    assert proof["intro"] == "No test was run for this change: only our own demo components ever run, and the changed code is not one of them."
    assert proof["verdict"]["checks"] == [{"ok": False, "text": text}]
    assert plain(details["ran_on"]["text"]) == ("Nothing. The file built from branch fix/ecdsa-range-check is not the same as any of our bundled "
                                               "demo components, byte for byte, so the app ran no test on it.")
    assert [f["label"] for f in details["ran_on"]["fingerprints"]] == ["The built file (SHA-256)"]
    assert details["ran_on"]["note"] == "This version of Evidence Lab only ever runs our own demo software."
    assert detail["actions"] == {"buttons": [], "note": None}  # there is nothing to run again
    assert lab_lines(corners.not_ours)[("bad_signatures", "result")] == line("Fix not offered:", "the changed code is not one of our demo components", "fail")


def test_a_proof_that_no_longer_covers_the_plan(corners):
    detail = code_fix(corners.out_of_date)
    text = "The test plan has changed since the proof ran, so the proof no longer covers exactly the tests in your plan."
    assert detail["status"]["word"] == "Proof failed"
    assert detail["proof"] == {"state": "failed", "badge": {"label": "Proof out of date", "tone": "warn"}, "text": f"{text} The change is not offered.", "muted": None}
    proof = section(detail, "proof")
    assert proof["line"] == "Out of date: the test plan has changed since the proof ran."
    # the proof record itself still stands, so its checks are listed under the reason
    assert proof["verdict"]["tone"] == "fail" and proof["verdict"]["title"] == "Why this change is not offered"
    assert proof["verdict"]["checks"] == [{"ok": False, "text": text}, {"ok": True, "text": "The 1 test that runs the changed code passed."},
                                          {"ok": True, "text": "Every control behaved as expected."},
                                          {"ok": True, "text": "The 2 server tests came out the same as before."}]
    # the added test has no first result yet, so a new proof can't start: the button is off and says why
    assert detail["actions"] == {"buttons": [button("run_proof_again", "Run proof again", False, enabled=False)],
                                 "note": "Run every test in the plan first, so there is a result to compare with."}
    assert detail["what"]["label"] == "What it changes" and detail["what"]["server_line"] == SERVER_LINE_UNPROVEN
    assert lab_lines(corners.out_of_date)[("bad_signatures", "result")] == line("Fix not offered:", "the test plan changed after the proof", "fail")


@pytest.mark.parametrize("corner", ["review_edited", "run_edited", "run_edited_with_pull_request", "run_edited_after_merge"])
def test_a_view_never_states_a_result_the_reviewer_did_not_give(corners, corner):
    """A stored proof run or proof review changed by hand: the view falls back on the fingerprint sentence, shows
    no tick, and nothing in it calls the change ready, passed or a fix."""
    seen = getattr(corners, corner)
    detail = code_fix(seen)
    assert detail["proof"] == {"state": "failed", "badge": {"label": "Proof can't be trusted", "tone": "warn"},
                               "text": f"{PROOF_CHANGED} The change is not offered.", "muted": None}
    proof = section(detail, "proof")
    assert proof["line"] == "Can't be trusted: the stored proof no longer matches its fingerprint."
    assert proof["verdict"] == {"tone": "fail", "title": "Why this change is not offered", "checks": [{"ok": False, "text": PROOF_CHANGED}],
                                "shows_title": None, "shows": []}
    assert all(row["check"] == {"ok": None, "text": "Not checked"} for row in proof_rows(detail).values())  # no tick survives
    assert "Evidence fingerprint of the proof (SHA-256)" not in facts(detail)
    assert not PROVEN_WORDS.search(" ".join(texts(detail)))
    assert detail["what"]["label"] == "What it changes" and detail["what"]["server_line"] == SERVER_LINE_UNPROVEN
    shown = lab_lines(seen)[("bad_signatures", "result")]
    assert (shown["look"], shown["busy"]) == ("fail", False) and shown["rest"].endswith("the stored proof no longer matches its fingerprint")
    if corner == "run_edited":
        # the changed run itself is no longer shown as passed either
        assert proof_rows(detail)["bad_signatures"]["proof"]["label"] == "Couldn't trust this run"
        assert detail["status"]["word"] == "Proof failed" and [b["action"] for b in detail["actions"]["buttons"]] == ["run_proof_again"]
        assert shown["lead"] == "Fix not offered:"
    if corner == "run_edited_with_pull_request":
        # the pull request stays on record, but nothing more can be recorded on it
        assert detail["status"]["word"] == "Proof failed" and detail["pull_request"]["title"].startswith("#1 ")
        assert [r["approve_label"] for r in detail["approvers"]["rows"]] == [None]
        assert detail["actions"] == {"buttons": [button("merge", "Merge pull request", True, enabled=False), PATCH_BUTTON],
                                     "note": f"{PROOF_CHANGED} Nothing more can be recorded on this pull request."}
        assert detail["merge_dialog"] is None
    if corner == "run_edited_after_merge":
        # the merge happened and stays on record; the view just no longer vouches for the proof
        assert detail["status"]["word"] == "Merged" and shown["lead"] == "Fix merged:" and "proof passed" not in shown["rest"]


def test_a_failed_signing_test_without_a_template_change_gets_a_text_only_fix(corners):
    view = corners.no_repository.fixes
    assert [(f["id"], f["kind"]) for f in view["fixes"]] == [(TLS, "text"), ("fix-bad-signatures", "text")]
    detail = fix_of(view, "fix-bad-signatures")
    assert detail["title"] == "Bad signatures: failed" and detail["status"]["word"] == "Text only" and detail["labels"] == []
    assert plain(detail["source"]) == "Came from 1 failed test on signing component acme-sign 1.4.2: Bad signatures."
    assert detail["what"] == {"label": "What it suggests", "server_line": None,
                              "paragraphs": [[{"t": "text", "v": "A suggestion in plain words. The app has not made a change for this finding."}]]}
    assert detail["approvers"]["text"] == "Whoever looks after this software, outside this app."
    (only,) = detail["sections"]
    assert only["line"] == "What to change, in plain words"
    # the suggestion is the sentence the "Suggested fix" box showed for this result
    assert only["suggestion"] == {"warning": None, "where": None, "options": None, "exact": None, "intro": [
        'Update the signing component to acme-sign 1.4.3, which checks that both parts of a signature are inside the allowed range before '
        'accepting it. Then press "Retest new version" to rerun the same tests on it.']}
    assert lab_lines(corners.no_repository)[("bad_signatures", "result")] == line("Text-only suggestion:", "see the suggestion", "dashed", fix_id="fix-bad-signatures")


# ---------------------------------------------------------------- wording that no flow here reaches, from hand-made states

def worded_from(lab, plan_id: int) -> tuple[dict, dict]:
    """What fixes.py hands to the wording for a plan's code fix: (its state, everything else)."""
    kept = {}
    real = present_fixes.code_fix
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(present_fixes, "code_fix", lambda fix, **more: kept.update(fix=fix, more=more) or real(fix, **more))
        lab.fixes_view(plan_id)
    return copy.deepcopy(kept["fix"]), copy.deepcopy(kept["more"])


def test_a_misbehaving_control_and_other_reasons_are_worded_from_the_review(flow):
    state, more = worded_from(flow.lab, flow.plan.id)
    assert state["status"] == "merged" and state["proof"]["review"]["offered"] is True
    state.update(status="failed", pull_request=None, merge=None)
    state["proof"]["state"] = "failed"
    review = state["proof"]["review"]
    review["offered"], review["checks"]["controls_behaved"] = False, False
    for test in state["proof"]["tests"]:
        if test["kind"] in ("bad_signatures", "certificate"):
            test["check"] = {**test["check"], "ok": False, "reason": "control_misbehaved"}
    for row in more["rows"]:
        if row["kind"] in ("bad_signatures", "certificate"):
            row["check"] = {**row["check"], "ok": False, "reason": "control_misbehaved"}
    detail = present_fixes.code_fix(state, **more)
    assert problems(detail, FIXES_VIEW["fixes"][0], "detail") == []
    sentence = "The control did not behave as expected in 2 tests: Certificate strength and Bad signatures."
    assert detail["proof"]["badge"] == {"label": "Proof did not pass", "tone": "fail"} and detail["proof"]["text"] == f"{sentence} The change is not offered."
    assert section(detail, "proof")["line"] == "Did not pass: the control did not behave as expected in 2 tests: Certificate strength and Bad signatures."
    assert {"ok": False, "text": "Control did not behave"} == proof_rows(detail)["bad_signatures"]["check"]
    assert detail["what"]["label"] == "What it changes" and not PROVEN_WORDS.search(" ".join(texts(detail)))
    # the code that ran was not the code that was checked
    review["checks"].update(controls_behaved=True, code_is_ours=False)
    detail = present_fixes.code_fix(state, **more)
    assert detail["proof"]["text"].startswith("The changed code is not the same as one of our demo components. ")
    # a proof in which no test runs the changed code shows nothing about the change
    review["checks"].update(code_is_ours=True, changed_code_passed=False)
    review["counts"].update(code=0, code_ok=0)
    detail = present_fixes.code_fix(state, **more)
    assert detail["proof"]["text"] == "No test in this proof runs the changed code, so it shows nothing about the change. The change is not offered."


def test_more_than_one_open_server_finding_and_none(flow):
    state, more = worded_from(flow.lab, flow.plan.id)
    two = present_fixes.code_fix(state, **{**more, "server_findings": 2})
    assert two["what"]["server_line"] == "This fixes the signing program. The server findings are separate and still open."
    assert section(two, "proof")["verdict"]["shows"][1] == ("It doesn't show that the change is free of other faults, and it does nothing about "
                                                            "the server findings.")
    none = present_fixes.code_fix(state, **{**more, "server_findings": 0})
    assert none["what"]["server_line"] is None
    assert section(none, "proof")["verdict"]["shows"][1] == "It doesn't show that the change is free of other faults."


def test_the_server_suggestion_names_a_cipher_suite_only_when_the_run_recorded_an_old_one(flow):
    with flow.lab.db() as db:
        (state, shown), = [(s, d) for s, d in flow.lab._fix_details(db, db.get(PlanRow, flow.plan.id)) if s["id"] == TLS]
    assert shown["title"] == "Server accepts TLS 1.2"

    def words(tls):
        return present_fixes.text_fix(state, titles=["Old TLS versions"], is_demo=True, result={"component": None, "label": "Failed",
                                      "suggested_fix": "The plain sentence."}, address="localhost:8443", tls=tls)

    # a strong suite was used for the old version: no suite is named and nothing is called "older"
    strong = words({"claimed": ["TLS 1.3"], "accepted": ["TLS 1.2"], "suites": {"TLS 1.2": "ECDHE-ECDSA-AES128-GCM-SHA256"}})
    given = section(strong, "suggestion")["suggestion"]
    assert given["intro"] == ["This is usually a server setting, not a code change. The server accepted TLS 1.2. The file claims TLS 1.3 only."]
    assert "older cipher suite" not in " ".join(texts(given)) and "ECDHE-ECDSA-AES128-GCM-SHA256`" not in " ".join(texts(given))
    two = given["options"]["items"][1]
    assert two["steps"][0] == "Keep only strong cipher suites (the sets of algorithms a connection uses) for TLS 1.2. The exact settings are below."
    assert two["note"] == "This test checks TLS versions only. It will not show which cipher suites the server accepts."
    assert problems(strong, FIXES_VIEW["fixes"][0], "detail") == []
    # the run did not record a suite at all: the same
    unknown = section(words({"claimed": ["TLS 1.3"], "accepted": ["TLS 1.2"], "suites": {"TLS 1.2": None}}), "suggestion")["suggestion"]
    assert unknown["intro"] == given["intro"]
    # any other case than "claims TLS 1.3 only, also accepts TLS 1.2" gets the plain sentence, the warning, and no exact settings
    other = words({"claimed": ["TLS 1.2", "TLS 1.3"], "accepted": ["TLS 1.0", "TLS 1.1"], "suites": {"TLS 1.0": "ECDHE-ECDSA-AES128-SHA", "TLS 1.1": None}})
    assert other["title"] == "Server accepts TLS 1.0 and TLS 1.1"
    given = section(other, "suggestion")["suggestion"]
    # (two versions were accepted, so no one handshake's suite is named)
    assert given["intro"] == ["This is usually a server setting, not a code change. The server accepted TLS 1.0 and TLS 1.1. The file claims "
                              "TLS 1.2 and TLS 1.3 only.", "The plain sentence."]
    one_old = section(words({"claimed": ["TLS 1.2", "TLS 1.3"], "accepted": ["TLS 1.1"], "suites": {"TLS 1.1": "ECDHE-ECDSA-AES128-SHA"}}), "suggestion")
    assert one_old["suggestion"]["intro"][0] == ("This is usually a server setting, not a code change. The server accepted TLS 1.1, with the older "
                                                 "cipher suite (the set of algorithms a connection uses) `ECDHE-ECDSA-AES128-SHA`. The file claims "
                                                 "TLS 1.2 and TLS 1.3 only.")
    assert given["warning"] == {"title": "Before you switch TLS 1.0 and TLS 1.1 off:",
                                "text": "older clients and partner systems that can't use TLS 1.2 or TLS 1.3 will no longer be able to connect."}
    assert given["where"] is given["options"] is given["exact"] is None
    assert section(other, "suggestion")["line"] == "A warning first, then what to change"
    assert problems(other, FIXES_VIEW["fixes"][0], "detail") == []


# ---------------------------------------------------------------- where the words live, and two races

def code_strings(module) -> list[tuple[str, bool]]:
    """Every piece of text in a module's code, leaving out the docstrings: (text, is it the reason an action is
    refused?). A refusal is text inside a `raise` or an `except` block, or in one of the functions that say why an
    action is refused."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body and isinstance(node.body[0], ast.Expr)
                  and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)}
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in docstrings:
            continue
        refusal, up = False, node
        while up in parents:
            up = parents[up]
            if isinstance(up, (ast.Raise, ast.ExceptHandler)) or (
                    isinstance(up, ast.FunctionDef) and (up.name.startswith("_no_") or up.name == "_pull_request_closed")):
                refusal = True
            if isinstance(up, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "PROOF_CHANGED" for target in up.targets):
                refusal = True
        found.append((node.value, refusal))
    return found


def sentences(module) -> dict[str, bool]:
    """The pieces of text in a module's code that read like words for a person (three words in a row):
    {text: is it, here or anywhere else in the module, the reason an action is refused?}."""
    found = {}
    for text, refusal in code_strings(module):
        if re.search(r"[A-Za-z']+ [A-Za-z']+ [A-Za-z']+", text):
            found[text] = found.get(text, False) or refusal
    return found


def test_fixes_and_changes_hold_no_wording_of_their_own():
    # fixes.py gathers and passes on: not one sentence in it
    assert sentences(fixes) == {}
    # changes.py: the only sentences are the reasons an action is refused, and what it writes into the repository
    # and the records (who made a commit, the merge message, the patch's footer, the names on the fixed reviewer
    # list). No status, no result, nothing a screen words.
    found = sentences(changes)
    assert {text for text, refusal in found.items() if not refusal} == {"Evidence Lab fix template", "Evidence Lab user", "Isogeny Evidence Lab (demo)",
                                                                       "Merge pull request #", "Demo reviewer A", "Demo reviewer B"}
    assert len([text for text, refusal in found.items() if refusal]) >= 20
    # (a refusal may name a button, as in "Retest now is available after the merge."; it never words a status or a result)
    screen_words = [*present_fixes.STATUS_WORDS.values(), *present_fixes.CHECK_WORDS.values(), present_fixes.VIEW_IN_FIXES, "Fix ready", "Fix prepared",
                    "Fix merged", "Fix available", "Fix not offered", "Text-only suggestion", "Proof passed", "Proof did not pass", "What it fixes",
                    "What it changes"]
    for module in (fixes, changes):
        constants = [text for text, _ in code_strings(module)]
        for word in screen_words:
            assert not any(word in constant for constant in constants), (module.__name__, word)
    # ... and the status a view shows is the key from the records, worded in one place
    assert set(present_fixes.STATUS_WORDS) == {"not_connected", "proving", "ready", "failed", "waiting", "ready_to_merge", "merged", "text_only"}


def test_the_views_decide_nothing_about_a_proof():
    """Whether a change is offered is the reviewer's answer, read through the gate in changes.py. The view code
    never calls the reviewer and never works out a verdict of its own."""
    for module in (fixes, present_fixes):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not names & {"review_proof", "reviewer", "RuleReviewer", "ProofReviewRow", "execute", "run_job", "subprocess"}, module.__name__
    imported = {alias.name for node in ast.walk(ast.parse(Path(present_fixes.__file__).read_text())) if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert "reviewer" not in imported and "changes" not in imported  # wording only: it is handed data, it fetches none


@contextmanager
def held(lab):
    """While this is open the harness jobs wait at the door until the Event it gives is set: a proof that is
    certainly still running, and that ends exactly when the test says so."""
    go, real = threading.Event(), lab.component_runner.run_job

    def waiting(job, **more):
        go.wait(60)
        return real(job, **more)

    lab.component_runner.run_job = waiting
    try:
        yield go
    finally:
        go.set()
        lab.component_runner.run_job = real


def test_a_proof_that_ends_while_a_view_is_put_together_is_never_shown_as_failed_or_stuck(lab):
    """The screen asks once a second while a proof runs. Whatever moment the last test finishes at, an answer
    says "Proving, ask again" or the settled result: never "Proof failed" for a proof that passed, and never
    "Proving" with nothing left to make the screen ask again."""
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    real_tests, main = lab._proof_tests, threading.current_thread()
    with held(lab) as go:
        lab.connect_code(plan.id)

        def tests_then_the_proof_ends(db, proof):
            out = real_tests(db, proof)  # read while the proof runs ...
            if threading.current_thread() is main:  # (the proof's own jobs read the same records: they pass straight through)
                go.set()
                lab.wait_until_idle(plan.id, 120)  # ... and the proof ends, review and all, before anything else is read
            return out

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(lab, "_proof_tests", tests_then_the_proof_ends)
            state = next(f for f in lab.fix_states(plan.id) if f["id"] == FIX)
    assert not lab.jobs.busy(plan.id)
    assert (state["status"], state["proof"]["state"]) == ("proving", "running")  # as it stood when the answer was begun
    assert all((row["job"] is None) != (row["proof"] is None) for row in state["proof"]["tests"])
    assert next(f for f in lab.fix_states(plan.id) if f["id"] == FIX)["status"] == "ready"  # and the next answer is the settled one
    # the same for the whole view: the proof of a second plan ends after its fixes are worded and before the view is finished
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    real_details = lab._fix_details
    with held(lab) as go:
        lab.connect_code(plan.id)

        def details_then_the_proof_ends(db, plan_row):
            out = real_details(db, plan_row)
            go.set()
            lab.wait_until_idle(plan.id, 120)
            return out

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(lab, "_fix_details", details_then_the_proof_ends)
            view = lab.fixes_view(plan.id)
    assert fix_of(view, FIX)["status"]["key"] == "proving" and view["busy"] is True  # so the screen asks again
    settled = lab.fixes_view(plan.id)
    assert fix_of(settled, FIX)["status"]["key"] == "ready" and settled["busy"] is False
