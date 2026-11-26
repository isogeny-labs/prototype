"""Evidence as the full record (design refactor, section 6; decisions H and I, 26 November 2026): every sentence of the
Timeline, Approvals and decisions, Evidence files and the history in an item's panel.

Words only. Nothing here reads a record, decides anything or words a result: a result's word and tone are handed in as
the reviewer or its own page gave them, and repeated as they are. What this module adds is what happened (a sentence for
each kind of record), who did it and where a name came from, and the one line that says what decides a result. A person
is never named as the decider of a result.
"""

from __future__ import annotations

from app.names import join_and

# ---------------------------------------------------------------- the two filters

AREAS = (
    ("observe", "Observatory and Verify"),
    ("advisories", "Advisories"),
    ("checks", "Checks"),
    ("fixes", "Fixes"),
    ("migration", "Migration plan"),
    ("dependencies", "Dependencies"),
    ("watch", "Change watch"),
    ("assessment", "The assessment"),
)
AREA_LABELS = dict(AREAS)
AREA_KEYS = tuple(key for key, _ in AREAS)
ALL_AREAS = "All"
KINDS = (
    ("runs", "Runs and results"),
    ("people", "What people did"),
    ("system", "Changes to a system"),
    ("files", "Files in and out"),
)
KIND_LABELS = dict(KINDS)
KIND_KEYS = tuple(key for key, _ in KINDS)
EVERYTHING = "Everything"
# The page each area's own work is on (History of that page opens the timeline with the area chosen).
AREA_PAGES = {
    "observe": "inventory/verify",
    "advisories": "advisories",
    "checks": "checks",
    "fixes": "fixes",
    "migration": "migration/systems",
    "dependencies": "migration/dependencies",
    "watch": "change-watch",
    "assessment": "overview",
}

TIMELINE_TITLE = "Timeline"
TIMELINE_SUBLINE = (
    "Everything that happened in this assessment, newest first: every run and what it found, every decision with who "
    "made it, every change to a system, and every file in and out. Reading it runs nothing."
)
TIMELINE_EMPTY = "Nothing has happened in this assessment yet."
TIMELINE_NOTHING_FITS = "Nothing in this assessment fits what is chosen here."
DECISIONS_TITLE = "Approvals and decisions"
DECISIONS_SUBLINE = (
    "Every decision a person made in this assessment, with who and when. No person approves a result: the separate "
    "reviewer decides each one by fixed rules, and Results shows them."
)
DECISIONS_EMPTY = "No person has decided anything in this assessment yet."
FILES_TITLE = "Evidence files"
FILES_SUBLINE = (
    "Every download of the signed evidence file, with its time, its fingerprint and who downloaded it. The JSON file "
    "is the record; the report is a readable copy and is not signed."
)
FILES_EMPTY = "The evidence file has not been downloaded yet."

# ---------------------------------------------------------------- who, and what decides a result

