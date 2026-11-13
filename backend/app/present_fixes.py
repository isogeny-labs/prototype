"""The words of the Fixes step, and of what Evidence Lab says about a fix and about the code a result ran on.

Wording only. Nothing here decides anything: where a fix stands, what its proof found and which code a run ran
on arrive as data worked out from the stored records (changes.fix_states, the reviewer's proof review, the
worded results). Every number and name in a sentence is taken from that data, never typed in.

Until the proof of a change has passed, nothing here says the change fixes anything and nothing calls a fix
"ready": the tests have not shown it yet. The heading then reads "What it changes", and the line about the
server finding is the "is for the signing program only" one."""
from __future__ import annotations

from datetime import datetime

from . import present
from .research import CHANGE_LABEL, TITLES, join_and

TITLE = "Fixes"
SUBLINE = "Fixes for the findings in Evidence Lab. A code change is ready for review only after its proof has passed."
EMPTY = "No failed test has a fix. Fixes for failed tests show here."
STATUS_WORDS = {"not_connected": "Code not connected", "proving": "Proving", "ready": "Ready for review", "failed": "Proof failed",
                "waiting": "Waiting for approval", "ready_to_merge": "Ready to merge", "merged": "Merged", "text_only": "Text only"}
VIEW_IN_FIXES = "View in Fixes"
ONE_LOGIN = "This version has one login and no separate accounts. Whoever is at the keyboard records each approval, under the name shown."
LOGGED_IN = "(the person logged in)"
NOT_OFFERED = "The change is not offered."
SECTIONS_NOTE = "The change, its proof and the technical details appear below once the code is connected."
RAN_ON_NOTE = ("This version of Evidence Lab only ever runs our own demo software. If a change produced anything else, the app would "
               "run nothing and would not offer the change.")
# What the rule check found for one test of a proof (the reviewer's reason), in a word or two.
CHECK_WORDS = {"passed": "Passed", "no_slowdown": "No slowdown", "ran": "Ran (reports only)", "same_as_before": "Same as before",
               "did_not_pass": "Did not pass", "control_misbehaved": "Control did not behave", "changed": "Not the same as before",
               "no_run": "Did not run", "nothing_to_compare": "Nothing to compare with"}
# The cipher suites the "keep TLS 1.2" option leaves on: ECDHE with AES-GCM or ChaCha20-Poly1305 (checked on real
# nginx and Apache, docs/HANDOFF.md "Server TLS suggestion").
STRONG_SUITES = ("ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:"
                 "ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305")


def _t(value: str) -> dict:
    return {"t": "text", "v": value}


def _m(value: str) -> dict:
    return {"t": "mono", "v": value}


_DEMO = {"t": "demo", "v": "Demo data"}


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


def _series(parts: list[str]) -> str:
    """The parts of one sentence: "a", "a and b", "a, b, and c"."""
    return " and ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + ", and " + parts[-1]


def _lower(sentence: str) -> str:
    return sentence[:1].lower() + sentence[1:]


def size_words(change: dict) -> str:
    """How big a change is: "3 lines added and 1 removed", counted over its files."""
    added, removed = sum(f["added"] for f in change["files"]), sum(f["removed"] for f in change["files"])
    return f"{added} {_plural(added, 'line')} added and {removed} removed"


def proven(fix: dict) -> bool:
    """Has this code fix's proof passed, as the records stand now? Only then is it called a fix, or ready."""
    return (fix["status"] in ("ready", "waiting", "ready_to_merge", "merged")
            and fix["proof"] is not None and fix["proof"]["state"] == "passed")