NOT_RECORDED = "Not recorded (before names were kept)"
BY_REVIEWER = "decided by the separate reviewer"
BY_RULES = "decided by fixed rules"
WHO_DECIDES = (
    "Who decides a result: the separate reviewer, by fixed rules, on every run. No person approves a result. What "
    "people did about it is in this history too."
)
WHO_DECIDES_CLAIM = (
    "Who decides a result: fixed rules compare the claim with what was found, on every Verify run. No person approves "
    "a result. What people did about it is in this history too."
)
NAMES_NOTE = (
    "Who: the account that was logged in, where the app has one (hosted, with a GitHub login); otherwise the name "
    "typed once in Settings (Who decides), or “You”. The app does not check who is at the keyboard beyond its login. "
    "Demo reviewers are Demo data. A record made before names were kept says so, and nothing is filled in afterwards."
)
SOURCE_LABELS = {
    "account": "The account that was logged in",
    "typed": "The name typed once in Settings (Who decides)",
    "default": "No name was typed in Settings, so it reads “You”",
    "reviewer": "The reviewer picked for this approval",
    "signoff": "The name typed in the Close box",
    "decides": "The name this record was made under (Who decides, or “You”)",
    "clock": "The Watch list's own timer, not a person",
    "author": "The author named in the commit",
    "none": "This was recorded before names were kept",
}
DEMO_DATA = "Demo data"
FROM_OTTO = "From Otto"
APART_LABEL = "From a developer's change"
APART_NOTE = (
    "A developer's change is not the system until someone merges it. What Change watch ran and what came in are listed "
    "under Change watch only, and are counted with nothing else."
)
BUTTONS = {
    "run": "Run",
    "run_all": "Run all",
    "retest": "Retest new version",
    "retest_now": "Retest now, on Fixes",
    "measure_status": "Measure status",
    "measure_dependencies": "Measure on a public copy",
    "verify": "Verify claims",
    "code_connected": "Connect demo code",
    "proof_started": "Run proof again",
    "pull_request_opened": "Open pull request",
    "approved": "Approve",
    "merged": "Merge pull request",
    "change_tried": "Try on a test copy",
    "approval_asked": "Ask for approval",
    "change_approved": "Approve",
    "applied": "Apply",
    "rolled_back": "Roll back",
    "picked_tests_run": "Run the picked tests",
    "demo_change_brought_in": "Bring in a demo change",
    "evidence_downloaded": "Download evidence",
    "closed": "Close and sign off",
    "marked_reviewed": "Mark reviewed",
    "dig_deeper": "Dig deeper",
    "file_imported": "Import",
    "dependency_list_added": "Add dependency list",
    "assessment_started": "New assessment",
    "assessment_rerun": "Rerun as new assessment",
    "address_confirmed": "I own this system or am allowed to test it",
    "address_unconfirmed": "I own this system or am allowed to test it",
    "test_added": "Add test",
    "test_removed": "Remove",
    "tests_reordered": "Move",
    "option_chosen": "Choose",
    "setting_changed": "Settings",
    "library_tied": "Part of",
    "assessment_changed": "Assessment details",
}


def button(kind: str | None, detail: dict | None = None) -> str | None:
    """The button a press was made with, as its page names it."""
    detail = detail or {}
    if kind == "measure_status" and detail.get("again"):
        return "Measure again"
    if kind == "picked_tests_run" and detail.get("again"):
        return "Run again"
    if kind == "measure_dependencies" and not detail.get("row"):
        return "Measure all"
    if kind == "file_imported" and detail.get("demo_file"):
        return "Use demo file"
    return BUTTONS.get(str(kind))


def who(name: str | None, source: str, demo: bool = False, pressed: str | None = None) -> dict:
    """One name as every view carries it: the name, where it came from, and the button where a press recorded it."""
    return {
        "name": name if name and source != "none" else NOT_RECORDED,
        "source": source,
        "source_label": SOURCE_LABELS[source],
        "demo": bool(demo),
        "recorded": source != "none",
        "button": pressed,
    }


def nobody() -> dict:
    return who(None, "none")


def started_by(person: dict) -> str:
    """ "started by You, with Run all" (or that no name was kept), for a run in an item's history."""
    if not person["recorded"]:
        return f"Who started it: {NOT_RECORDED[0].lower()}{NOT_RECORDED[1:]}"
    return f"started by {person['name']}" + (f", with {person['button']}" if person.get("button") else "")


def by(person: dict) -> str:
    return f"by {person['name']}" if person["recorded"] else NOT_RECORDED


# ---------------------------------------------------------------- small helpers


def _t(value: object) -> dict:
    return {"t": "text", "v": str(value)}


def _m(value: object) -> dict:
    return {"t": "mono", "v": str(value)}


def count(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def short(value: object, limit: int = 12) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit]


def plain(lead: str, rest: list[dict]) -> str:
    """A sentence as one line of plain text (for the search, the report and a panel's heading)."""
    return (lead + "".join(part["v"] for part in rest)).strip()


def reviewers(names: list[str]) -> str:
    return join_and([str(n) for n in names]) if names else "nobody"


# ---------------------------------------------------------------- the sentences of the timeline: (bold lead, the rest)

Sentence = tuple[str, list[dict]]


def assessment_started(title: str, purpose: str | None, rerun_of: str | None = None) -> Sentence:
    rest = f" ({purpose})." if purpose else "."
    if rerun_of:
        rest += f" It is a rerun of {rerun_of}: the same scanner file, brought in again."
    return f"{title} started", [_t(rest)]


def assessment_changed(changed: dict) -> Sentence:
    said = []
    if "name" in changed:
        said.append(f"renamed to “{changed['name']}”")
    if "purpose" in changed:
        said.append(f"purpose set to {changed['purpose']}")
    if "reference" in changed:
        said.append(f"reference set to “{changed['reference']}”" if changed["reference"] else "reference cleared")
    if "project_id" in changed:
        said.append("moved to another project")
    if "archived" in changed:
        said.append("archived (hidden; nothing is deleted)" if changed["archived"] else "taken out of the archive")
    return "Assessment details changed:", [_t(" " + (join_and(said) if said else "no field named") + ".")]


def details_changed(purpose: str | None, reference: str | None) -> Sentence:
    said = [f"purpose {purpose}"] if purpose else []
    said.append(f"reference “{reference}”" if reference else "no reference")
    return "Assessment details changed:", [_t(" " + join_and(said) + ".")]


def closed(name: str, note: str | None) -> Sentence:
    rest = [_t(f" by {name}. It is read-only from here on.")]
    if note:
        rest.append(_t(f" Note: {note}"))
    return "Closed and signed off", rest


def file_imported(filename: str, claims: int, servers: int, programs: int) -> Sentence:
    what = [count(claims, "claim")]
    places = [count(n, word) for n, word in ((servers, "server"), (programs, "program")) if n]
    if places:
        what.append(" and ".join(places))
    return "Brought in", [_t(" "), _m(filename), _t(": " + ", ".join(what) + ".")]


def evidence_downloaded(fingerprint: str) -> Sentence:
    return "Evidence file downloaded.", [_t(" Fingerprint "), _m(short(fingerprint)), _t(".")]


def address_ticked(address: str, pressed_on: bool, confirmed: bool) -> Sentence:
    if not pressed_on:
        return "Took back “I own this system”", [
            _t(" for "),
            _m(address),
            _t(". Nothing connects to it until it is ticked again."),
        ]
    if not confirmed:
        return "Ticked “I own this system”", [
            _t(" for "),
            _m(address),
            _t(", but the name could not be looked up, so it is not confirmed and nothing connects to it."),
        ]
    return "Confirmed “I own this system”", [_t(" for "), _m(address), _t(".")]


def verify_ran(claims: int) -> Sentence:
    return "Verify:", [_t(f" the {count(claims, 'claim')} of your file, checked against what was found.")]


def test_added(titles: list[str], back: int) -> Sentence:
    what = join_and([f"“{t}”" for t in titles]) if titles else "a test"
    tail = " It was in the plan before: it comes back with its runs." if back and len(titles) == back else ""
    return "Added to the test plan:", [_t(f" {what}.{tail}")]


def test_removed(title: str | None) -> Sentence:
    return "Removed from the test plan:", [
        _t(f" “{title}”. Its runs are kept." if title else " a test. Its runs are kept.")
    ]


def tests_reordered(titles: list[str]) -> Sentence:
    order = f" The order is now: {join_and(titles)}." if titles else ""
    return "Changed the order of the test plan.", [_t(order)] if order else []