def _duration(started: str, finished: str) -> str:
    seconds = (datetime.fromisoformat(finished.replace("Z", "+00:00")) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
    return f"{seconds:.1f} s" if seconds < 60 else f"{int(seconds // 60)} min {int(seconds % 60)} s"


# ------------------------------------------------------------------ why a change is not offered

def _stopped(fix: dict) -> dict | None:
    """Why a code fix has no proof result to go by, or None when its proof ran to the end and was reviewed.
    `line` is for Evidence Lab's one line, `badge` and `text` for the summary, `fold` for the folded Proof line."""
    change, proof = fix["change"], fix["proof"]
    if change["built"]["matches"] is None or proof is None:
        return {"line": "the changed code is not one of our demo components", "badge": "Nothing was run",
                "text": "The changed code is not the same as one of our demo components, byte for byte, so nothing was run.",
                "fold": "Nothing was run: the changed code is not one of our demo components."}
    if proof["state"] == "interrupted":
        finished = f"{proof['finished']} of {proof['total']} {_plural(proof['total'], 'test')} finished"
        return {"line": "the proof did not finish", "badge": "Proof did not finish",
                "text": f"The proof was interrupted before every test had run: {finished}.", "fold": f"Did not finish: {finished}."}
    if proof["review"] is not None and not proof["review"]["believed"]:
        problem = proof["review"]["problem"]
        return {"line": _lower(problem).rstrip("."), "badge": "Proof can't be trusted", "text": problem,
                "fold": f"Can't be trusted: {_lower(problem)}"}
    if proof["state"] == "passed" and not proof["covers_plan"] and fix["pull_request"] is None:
        # (once a pull request is open it stands on the proof it was opened with, whatever happens to the plan)
        return {"line": "the test plan changed after the proof", "badge": "Proof out of date",
                "text": "The test plan has changed since the proof ran, so the proof no longer covers exactly the tests in your plan.",
                "fold": "Out of date: the test plan has changed since the proof ran."}
    return None


# ------------------------------------------------------------------ Evidence Lab: the one line, and the code notes

def fix_line(fix: dict) -> dict:
    """The one line Evidence Lab shows on a failed result that has a fix. A fix is called ready only once its
    proof has passed; while the proof runs it is "prepared", and after a proof that did not pass, "not offered"."""
    def line(lead: str, rest: str, look: str, busy: bool = False) -> dict:
        return {"fix_id": fix["id"], "lead": lead, "rest": rest, "look": look, "busy": busy, "button": VIEW_IN_FIXES}
    if fix["kind"] != "code":
        return line("Text-only suggestion:", "a server setting" if fix["id"] == "fix-tls-versions" else "see the suggestion", "dashed")
    if fix["status"] == "not_connected":
        return line("Fix available,", "code not connected", "plain")
    size = size_words(fix["change"])
    if fix["status"] == "proving":
        return line("Fix prepared:", f"{size}, proof running", "plain", busy=True)
    if proven(fix):
        return line("Fix merged:", f"{size}, proof passed", "plain") if fix["status"] == "merged" else line("Fix ready:", f"{size}, proof passed", "pass")
    why = (_stopped(fix) or {"line": "the proof did not pass"})["line"]
    return line("Fix merged:", f"{size}, {why}", "fail") if fix["status"] == "merged" else line("Fix not offered:", why, "fail")


def _code_note(code: dict | None) -> list[dict]:
    """Which code one side of before and after ran on, in a few words (the second line under its heading)."""
    if code is None:
        return []
    if code["source"] != "repository":
        return [_t("the bundled demo version")]
    commit = _m(present.short_commit(code["commit"]))
    if code["pull_request_number"] is not None:
        return [_t("the merged fix, commit "), commit]
    lead = "the change on branch " if code["change_id"] is not None else "branch "
    return [_t(lead), _m(code["branch"]), _t(", commit "), commit]


def _code_heading(heading: str, code: dict | None) -> str:
    """The heading of one side's opened details: the column heading, then which code it ran on."""
    if code is None:
        return heading
    if code["source"] != "repository":
        return f"{heading}, the bundled demo version"
    commit = present.short_commit(code["commit"])
    if code["pull_request_number"] is not None:
        return f"{heading}, the merged fix (commit {commit})"
    lead = "the change on branch" if code["change_id"] is not None else "branch"
    return f"{heading}, {lead} {code['branch']} (commit {commit})"


def code_columns(before: str, after: str, before_code: dict | None, after_code: dict | None) -> dict:
    """The before and after headings of Evidence Lab, each with the code that side ran on. A code is None when
    the results on that side did not all run on the same code; nothing is said about it then."""
    return {"before": before, "after": after, "before_note": _code_note(before_code), "after_note": _code_note(after_code),
            "before_heading": _code_heading(before, before_code), "after_heading": _code_heading(after, after_code)}


def code_line(before_code: dict | None, after_code: dict | None) -> list[dict] | None:
    """The sentence under Evidence Lab's subline that says in full which code each side ran on."""
    if before_code is None or after_code is None:
        return None
    return [_t(f"Code they ran on: before, {present.code_words(before_code)}; after, {present.code_words(after_code)}.")]


# ------------------------------------------------------------------ where a fix came from

def _came_from(titles: list[str]) -> str:
    return f"Came from {len(titles)} failed {_plural(len(titles), 'test')}"


def _list_source(titles: list[str]) -> str:
    return f"{_came_from(titles)}: {', '.join(titles)}"


def _source(titles: list[str], where: str, what: str, tail: str = "") -> list[dict]:
    return [_t(f"{_came_from(titles)} on {where} "), _m(what), _t(f": {join_and(titles)}.{tail}")]


# ------------------------------------------------------------------ the fix template's own words
# Only the template knows what its change is about, so what a screen says about that change is kept by template.

def _range_check_words(name: str, version: str | None, size: str) -> dict:
    numbered = f", and gives the changed program the version number {version}" if version else ""
    reports = f" The changed program reports version {version}." if version else ""
    return {
        "title": f"{name} accepts out-of-range signatures",
        "available": [_t("A fix template exists for this failure: a ready-made change for a missing range check on the two signature "
                         "numbers (r and s), written for "), _m(name), _t("'s code. Connect the code to prepare the change and prove it.")],
        "changes": [_t("Adds a range check on the two signature numbers (r and s) to "), _m(name),
                    _t(f"'s signature check{numbered}. {size}.")],
        "fixes": [_t("Adds the missing range check to "), _m(name),
                  _t(f"'s signature check, so it now rejects signatures such as r = 0, s = 0, as the proof's tests show.{reports} {size}.")],
        "intro": ("Written from a fix template: a ready-made change for one known kind of bug, a missing range check when checking an "
                  "ECDSA signature. It was not written by an AI model, and it applies only where the code has exactly the lines it expects."),
    }


TEMPLATE_WORDS = {"ecdsa-range-check": _range_check_words}


# ------------------------------------------------------------------ the proof: its rows, what the rule check found

def proof_cell(result: dict | None, kind: str, side: str) -> dict | None:
    """A result badge and one line under it, for the proof table: `side` is "before" (the first result the proof
    is compared with) or "proof" (the run on the changed code). The download's report uses the same cells."""
    if result is None:
        return None
    short = result["short"]
    if kind == "speed_size" and side == "before" and result["code"] == "measured":
        # The proof times the old version again, side by side with the new one, so its numbers for the old
        # version differ a little from these: say which run these are from.
        short = short.replace("(medians).", "(medians, first run).")
    if kind == "speed_size" and side == "proof" and result["code"] in ("no_slowdown", "slowdown"):
        short = result["summary"]  # the fuller sentence names the side-by-side measurement the rule compares
    return {"label": result["label"], "tone": result["tone"], "short": short}


def _waiting(job: dict | None) -> dict | None:
    if job is None:
        return None
    if job["status"] == "waiting":
        return {"text": "Waiting", "detail": None, "percent": None}
    shown = present.status_view("running", job["progress_text"], job["progress_percent"])
    return {"text": shown["status_text"], "detail": shown["progress"]["text"], "percent": shown["progress"]["percent"]}


def _rule_check(row: dict, running: bool) -> dict:
    check = row["check"]
    if check is not None:
        return {"ok": bool(check["ok"]), "text": CHECK_WORDS.get(check["reason"], "Did not pass")}
    if row["proof"] is None:
        return {"ok": None, "text": "Not finished yet" if running else "Did not run"}
    return {"ok": None, "text": "Not checked yet" if running else "Not checked"}


def _proof_rows(rows: list[dict], group: str, running: bool) -> list[dict]:
    return [{"kind": r["kind"], "title": r["title"], "before": proof_cell(r["first"], r["kind"], "before"),
             "proof": proof_cell(r["proof"], r["kind"], "proof"), "waiting": _waiting(r["job"]) if r["proof"] is None else None,
             "control": r["proof"]["control"]["line"] if r["proof"] is not None else "", "check": _rule_check(r, running)}
            for r in rows if r["group"] == group]


def _tables(fix: dict, rows: list[dict]) -> list[dict]:
    proof = fix["proof"]
    running = proof["state"] == "running"
    code, server = _proof_rows(rows, "code", running), _proof_rows(rows, "server", running)
    need = "Each of these must pass, and its control must behave as expected."
    if any(r["kind"] == "mldsa_compare" for r in code):
        need += f" The {TITLES['mldsa_compare']} only reports numbers, so it only has to run."
    tables = []
    if code:
        tables.append({"heading": "Tests that run the changed code", "tag": "measured", "need": need,
                       "columns": ["Test", f"Before: {fix['component']['name']} {proof['baseline_version']}", "On the changed code", "Rule check"],
                       "rows": code})
    if server:
        tables.append({"heading": "Tests that don't run this code (they test the server)", "tag": "measured",
                       "need": "A code change can't affect these. They are rerun anyway and must come out the same as before.",
                       "columns": ["Test", "Before", "Rerun for this proof", "Rule check"], "rows": server})
    return tables


def _named(rows: list[dict]) -> str:
    """The tests a check did not hold for, each with the result its proof run got."""
    return "; ".join(f"{r['title']}, {r['proof']['label'] if r['proof'] is not None else 'no result'}" for r in rows)


def _checks(proof: dict, rows: list[dict]) -> list[dict]:
    """The reviewer's answer to its questions about a proof, as sentences. Each: {"ok", "text", "short"};
    `short` leaves out which tests, for the folded line."""
    counts, checks = proof["review"]["counts"], proof["review"]["checks"]
    missed = {group: [r for r in rows if r["group"] == group and r["check"] is not None and not r["check"]["ok"]] for group in ("code", "server")}
    out = []

    def add(ok: bool, short: str, named: list[dict] | None = None) -> None:
        out.append({"ok": ok, "short": short, "text": f"{short}: {_named(named)}." if named else f"{short}."})

    if not checks["code_is_ours"]:
        add(False, "The changed code is not the same as one of our demo components")
    n = counts["code"]
    if checks["changed_code_passed"]:
        add(True, "The 1 test that runs the changed code passed" if n == 1 else f"All {n} tests that run the changed code passed")
    elif n == 0:
        add(False, "No test in this proof runs the changed code, so it shows nothing about the change")
    else:
        add(False, "The 1 test that runs the changed code did not pass" if n == 1 else
            f"{len(missed['code'])} of the {n} tests that run the changed code did not pass", missed["code"])
    if checks["controls_behaved"]:
        # A test that could not run has no control result, so the sentence then speaks only of the tests that ran.
        every = all(r["proof"] is not None and r["proof"]["code"] != "couldnt_run" for r in rows)
        add(True, "Every control behaved as expected" + ("" if every else " in the tests that ran"))
    else:
        wrong = [r["title"] for r in rows if r["check"] is not None and r["check"]["reason"] == "control_misbehaved"]
        add(False, f"The control did not behave as expected in {len(wrong)} {_plural(len(wrong), 'test')}: {join_and(wrong)}")
    n = counts["server"]
    if n and checks["server_unchanged"]:
        add(True, f"The {n} server {_plural(n, 'test')} came out the same as before")
    elif n:
        add(False, "The 1 server test did not come out the same as before" if n == 1 else
            f"{len(missed['server'])} of the {n} server tests did not come out the same as before", missed["server"])
    return out


def _shows(rows: list[dict], server_findings: int) -> list[str]:
    """What a passed proof shows and what it doesn't, from its own rows."""
    now_pass = sum(1 for r in rows if r["group"] == "code" and r["first"] is not None and r["first"]["code"] == "failed"
                   and r["proof"] is not None and r["proof"]["code"] == "passed")
    parts = []
    if now_pass:
        parts.append(f"the {present.number_word(now_pass)} failed {_plural(now_pass, 'test passes', 'tests pass')}")
    if any(r["kind"] == "speed_size" and r["proof"] is not None and r["proof"]["code"] == "no_slowdown" for r in rows):
        parts.append("no slowdown beyond measured noise was found")
    if any(r["group"] == "server" for r in rows):
        parts.append("the server tests came out as before")
    if not parts:
        parts.append("every test that runs the changed code did what the rule asks of it")
    server = f", and it does nothing about the server {_plural(server_findings, 'finding')}" if server_findings else ""
    return [f"It shows that with this change {_series(parts)}.", f"It doesn't show that the change is free of other faults{server}."]


def _proof_words(fix: dict, rows: list[dict], server_findings: int) -> dict:
    """Everything said about the latest proof of a connected code fix: the summary's proof row (`state`, `badge`,
    `text`, `muted`), the folded line (`fold`) and the box under the tables (`verdict`)."""
    proof, stopped = fix["proof"], _stopped(fix)
    if proof is not None and proof["state"] == "running":
        running = f"Running: {proof['finished']} of {proof['total']} {_plural(proof['total'], 'test')} finished."
        return {"state": "running", "badge": None, "text": running, "muted": "Not offered yet.", "fold": running, "verdict": None}
    checks = _checks(proof, rows) if proof is not None and proof["review"] is not None and proof["review"]["believed"] else []
    if stopped is None and proof["review"]["offered"]:
        passed = _series([checks[0]["short"]] + [_lower(c["short"]) for c in checks[1:]]) + "."
        return {"state": "passed", "badge": {"label": "Proof passed", "tone": "pass"}, "text": passed, "muted": None,
                "fold": f"Passed: {_lower(passed)}",
                "verdict": {"tone": "pass", "title": "Why it is ready for review", "checks": [{"ok": c["ok"], "text": c["text"]} for c in checks],
                            "shows_title": "What this proof shows, and what it doesn't", "shows": _shows(rows, server_findings)}}
    if stopped is None:
        missed = [c for c in checks if not c["ok"]]
        stopped = {"badge": "Proof did not pass", "text": " ".join(c["text"] for c in missed),
                   "fold": "Did not pass: " + "; ".join(_lower(c["short"]) for c in missed) + "."}
        tone, reasons = "fail", checks
    else:
        # The proof record itself still stands when only the plan has changed since: its checks are shown under the reason.
        tone, reasons = "warn", [{"ok": False, "text": stopped["text"]}] + checks
    return {"state": "failed", "badge": {"label": stopped["badge"], "tone": tone}, "text": f"{stopped['text']} {NOT_OFFERED}", "muted": None,
            "fold": stopped["fold"],
            "verdict": {"tone": "fail", "title": "Why this change is not offered", "checks": [{"ok": c["ok"], "text": c["text"]} for c in reasons],
                        "shows_title": None, "shows": []}}


def proof_outcome(review: dict | None) -> str:
    """One proof in a sentence, for the download's report, which lists every proof of a change and not only the
    latest. `review` is the proof's review as the read gate lets it through (None when the proof has none)."""
    if review is None:
        return "This proof has no review: it was interrupted before every test had run."
    if review["offered"]:
        return "The proof passed."
    return review["problem"] or "The proof did not pass."


# ------------------------------------------------------------------ a code fix: the summary

def _approvers(fix: dict, reviewers: dict[str, str]) -> dict:
    request = fix["pull_request"]
    if request is not None:
        open_for_approval = fix["status"] == "waiting"
        rows = [{"id": a["reviewer"], "name": a["name"], "note": LOGGED_IN if a["reviewer"] == "you" else None, "demo": a["reviewer"] != "you",
                 "approved_at": a["approved_at"], "approved_text": "Approved" if a["approved_at"] else None,
                 "approve_label": (None if a["approved_at"] or not open_for_approval else
                                   "Approve" if a["reviewer"] == "you" else f"Approve as {a['name']}"),
                 "primary": a["reviewer"] == "you"} for a in request["approvals"]]
        return {"text": None, "options": None, "rows": rows, "footnote": ONE_LOGIN}
    if fix["status"] == "ready":
        options = [{"id": key, "name": name, "note": LOGGED_IN if key == "you" else None, "demo": key != "you", "checked": key == "you"}
                   for key, name in reviewers.items()]
        return {"text": None, "options": options, "rows": None, "footnote": ONE_LOGIN}
    text = ("Nobody yet: a change that is not offered can't get a pull request." if fix["status"] == "failed"
            else "You pick the reviewers once the proof has passed.")
    return {"text": text, "options": None, "rows": None, "footnote": None}


def _pull_request(fix: dict, holds: str) -> dict | None:
    request, merge = fix["pull_request"], fix["merge"]
    if request is None:
        return None
    if merge is not None:
        text = [_t("Merged "), {"t": "time", "v": merge["merged_at"]}, _t(" by the person logged in, after confirming. The demo repository's "),
                _m(fix["connection"]["branch"]), _t(" branch now holds "), _m(holds), _t(". Nothing was deployed.")]
    else:
        tail = " Every reviewer has approved. Not merged yet." if fix["status"] == "ready_to_merge" else ""
        text = [_t("Open since "), {"t": "time", "v": request["opened_at"]},
                _t(f". It stays inside the app; nothing is sent anywhere else.{tail}")]
    return {"title": f"#{request['number']} {request['title']}.", "text": text}


def _button(action: str, label: str, primary: bool, enabled: bool) -> dict:
    return {"action": action, "label": label, "primary": primary, "enabled": enabled}


def _actions(fix: dict, plan_tests: int, holds: str) -> dict:
    """The buttons that apply to this fix now, and the sentence under them. A button that would be refused right
    now is switched off, and the sentence then is the refusal itself."""
    status, refused, name = fix["status"], fix["actions"], fix["component"]["name"]
    patch = _button("download_patch", "Download patch", False, refused["download_patch"] is None)
    if status == "not_connected":
        note = (f"Connects a fresh copy of the small demo repository of {name} {fix['component']['version']} that comes with the app "
                "(the source code and its history of changes, in git's format), for this imported file and every fix in it. "
                "The proof then starts by itself.")
        return {"buttons": [_button("connect", "Connect demo code", True, refused["connect"] is None)],
                "note": f"{refused['connect']} {note}" if refused["connect"] else note}
    if status == "ready":
        return {"buttons": [_button("open_pull_request", "Open pull request", True, refused["open_pull_request"] is None)],
                "note": "Nothing goes into the main copy of the code until the reviewers you pick approve and you confirm the merge."}
    if status == "failed" and fix["pull_request"] is None and fix["proof"] is not None:
        every = "the 1 test" if plan_tests == 1 else f"all {plan_tests} tests"
        return {"buttons": [_button("run_proof_again", "Run proof again", False, refused["run_proof_again"] is None)],
                "note": refused["run_proof_again"] or f"Reruns {every} in your plan. The change is offered only if the proof passes."}
    if status in ("waiting", "ready_to_merge", "failed") and fix["pull_request"] is not None:
        waiting = [a["name"] for a in fix["pull_request"]["approvals"] if a["approved_at"] is None]
        never = "The app never merges on its own: you press the button and confirm."
        if status == "failed":
            note = f"{refused['merge']} Nothing more can be recorded on this pull request."
        elif waiting:
            note = f'"Merge pull request" unlocks when every reviewer has approved: waiting for {join_and(waiting)}. {never}'
        else:
            note = f"Every reviewer has approved. {never}"
        return {"buttons": [_button("merge", "Merge pull request", True, refused["merge"] is None), patch], "note": note}
    if status == "merged":
        note = (f"Reruns the same locked tests on {holds}, the code now on {fix['connection']['branch']}, and shows before and after in "
                'Evidence Lab. It does the same as "Retest new version" there.')
        return {"buttons": [_button("retest_now", "Retest now", True, refused["retest_now"] is None), patch],
                "note": refused["retest_now"] or note}
    return {"buttons": [], "note": None}


def _merge_dialog(fix: dict, holds: str) -> dict | None:
    if fix["status"] != "ready_to_merge":
        return None
    connection = fix["connection"]
    return {"title": f"Merge pull request #{fix['pull_request']['number']}?",
            "paragraphs": [[_t("This puts the change on the "), _m(connection["branch"]),
                            _t(" branch of the app's own copy of the demo repository "), _m(connection["repository"]),
                            _t(". After the merge, that branch holds "), _m(holds), _t(".")],
                           [_t("Every reviewer has approved. The app deploys nothing, and a merge can't be undone here.")]],
            "confirm": "Confirm merge", "cancel": "Cancel"}


def _server_line(fix: dict, server_findings: int) -> str | None:
    """Kevin's line about the server finding. It says "fixes" only once the proof has passed."""
    if not server_findings:
        return None
    lead = "This fixes the signing program." if proven(fix) else "This change is for the signing program only."
    return f"{lead} The server {_plural(server_findings, 'finding is', 'findings are')} separate and still open."


# ------------------------------------------------------------------ a code fix: the folded sections

def _change_section(fix: dict, words: dict, parts: list[dict] | None) -> dict:
    change, before = fix["change"], f"{fix['component']['name']} {fix['component']['version']}"
    names = [f["name"] for f in change["files"]]
    shown = []
    for number, part in enumerate(parts or [], start=1):
        removed, added = part["removed"], part["added"]
        shown.append({
            "title": f"{number}. {part['title']}", "why": part["why"],
            "before_label": {"lead": "Before:", "strong": before, "rest": (f", {removed} {_plural(removed, 'line')} removed (marked −)"
                                                                         if removed else ", nothing removed here")},
            "before": part["before"],
            "after_label": {"lead": "After:", "strong": "this change", "rest": (f", {added} {_plural(added, 'line')} added (marked +)"
                                                                               if added else ", nothing added here")},
            "after": part["after"]})
    intro = words["intro"] if parts is not None else "The changed lines could not be read from the app's copy of the repository."
    return {"key": "change", "title": "The change", "open": True, "intro": intro, "parts": shown,
            "line": f"{size_words(change)}, in {len(names)} {_plural(len(names), 'file')} ({', '.join(names)})"}


def _proof_section(fix: dict, rows: list[dict], said: dict) -> dict:
    timed = ", with the old and the new version timed side by side" if any(r["kind"] == "speed_size" for r in rows) else ""
    intro = (f"The app applied this change on a new branch of its own copy of the code, then reran every locked test in your plan{timed}. "
             "The runs went through the same steps as your first results: the same test runner, then the same automatic check that "
             "decides each result from what the run recorded. The fix template has no say in any result.")
    if fix["proof"] is None:
        intro = "No test was run for this change: only our own demo components ever run, and the changed code is not one of them."
    return {"key": "proof", "title": "Proof", "line": said["fold"], "open": False, "intro": intro,
            "tables": _tables(fix, rows) if fix["proof"] is not None else [], "verdict": said["verdict"]}


def _details_section(fix: dict, modes: list[str], ran_sha256: str | None) -> dict:
    connection, change, proof, request, merge = fix["connection"], fix["change"], fix["proof"], fix["pull_request"], fix["merge"]
    review = proof["review"] if proof is not None else None
    short = present.short_commit
    started_on = f"{connection['component']['name']} {connection['component']['version']}"
    repository = [_m(connection["repository"]), _t(" ")] + ([_DEMO] if connection["is_demo"] else [])

    def fact(label: str, value: list[dict], fingerprint: bool = False) -> dict:
        return {"label": label, "value": value, "fingerprint": fingerprint}

    facts = [fact("Repository", repository + [_t(", the app's own copy. Nothing is sent anywhere else.")]),
             fact("Starting point", [_t("branch "), _m(connection["branch"]), _t(", commit "), _m(short(change["base_commit"])),
                                     _t(" ("), _m(started_on), _t(")")]),
             fact("Change branch", [_m(change["branch"]), _t(", commit "), _m(short(change["head_commit"]))])]
    facts += [fact("File changed", [_m(f["name"]), _t(f": {f['added']} {_plural(f['added'], 'line')} added and {f['removed']} removed")])
              for f in change["files"]]
    if request is not None:
        value = [_t(f"#{request['number']}, opened "), {"t": "time", "v": request["opened_at"]}]
        if merge is not None:
            value += [_t("; merged "), {"t": "time", "v": merge["merged_at"]}, _t(" (merge commit "), _m(short(merge["merge_commit"])), _t(")")]
        facts.append(fact("Pull request", value))
    if review is not None:
        facts.append(fact("Proof finished", [{"t": "time", "v": review["reviewed_at"]},
                                             _t(f", after {_duration(proof['started_at'], review['reviewed_at'])} "), {"t": "tag", "v": "measured"}]))
    elif proof is not None and proof["state"] == "interrupted":
        facts.append(fact("Proof started", [{"t": "time", "v": proof["started_at"]}, _t(". It was interrupted before every test had run.")]))
    facts.append(fact("Mode", [_t(join_and([present.MODE_WORDS.get(mode, mode) for mode in modes]))]))
    fingerprint = review["record_sha256"] if review is not None else None
    if fingerprint:
        facts.append(fact("Evidence fingerprint of the proof (SHA-256)", [_t(fingerprint)], fingerprint=True))
    note = ("A branch is a separate line of work inside the repository, so the main copy stays untouched until a merge. A commit is "
            f"one saved state of the code, named by a short id such as {short(change['head_commit'])}.")
    if fingerprint:
        note += (' The full record of every run in this proof is in the files saved by "Download evidence", where the evidence '
                 "fingerprint of the proof can be checked. That fingerprint is listed inside the evidence file; it is not the "
                 "fingerprint of the file itself.")
    if request is not None:
        note += ' "Download patch" saves this change as one file that a developer can apply to another copy of the code.'
    return {"key": "details", "title": "Technical details", "line": "Repository, branches, commits, fingerprints and mode", "open": False,
            "facts": facts, "note": note, "ran_on": _ran_on(fix, ran_sha256)}


def _ran_on(fix: dict, ran_sha256: str | None) -> dict:
    """What the proof's tests ran on: never the changed file, always the registered demo component it is identical
    to. `ran_sha256` is that component's SHA-256 (None when the change is identical to none, and nothing ran)."""
    change, proof = fix["change"], fix["proof"]
    built, matches = change["built"], change["built"]["matches"]
    measured = {"label": "The built file (SHA-256)", "value": built["sha256"] or "", "tag": "measured"}
    if matches is None or proof is None:
        return {"title": "What the tests ran on",
                "text": [_t("Nothing. The file built from branch "), _m(change["branch"]),
                         _t(" is not the same as any of our bundled demo components, byte for byte, so the app ran no test on it.")],
                "fingerprints": [measured], "note": "This version of Evidence Lab only ever runs our own demo software."}
    component = f"{matches['name']} {matches['version']}"
    same = ("is exactly the same as that bundled component, byte for byte: the two fingerprints below match." if ran_sha256 == built["sha256"]
            else "is the same as that bundled component. The two fingerprints below should match, and they do not.")
    return {"title": "What the tests are running on" if proof["state"] == "running" else "What the tests ran on",
            "text": [_t("Our own bundled demo component, "), _m(component),
                     _t(". Before running anything, the app checked that the file built from branch "), _m(change["branch"]), _t(f" {same}")],
            "fingerprints": [measured, {"label": f"Bundled {component} (SHA-256)", "value": ran_sha256 or "", "tag": "demo"}],
            "note": RAN_ON_NOTE}


# ------------------------------------------------------------------ a code fix, whole

def code_fix(fix: dict, *, plan_id: int, titles: list[str], server_findings: int, plan_tests: int, reviewers: dict[str, str],
             patch_name: str | None, parts: list[dict] | None, rows: list[dict], modes: list[str], ran_sha256: str | None) -> dict:
    """One code fix as the Fixes step shows it. `fix` is its entry in changes.fix_states; the rest is what the
    words need besides: the titles of the failed tests it answers, how many server findings are open, how many
    tests the plan has, the reviewer list, the patch's file name, the changed lines (`parts`, None when they
    could not be read), the proof's tests with their worded results (`rows`), the modes its runs ran in, and
    the SHA-256 of the registered component that ran."""
    change, component = fix["change"], fix["component"]
    connected = change is not None
    matches = change["built"]["matches"] if connected else None
    words = TEMPLATE_WORDS[fix["template_id"]](component["name"], matches["version"] if matches else None, size_words(change) if connected else "")
    holds = f"{matches['name']} {matches['version']}" if matches else ""
    if connected:
        said = _proof_words(fix, rows, server_findings)
        what = words["fixes"] if proven(fix) else words["changes"]
        proof = {k: said[k] for k in ("state", "badge", "text", "muted")}
        sections = [_change_section(fix, words, parts), _proof_section(fix, rows, said), _details_section(fix, modes, ran_sha256)]
    else:
        what, sections = words["available"], []
        proof = {"state": "not_started", "badge": None, "muted": None,
                 "text": ("Not started. It starts by itself once the code is connected: every locked test in your plan is rerun on the "
                          "changed code. This takes about a minute.")}
    return {
        "id": fix["id"], "kind": "code", "title": words["title"], "list_source": _list_source(titles),
        "source": _source(titles, "signing component", f"{component['name']} {component['version']}"),
        "status": {"key": fix["status"], "word": STATUS_WORDS[fix["status"]], "busy": fix["status"] == "proving"},
        "labels": [CHANGE_LABEL], "is_demo": fix["connection"]["is_demo"] if connected else True,
        "what": {"label": "What it fixes" if proven(fix) else "What it changes", "paragraphs": [what],
                 "server_line": _server_line(fix, server_findings)},
        "proof": proof, "pull_request": _pull_request(fix, holds), "approvers": _approvers(fix, reviewers),
        "actions": _actions(fix, plan_tests, holds),
        "patch": ({"url": f"/api/plans/{plan_id}/fixes/{fix['id']}/patch", "filename": patch_name}
                  if patch_name and fix["actions"]["download_patch"] is None else None),
        "merge_dialog": _merge_dialog(fix, holds), "sections": sections, "sections_note": None if connected else SECTIONS_NOTE,
    }


# ------------------------------------------------------------------ a text-only fix

def _old_suite(suite: str | None) -> bool:
    """Is this one of the old cipher suites the suggestion may name? Only a suite whose name ends in "-SHA":
    in OpenSSL's names those are the ones that use SHA-1 with a CBC (or older) cipher, such as
    ECDHE-ECDSA-AES128-SHA. The test records only the suite each handshake used; it does not scan for others."""
    return bool(suite) and suite.endswith("-SHA")


def _join_or(items: list[str]) -> str:
    return "".join(items) if len(items) <= 1 else ", ".join(items[:-1]) + " or " + items[-1]


def _tls_words(tls: dict, box: str) -> dict:
    """The server TLS finding's own words, built from the failed test's recorded outcome. `tls`: the address, what
    the file claims, the versions accepted outside the claim, and the cipher suite each of those handshakes used.
    The fuller suggestion (where the setting lives, two options, exact settings) was written and checked for one
    case: the file claims TLS 1.3 only and the server also accepts TLS 1.2. Any other case gets the plain
    sentence (`box`, what the "Suggested fix" box said) with the same warning."""
    claimed, accepted = join_and(tls["claimed"]), join_and(tls["accepted"])
    # A suite is named only when exactly one version was accepted outside the claim: the sentence then speaks of
    # that one recorded handshake, and of no other.
    suite = tls["suites"].get(tls["accepted"][0]) if len(tls["accepted"]) == 1 else None
    suite = suite if _old_suite(suite) else None
    with_suite = f", with the older cipher suite (the set of algorithms a connection uses) `{suite}`" if suite else ""
    intro = f"This is usually a server setting, not a code change. The server accepted {accepted}{with_suite}. The file claims {claimed} only."
    warning = {"title": f"Before you switch {accepted} off:",
               "text": f"older clients and partner systems that can't use {_join_or(tls['claimed'])} will no longer be able to connect."}
    title = f"Server accepts {accepted}"
    if (tls["claimed"], tls["accepted"]) != (["TLS 1.3"], ["TLS 1.2"]):
        return {"title": title, "line": "A warning first, then what to change",
                "what": f"A server setting, not a code change: stop accepting {accepted}, or correct the scanner file if it is meant to stay on.",
                "suggestion": {"intro": [intro, box], "warning": warning, "where": None, "options": None, "exact": None}}
    where = {
        "title": "Where the setting lives", "note": "Use the row that matches how TLS is handled for this server.",
        "columns": ["Where TLS is set up", "The setting", f"To accept {claimed} only"],
        "rows": [
            {"place": "nginx", "setting": "the `ssl_protocols` line (often in the `http` block of `nginx.conf`)", "lead": "",
             "code": "ssl_protocols TLSv1.3;"},
            {"place": "Apache", "setting": "the `SSLProtocol` line (in the main server config, or in every virtual host on the address)",
             "lead": "", "code": "SSLProtocol -all +TLSv1.3"},
            {"place": "A cloud load balancer",
             "setting": ("the security policy (also called a TLS or SSL policy) on the load balancer's HTTPS or TLS listener, the part "
                         "that accepts incoming connections"),
             "lead": (f"Choose a policy that allows {claimed} only (not every provider has one), and check it in your provider's own "
                      "list. On an AWS Application or Network Load Balancer, for example:"),
             "code": "ELBSecurityPolicy-TLS13-1-3-2021-06"},
            {"place": "Your own application", "setting": "the minimum TLS version in your application's own TLS settings",
             "lead": f"Set the minimum to {claimed}. In Python, for example:", "code": "context.minimum_version = ssl.TLSVersion.TLSv1_3"},
        ],
        "after": ["For either option, change every existing line, including any in a site's own block, rather than adding another one. "
                  "Make sure every site on that address is covered, then reload the server."]}
    both = join_and(tls["accepted"] + tls["claimed"])
    keep_strong = (f"Remove the older cipher suite this test found, `{suite}`, and keep only strong ones. The exact settings are below." if suite
                   else f"Keep only strong cipher suites (the sets of algorithms a connection uses) for {accepted}. The exact settings are below.")
    options = {"title": "Two ways to fix it", "items": [
        {"title": f"Option 1: switch {accepted} off", "when": f"Choose this when nothing still connects with {accepted}.",
         "steps": [f"Check the access logs of the server or load balancer for connections that used {accepted}. Many servers do not log "
                   "the TLS version until you add it (nginx: `$ssl_protocol`; Apache: `%{SSL_PROTOCOL}x`).",
                   f"If the log shows only {claimed} over a normal period of use, apply the setting above.",
                   "Run this test again."],
         "note": ""},
        {"title": f"Option 2: keep {accepted}, with strong settings only", "when": f"Choose this when some clients or partners still need {accepted}.",
         "steps": [keep_strong, f"Correct the scanner file so that it says {both}.", "Import the corrected file and run the tests again."],
         "note": ("This test checks TLS versions only. It will not show " +
                  ("whether the old cipher suite is gone." if suite else "which cipher suites the server accepts."))}]}
    exact = {"title": "Option 2: the exact settings",
             "note": (f"These keep {both}. For {accepted} they keep only cipher suites that use ECDHE with AES-GCM or ChaCha20-Poly1305, "
                      f"the same kinds of encryption {claimed} uses. Copy each setting exactly, as one line, even where it wraps here."),
             "blocks": [{"place": "nginx", "code": f"ssl_protocols TLSv1.2 TLSv1.3;\nssl_ciphers {STRONG_SUITES};"},
                        {"place": "Apache", "code": f"SSLProtocol -all +TLSv1.2 +TLSv1.3\nSSLCipherSuite {STRONG_SUITES}"},
                        {"place": "AWS Application or Network Load Balancer (security policy)", "code": "ELBSecurityPolicy-TLS13-1-2-Res-2021-06"}]}
    return {"title": title, "line": "A warning first, where the setting lives, and two ways to fix it",
            "what": (f"A server setting, not a code change: stop accepting {accepted}, or keep it with strong settings only and correct the "
                     "scanner file. The suggestion below says where the setting lives and gives two ways to do it."),
            "suggestion": {"intro": [intro], "warning": warning, "where": where, "options": options, "exact": exact}}


def text_fix(fix: dict, *, titles: list[str], is_demo: bool, result: dict, address: str | None, tls: dict | None) -> dict:
    """One text-only fix as the Fixes step shows it: a suggestion in words that the app has not made or tested.
    `result` is the worded failed result it answers; `address` is the server it is about (None for a test of the
    signing component); `tls` is the recorded outcome of a failed "Old TLS versions" test, when it is that."""
    on_server = address is not None
    claims = f" The file claims {join_and(tls['claimed'])} only." if tls else ""
    source = _source(titles, "server" if on_server else "signing component", address if on_server else str(result["component"]), claims)
    if tls:
        words = _tls_words(tls, result["suggested_fix"])
        approves = "Your own server team, outside this app. The app never changes your server."
    else:
        words = {"title": f"{titles[0]}: {_lower(result['label'])}", "line": "What to change, in plain words",
                 "what": "A suggestion in plain words. The app has not made a change for this finding.",
                 "suggestion": {"intro": [result["suggested_fix"]], "warning": None, "where": None, "options": None, "exact": None}}
        approves = ("Your own server team, outside this app. The app never changes your server." if on_server
                    else "Whoever looks after this software, outside this app.")
    return {
        "id": fix["id"], "kind": "text", "title": words["title"], "list_source": _list_source(titles), "source": source,
        "status": {"key": "text_only", "word": STATUS_WORDS["text_only"], "busy": False}, "labels": [], "is_demo": is_demo,
        "what": {"label": "What it suggests", "paragraphs": [[_t(words["what"])]], "server_line": None},
        "proof": {"state": "none", "badge": None, "muted": None,
                  "text": "None. This suggestion is text only: the app has not applied it or tested it."},
        "pull_request": None, "approvers": {"text": approves, "options": None, "rows": None, "footnote": None},
        "actions": {"buttons": [], "note": None}, "patch": None, "merge_dialog": None,
        "sections": [{"key": "suggestion", "title": "The suggestion", "line": words["line"], "open": True, "suggestion": words["suggestion"]}],
        "sections_note": None,
    }


# ------------------------------------------------------------------ the whole step

def view(plan_id: int, is_demo: bool, fixes: list[dict], busy: bool) -> dict:
    return {"plan_id": plan_id, "is_demo": is_demo, "title": TITLE, "subline": SUBLINE, "disclaimer": present.DISCLAIMER,
            "list_title": f"Open findings with a fix ({len(fixes)})", "empty_text": None if fixes else EMPTY, "fixes": fixes, "busy": busy}