def ran(kind: str, n: int, title: str | None = None) -> Sentence:
    """A press that started runs: Run, Run all, Measure status, Measure on a public copy."""
    if kind == "run":
        return "Run:", [_t(f" “{title}”." if title else " one test of the plan.")]
    if kind == "run_all":
        return "Run all:", [_t(f" the {count(n, 'test')} in the plan.")]
    if kind == "measure_status":
        return "Measure status:", [_t(f" the post-quantum status of {count(n, 'system')}.")]
    return "Measure on a public copy:", [_t(f" {count(n, 'library', 'libraries')}.")]


def ran_alone(title: str, ran_on: str | None, came_from: str | None) -> Sentence:
    """One run with no press on record (before names were kept): listed by itself."""
    lead = f"{came_from}:" if came_from else "Ran:"
    return lead, [_t(f" “{title}”" + (f" on {ran_on}." if ran_on else "."))]


def retested(name: str, n: int, now: bool) -> Sentence:
    tail = ", on the merged fix." if now else "."
    return f"Retest on {name}:", [_t(f" the {count(n, 'test')} in the plan{tail}")]


def marked_reviewed(title: str, ran_on: str | None, label: str | None) -> Sentence:
    rest = f" “{title}”" + (f" on {ran_on}" if ran_on else "") + (f": {label}." if label else ".")
    return "Marked reviewed:", [_t(rest)]


def asked_to_dig(title: str, ran_on: str | None) -> Sentence:
    return "Asked to dig deeper:", [
        _t(f" “{title}”" + (f" on {ran_on}" if ran_on else "") + ". The request is kept; no answer is made up for it.")
    ]


def code_connected(repository: str, branch: str, title: str | None) -> Sentence:
    rest = [_t(" the app's own copy of the repository "), _m(repository), _t(", branch "), _m(branch), _t(".")]
    if title:
        rest.append(_t(f" The change: {title}."))
    return "Connected the demo code:", rest


def proof_ran(name: str, n: int) -> Sentence:
    return f"Proof on {name}:", [_t(f" the {count(n, 'locked test')} of the plan, rerun on the changed code.")]


def pull_request_opened(number: int, title: str, names: list[str]) -> Sentence:
    return f"Opened pull request #{number}", [_t(f" for {title}. Reviewers: {reviewers(names)}.")]


def approved(number: int) -> Sentence:
    return f"Approved pull request #{number}.", []


def merged(number: int, branch: str, commit: str) -> Sentence:
    return f"Merged pull request #{number}", [_t(" into "), _m(branch), _t(", commit "), _m(short(commit, 7)), _t(".")]


OTTO_DECISIONS = {"accept": "Accepted", "reject": "Not added", "undo": "Undone", "reconsider": "Reconsidered"}
OTTO_PROPOSAL = "Otto's proposal"
OTTO_WHAT = {
    "check": "Otto's proposed check",
    "fix": "Otto's proposed fix",
    "plan": "Otto's proposed change to the plan",
    "dependency": "Otto's proposed dependency update",
}


def otto_on(kind: str, title: str, decision: str, reason: str | None) -> str:
    """What one of Otto's proposals a decision was on, in one line."""
    said = f"{OTTO_WHAT.get(kind, OTTO_PROPOSAL)}: {title}"
    if decision == "reject":
        said += f". Reason: {reason}" if reason else ". No reason given"
    if decision == "undo":
        said += ". The accept was taken back"
    if decision == "reconsider":
        said += ". It is open for a decision again"
    return said


def otto_decided(kind: str, title: str, decision: str, reason: str | None) -> Sentence:
    return OTTO_DECISIONS[decision], [_t(" " + otto_on(kind, title, decision, reason) + ".")]


def looked(libraries: int, found: int, source: str) -> Sentence:
    where = "recorded answers on this computer" if source == "recorded" else "the public advisory source"
    return "Looked for new advisories:", [
        _t(
            f" {count(libraries, 'library', 'libraries')} asked about, by package name only, of {where}; "
            f"{count(found, 'advisory', 'advisories')} came back. A look proposes nothing."
        )
    ]


def research_ran(advisories: int, ended: str | None, pack: str | None) -> Sentence:
    rest = f" {count(advisories, 'advisory', 'advisories')}."
    if ended is None:
        rest += " The run has not finished."
    elif pack:
        rest += f" It made test pack {pack}; its checks are proposals, each decided by a person."
    else:
        rest += " It made no test pack."
    return "Design and prove tests:", [_t(rest)]


def change_tried(title: str) -> Sentence:
    return "Try on a test copy:", [_t(f" {title}. Nothing real was changed.")]


def approval_asked(title: str, names: list[str]) -> Sentence:
    return "Asked for approval", [_t(f" of the change: {title}. Reviewers: {reviewers(names)}.")]


def change_approved(title: str) -> Sentence:
    return "Approved the change:", [_t(f" {title}.")]


def applied(title: str, address: str, accepted: bool) -> Sentence:
    rest = [_t(f" {title}, on "), _m(address), _t(".")]
    if not accepted:
        rest.append(_t(" The server did not take the settings, so nothing changed."))
    return "Applied:", rest


def rolled_back(title: str, address: str, accepted: bool) -> Sentence:
    rest = [_t(f" {title}, on "), _m(address), _t(": the settings from before were put back.")]
    if not accepted:
        rest = [_t(f" {title}, on "), _m(address), _t(". The server did not take the earlier settings.")]
    return "Rolled back:", rest


def option_chosen(option: str, system: str, reason: str | None, review_date: str | None) -> Sentence:
    rest = f" for {system}."
    if review_date:
        rest += f" Review date: {review_date}."
    if reason:
        rest += f" Reason: {reason}"
    return f"Chose {option}", [_t(rest)]


def setting_changed(system: str, field: str, value: str) -> Sentence:
    return "Changed a system setting:", [_t(f" {system}: {field.rstrip('?')} is now {value}.")]


def dependency_list_added(filename: str, components: int, kind: str) -> Sentence:
    return "Dependency list added:", [
        _t(" "),
        _m(filename),
        _t(f" ({kind}), {count(components, 'component')} listed. Nothing in it is run."),
    ]


def library_tied(top: str, system: str | None) -> Sentence:
    return "Tied a library:", [
        _t(f" {top} is part of {system}." if system else f" {top} is part of none of these systems.")
    ]


def developer_change(title: str, branch: str, commit: str) -> Sentence:
    return "A developer's change came in:", [
        _t(f" {title}, on "),
        _m(branch),
        _t(", commit "),
        _m(short(commit, 7)),
        _t("."),
    ]


def picked_tests_ran(n: int, branch: str, commit: str) -> Sentence:
    return "Run the picked tests:", [
        _t(f" {count(n, 'test')} picked for the change on "),
        _m(branch),
        _t(", commit "),
        _m(short(commit, 7)),
        _t(". These runs never replace a result of the test plan."),
    ]


WATCH_MARKS = {"stop": "Stopped watching", "watch": "Watching again"}


def watch_marked(kind: str, item: str, reason: str | None) -> Sentence:
    return WATCH_MARKS.get(kind, "Watching again"), [_t(f" {item}." + (f" Reason: {reason}" if reason else ""))]


# ---------------------------------------------------------------- the words of a decision (Approvals and decisions)

DECISIONS = {
    "approved": "Approved",
    "merged": "Merged",
    "accept": "Accepted",
    "reject": "Not added",
    "undo": "Undone",
    "reconsider": "Reconsidered",
    "applied": "Applied",
    "rolled_back": "Rolled back",
    "marked_reviewed": "Marked reviewed",
    "confirmed": "Confirmed “I own this system”",
    "unconfirmed": "Took back “I own this system”",
    "chose": "Chose an option",
    "setting": "Changed a system setting",
    "tied": "Tied a library",
    "stop": "Stopped watching",
    "watch": "Watching again",
    "signed_off": "Signed off",
}
# Which of them are approvals (the second count on top), and which are decisions on Otto's proposals (the third).
APPROVALS = ("approved",)
OTTO_DECIDED = ("accept", "reject", "undo", "reconsider")
RESULTS_ARE_NOT_HERE = (
    "Results are not in this list: no person decides one. Each result is the separate reviewer's (for a claim on "
    "Verify, fixed rules), and Results shows them."
)


def decision_cards(total: int, approvals: int, otto: dict, signoff: dict | None) -> list[dict]:
    """The four counts on top of Approvals and decisions."""
    decided = sum(otto.values())
    otto_small = (
        ", ".join(f"{n} {OTTO_DECISIONS[k].lower()}" for k, n in otto.items() if n) if decided else "none decided yet"
    )
    return [
        {"key": "decisions", "title": "Decisions", "value": str(total), "small": "by people, in this assessment"},
        {"key": "approvals", "title": "Approvals", "value": str(approvals), "small": "of a pull request or a change"},
        {"key": "otto", "title": "Otto's proposals decided", "value": str(decided), "small": otto_small},
        {
            "key": "signoff",
            "title": "Sign-off",
            "value": signoff["by"] if signoff else "Not yet",
            "small": "who closed this assessment" if signoff else "Close assessment records who and when",
        },
    ]


# ---------------------------------------------------------------- the story of one entry (its side panel)

RESTED_ON = "What it rested on"
CAME_AFTER = "What came after"
TECHNICAL_RECORD = "Technical record"
ROLES = {
    "pressed": "Pressed by",
    "started": "Started by",
    "merged": "Merged by",
    "approved": "Approved by",
    "approved_as": "Approved as",
    "opened": "Opened by",
    "connected": "Connected by",
    "applied": "Applied by",
    "rolled_back": "Rolled back by",
    "asked": "Asked by",
    "tried": "Tried by",
    "decided": "Decided by",
    "signed_off": "Signed off by",
    "downloaded": "Downloaded by",
    "brought_in": "Brought in by",
    "author": "Written by",
    "looked": "Looked by",
    "chose": "Chosen by",
    "changed": "Changed by",
    "marked": "Marked by",
    "ticked": "Ticked by",
}


def role(key: str, person: dict, at: str | None = None, note: str | None = None) -> dict:
    """One line of a story's Who: "Merged by You"."""
    return {"role": ROLES[key], "who": person, "at": at, "note": note}


MERGE_NOTE = "after the box “Merge pull request?” was confirmed"
ONE_LOGIN_NOTE = "One login records every approval, under the name shown."
PROPOSAL_NO_TIME = (
    "worked out from the results each time it is shown · a proposal is not stored, so it has no time of its own; "
    "the first record is a person's decision on it"
)
PROPOSED_BY_OTTO = "Proposed by Otto"
LOCKED = "Test details locked"


def locked_line(fingerprint: str | None) -> str:
    return (
        "before its first run on this computer · a locked test is shared by every assessment that runs it · they can't "
        "change after this" + (f" · fingerprint {short(fingerprint)}" if fingerprint else "")
    )


HISTORY_TITLES = {
    "test": "History of this check",
    "check": "History of this check",
    "claim": "History of this claim",
    "fix": "History of this fix",
    "change": "History of this change",
    "system": "History of this system",
    "advisory": "History of this advisory",
    "library": "History of this library",
}
FIX_MERGED = "The fix it answers was merged"


def run_title(phase: str, origin: str, ran_on: str | None) -> str:
    """One run in an item's history: what kind of run it was, and what it ran on."""
    what = {
        "after_apply": "Measured right after Apply",
        "after_rollback": "Measured right after Roll back",
    }.get(origin) or {
        "first": "First run",
        "retest": "Retest",
        "proof": "Proof run",
        "migration": "Measure status",
        "dependencies": "Measured on a public copy",
        "verify": "Verify",
        "watch": "Run for a developer's change",
        "watch_base": "Run on the code before a developer's change",
    }.get(phase, "Run")
    return f"{what} on {ran_on}" if ran_on else what


PROOF_IS_ITS_OWN = (
    "The proof's run of this test, on the changed code, is a check of its own, under Fix proofs on Checks."
)
WATCH_IS_ITS_OWN = (
    "A run made for a developer's change is a check of its own, under Change watch, and is never this test's result."
)
NO_HISTORY = "Nothing has happened to this yet."
UNKNOWN_ITEM = "That item is not in this assessment."

# What a proof, a try and the measurement after a change said, in the words their own pages use.
PROOF_WORDS = {
    "passed": ("Proof passed", "pass"),
    "failed": ("Proof did not pass", "fail"),
    "untrusted": ("Proof can't be trusted", "warn"),
    "unfinished": ("Proof did not finish", "warn"),
    "running": ("Proving", "neutral"),
}
TRY_WORDS = {
    "passed": ("Try passed", "pass"),
    "failed": ("Try did not pass", "fail"),
    "running": ("Try running", "neutral"),
    "couldnt_run": ("No answer from the try", "warn"),
    "not_run": ("No answer from the try", "warn"),
}


def badge(words: tuple[str, str] | None) -> dict | None:
    return {"label": words[0], "tone": words[1]} if words else None


def rested(title: str, text: str | None, chips: list[dict], link: dict | None, link_label: str | None) -> dict:
    """One line of "What it rested on" or "What came after": a title, result words as their pages gave them, a sentence."""
    return {"title": title, "text": text, "chips": chips, "link": link, "link_label": link_label}


def fact(label: str, value: object, mono: bool = True) -> dict:
    return {"label": label, "value": str(value), "mono": mono}


def chip(label: str, tone: str, name: str | None = None) -> dict:
    """A result word as its own page gave it, with the name of what it is a result of where several stand together."""
    return {"name": name, "label": label, "tone": tone}


def findings_title(n: int) -> str:
    return f"The {count(n, 'failed result')} it answers"


FINDINGS_TEXT = "The results this fix came from. Each decided by the separate reviewer."
PROOF_RESTED = "Every locked test of the plan was rerun on the changed code before the pull request could be opened."
RETEST_AFTER = "The plan's tests, run again after the merge. Each decided by the separate reviewer."
TRY_RESTED = "The change was tried on a test copy first. Nothing real was changed by the try."
MEASURED_AFTER = (
    "The system itself was measured again right after, with handshakes only. Decided by the separate reviewer."
)
NOT_MEASURED_AFTER = "No measurement of the system right after it is on record."
OPEN_THE_PROOF = "Open the proof"
OPEN_IN_RESULTS = "Open in Results"
OPEN_THE_CHANGE = "Open the change"
APPROVALS_TITLE = "Approvals"
AFTER_APPLY = "Measured right after Apply"
AFTER_ROLLBACK = "Measured right after Roll back"


def approvals_text(names: list[str], asked: list[str]) -> str:
    if not names:
        return f"Nobody had approved it. Asked: {reviewers(asked)}."
    return f"Approved by {reviewers(names)}. {ONE_LOGIN_NOTE}"


def open_in(area: str) -> str:
    return f"Open in {AREA_LABELS.get(area, 'its page')}"


# ---------------------------------------------------------------- Evidence files

HOW_TO_CHECK_TITLE = "How to check a file"
HOW_TO_CHECK = (
    "The verify command reads the JSON file as data and checks that nothing in it was changed after it was signed, "
    "and that it was signed with this app's own key. Exit code 0 only if both hold; 2 means the file is consistent but "
    "the signer could not be confirmed, which is not a pass."
)
WHAT_IT_HOLDS_TITLE = "What the file holds"
WHAT_IT_HOLDS = (
    "The imported claims and every Verify run.",
    "Every check of every kind with every run of it: the locked test, the run record, its fingerprint and the "
    "reviewer's review.",
    "Every fix: the change, each proof, the pull request, the approvals and the merge.",
    "The migration plan, every change to a system (each try, approval, Apply and Roll back) and the dependency list.",
    "Otto's part, where the assessment has one: the test packs, the ledger and every decision on a proposal.",
    "Change watch, kept apart: each developer's change and every watch run.",
    "Who did what: each recorded press with who, when, which button and the runs and records it started.",
    "The organization, project and assessment it belongs to, and the sign-off once it is closed.",
)
REPORT_NOTE = "The report is a readable copy of the same file. It is not signed."


# ---------------------------------------------------------------- the signed evidence file's part and the report's section

EVIDENCE_NOTE = (
    "Who did what: one entry for each recorded press of a button that decides or changes something in this assessment, "
    "with the name it was made under, the time of the press and what it started or made. A name is the account that "
    "was logged in where the app has one, otherwise the name typed once in Settings (Who decides), or “You”; the app "
    "does not check who is at the keyboard beyond its login. Nothing here decides a result: every result is the "
    "separate reviewer's. What happened before names were kept has no entry, and nothing was filled in afterwards. "
    "Decisions on Otto's proposals, looks and research runs keep their own names in the Otto part; approvals and the "
    "sign-off keep theirs where they are."
)
REPORT_TITLE = "Who did what"
REPORT_EMPTY = "No press was recorded for this assessment: everything in this file was done before names were kept."
ACTION_WORDS = {
    "assessment_started": "Started the assessment",
    "assessment_rerun": "Started the assessment as a rerun",
    "assessment_changed": "Changed the assessment's details",
    "closed": "Closed and signed off",
    "file_imported": "Brought the scanner file in",
    "dependency_list_added": "Added a dependency list",
    "evidence_downloaded": "Downloaded the evidence file",
    "address_confirmed": "Ticked “I own this system”",
    "address_unconfirmed": "Took back “I own this system”",
    "verify": "Verified the claims",
    "run": "Ran one test",
    "run_all": "Ran every test in the plan",
    "test_added": "Added a test to the plan",
    "test_removed": "Removed a test from the plan",
    "tests_reordered": "Changed the order of the test plan",
    "retest": "Retested on another version",
    "retest_now": "Retested on the merged fix",
    "measure_status": "Measured the post-quantum status",
    "measure_dependencies": "Measured on a public copy",
    "marked_reviewed": "Marked a result reviewed",
    "dig_deeper": "Asked to dig deeper",
    "code_connected": "Connected the demo code",
    "proof_started": "Ran the proof again",
    "pull_request_opened": "Opened a pull request",
    "approved": "Approved a pull request",
    "merged": "Merged a pull request",
    "change_tried": "Tried a change on a test copy",
    "approval_asked": "Asked for approval of a change",
    "change_approved": "Approved a change",
    "applied": "Applied a change",
    "rolled_back": "Rolled a change back",
    "option_chosen": "Chose a migration option",
    "setting_changed": "Changed a system setting",
    "library_tied": "Tied a library to a system",
    "demo_change_brought_in": "Brought in a demo change",
    "picked_tests_run": "Ran the tests picked for a change",
}


def action_words(kind: str) -> str:
    return ACTION_WORDS.get(kind, kind.replace("_", " "))


__all__ = [
    "AREAS",
    "AREA_KEYS",
    "AREA_LABELS",
    "AREA_PAGES",
    "BY_REVIEWER",
    "BY_RULES",
    "DECISIONS",
    "KINDS",
    "KIND_KEYS",
    "KIND_LABELS",
    "NAMES_NOTE",
    "NOT_RECORDED",
    "action_words",
    "button",
    "who",
]
