"""Words for Otto's screens (phase 5c): the Advisories page of an assessment, and the Test packs and Live Otto
sections of Settings.

Nothing here decides anything. A result shown on Advisories is the reviewer's, as Evidence Lab already words it (its
label and its one plain sentence are passed in and repeated). An advisory's own line is shown as its publisher's.
Otto's ledger entries are listed as what they are (a lock, a bound run); the ledger's own verdict is never shown as
a result. A trial on public copies is described by its counts, never by a word of praise.
"""
from __future__ import annotations

from datetime import datetime

from app.otto import designs, model
from app.present import advisory as present_advisory
from app.present.results import DISCLAIMER

TEST_LABELS = {"ready": ("Test ready", "pass"), "not_offered": ("Not offered", "warn"), "none": ("No test yet", "neutral")}
FIX_LABEL = "From Otto"
# A quote is not always from the advisory page itself: where the advisory does not put the weakness into words, the
# reading quotes the publisher's own source file. The caption beside each quote names where it was read.
PUBLISHER_TAG = "quoted from the named source, not a result"
NOT_INSTALLED_TAIL = " Advisory checks can't be added or run, because their runs could not be recorded. Everything else works as before."
# What kind of entry a ledger line is, in plain words. Otto's own record names stay in the ledger: one of them is
# "verdict", which is a check of a record and must never read as the result of a test.
LEDGER_WORDS = {"question": "Asked", "objective": "Opened", "claim": "Recorded", "verdict": "Record checked", "hypothesis": "Registered",
                "run": "Trial run", "decision": "Judged", "audit": "Replayed", "fact": "Noted", "correction": "Note"}


def _entries(ledger: list[dict]) -> list[dict]:
    return [{"seq": e["seq"], "kind": LEDGER_WORDS.get(str(e["kind"]), "Entry"), "id": e["id"][7:19], "at": e["at"], "what": e["what"]}
            for e in ledger]
STEP_WORDS = {"read_advisory": "Read the advisory", "design_test": "Design a test", "propose_fix": "Propose the fix",
              "write_fix": "Write a change for your own code"}
# What a reading recorded about the weakness, in plain words (a reading's notes can refer to "the kind").
KIND_WORDS = {"accepts_bad_signature": "accepts a signature it must reject", "rejects_good_signature": "rejects a signature it must accept",
              "stops_with_error": "stops with an error"}
AREA_WORDS = {"ecdsa_signature_check": "when checking ECDSA signatures", "eddsa_signature_check": "when checking EdDSA signatures"}
SENT_LINE = ("What is sent to Claude when this is on: the advisory text and, for a fix to your own code, the source file of the failing "
             "program and the cases it got wrong. Nothing else leaves this computer.")


def day(stamp: str | None) -> str:
    """A date as the screens show it: 17 November 2026."""
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return str(stamp or "")
    return f"{when.day} {when.strftime('%B %Y')}"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


def _count(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {_plural(n, one, many)}"


# ---------------------------------------------------------------- Settings: Test packs, the status lines, Live Otto

def pack_card(pack, installed_at: str | None = None) -> dict:
    advisories, tests = len(pack.pack["advisories"]), len(pack.pack["tests"])
    return {"version": pack.version, "built_at": pack.pack["built_at"], "built": day(pack.pack["built_at"]),
            "signer": pack.signer, "made_here": pack.made_here, "advisories": advisories, "tests": tests,
            "line": (f"Pack {pack.version}, built {day(pack.pack['built_at'])}: {_count(advisories, 'advisory', 'advisories')}, {_count(tests, 'test')}."
                     + (" Made on this computer." if pack.made_here else "")),
            "fingerprint": pack.fingerprint, "installed_at": installed_at}


def pack_adds(pack) -> list[str]:
    """What a pack adds, one plain line per advisory, for the Install update box."""
    lines = []
    for advisory in pack.pack["advisories"]:
        name = (advisory["reading"] or {}).get("plain_name") or "An advisory Otto could not read"
        label = TEST_LABELS[advisory["test"]["state"]][0]
        lines.append(f"{name} ({advisory['id']}): {label}")
    return lines


def settings_view(*, installed: list, update, refused: list[dict], scan_line: str | None, harness_status: dict, live_on: bool,
                  limit_nano: int, key_present: bool, answers_line: str, unreadable: list[str] | None = None) -> dict:
    cards = [pack_card(pack, at) for at, pack in installed]
    unreadable = list(unreadable or [])
    newest = cards[-1] if cards else None
    box = None
    if update is not None:
        adds = pack_adds(update)
        box = {"version": update.version, "button": "Install update",
               "line": f"Test pack {update.version} is in the updates folder.",
               "dialog": {"title": f"Install test pack {update.version}?",
                          "lines": [pack_card(update)["line"], f"Signed by: {update.signer}.",
                                    "It adds:"] + adds +
                                   ["Nothing in a pack runs. Installing adds no check to any assessment: Otto proposes its checks on the Advisories page, and you accept or reject each one.",
                                    "Packs install in order and are never removed."],
                          "confirm": "Install", "cancel": "Cancel"}}
    live_ready = live_on and key_present
    if not key_present:
        status = ("Live Otto is off: no API key is set on this computer. Otto works on the answers recorded during the build."
                  if not live_on else
                  "Live Otto is switched on, but no API key is set on this computer, so Otto works on the answers recorded during the build.")
    elif live_on:
        status = "Live Otto is on: when Otto needs an answer, it asks Claude through your key, within the spending limit."
    else:
        status = "Live Otto is off: Otto works on the answers recorded during the build."
    return {
        "packs": {
            "title": "Test packs",
            "intro": ("A test pack is a signed update, like an antivirus update: published advisories, a test for each one that has one, a "
                      "proposed fix, and how each did when it was tried on public copies. Nothing in a pack runs."),
            "installed": cards,
            "installed_line": (f"Installed: pack {newest['version']}, built {newest['built']}, signed by {newest['signer']}." if newest
                               else "No test pack is installed yet." if not unreadable
                               else "No installed test pack can be read by this version of the app."),
            # A pack that was installed by an earlier build of the app, in a form that has changed since. It is said
            # plainly, never passed over: packs install in order, so nothing can be installed after it here.
            "unreadable_line": ((f"Test pack {', '.join(unreadable)}, installed here earlier, can't be read by this version of the app: "
                                 "it was made by an earlier build. Its advisories are not shown, and no other pack can be installed "
                                 "in this data folder. To start afresh, stop the app, move the data folder away and start the app "
                                 "again.") if unreadable else None),
            "counts_line": (f"{_count(sum(c['advisories'] for c in cards), 'advisory', 'advisories')} and "
                            f"{_count(sum(c['tests'] for c in cards), 'test')} in {_count(len(cards), 'installed pack')}." if cards else None),
            "check": {"button": "Check for updates",
                      "note": "It looks in the updates folder on this computer, never on the internet."},
            "checked_line": scan_line, "refused": [{"file": r["file"], "reason": r["reason"]} for r in refused],
            "update": box,
            "order_note": "Packs install in order and are never removed.",
        },
        "harness": {"installed": bool(harness_status["installed"]),
                    "line": harness_status["sentence"] + ("" if harness_status["installed"] else NOT_INSTALLED_TAIL)},
        "answers": {"line": answers_line, "live": live_ready},
        "live": {
            "title": "Live Otto",
            "key_present": key_present,
            "key_line": ("An API key is set on this computer." if key_present else
                         f"No API key is set on this computer. Live Otto reads it from the {model.KEY_ENV} environment variable; "
                         "the key is never shown, stored or sent anywhere but to Claude."),
            "switch": {"label": "Use live Claude", "on": live_on, "can_turn_on": key_present,
                       "blocked_reason": None if key_present else "This can be turned on only when an API key is present."},
            "limit": {"label": "Spending limit per run (US dollars)", "value": f"{limit_nano / model.NANO:.2f}", "save": "Save",
                      "note": ("A run is one fix request in the app, or one research command. Otto adds up each call's cost from the tokens the "
                               "API reports, and does not send a request that could pass the limit.")},
            "sent_line": SENT_LINE,
            "status_line": status,
            "price_line": (f"Prices used to add up the cost: {model.PRICE_SOURCE['title']}, as of {day(model.PRICE_SOURCE['as_of'])}. "
                           "A price list can go out of date."),
        },
    }


# ---------------------------------------------------------------- a library fix's two proof rows (the same words everywhere)

PUBLIC_LABEL, HERE_LABEL = "Proven on public copies", "Proven on your system"
NOT_YET_TEXT = "Update the library, then press Retest."
# What stands behind the second row, said plainly wherever the row is shown in full: a retest reruns the locked tests
# on a public copy of the updated version. The app has no connector to the system a customer runs (a later phase).
HERE_NOTE = ("A retest here reruns the same locked tests on a public copy of the updated version, on this computer. In this version the "
             "app does not connect to the system you run.")


def stamp(value: str | None) -> str:
    """A time as the screens show it in a sentence: 18 November 2026, 10:02 UTC."""
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value or "")
    return f"{when.day} {when.strftime('%B %Y')}, {when.strftime('%H:%M')} UTC"


def _row(key: str, label: str, word: str, tone: str, text: str, links: list[dict] | None = None, ledger: dict | None = None,
         note: str | None = None) -> dict:
    return {"key": key, "label": label, "badge": {"label": word, "tone": tone}, "text": text, "line": f"{label}: {word}. {text}",
            "links": list(links or []), "ledger": ledger, "note": note}


def public_copies_row(fix: dict, advisory: dict | None) -> dict:
    """The first proof row of a library's fix: how the update did when Otto tried it on public copies, before the pack
    was signed. It repeats the pack's own counts; "Passed" here is the pack's "proven" (the advisory check passed on
    the fixed version and every other locked test passed there too). `advisory`: the pack's entry, for the research
    ledger's entries (None where only the fix is at hand)."""
    arms = (fix.get("trial") or {}).get("arms") or {}
    affected, fixed = str((arms.get("affected") or {}).get("version") or "the affected version"), str(fix.get("version"))
    failing = int((arms.get("fixed") or {}).get("failing") or 0)
    check_wrong = ((((advisory or {}).get("test") or {}).get("trial") or {}).get("arms") or {}).get("fixed", {}).get("wrong")
    ledger = None
    if advisory is not None and advisory.get("ledger"):
        ledger = {"title": "Otto ledger entries", "count": len(advisory["ledger"]), "entries": _entries(advisory["ledger"]),
                  "note": ("From Otto's research ledger, a hash chain kept with the Otto harness: the test and the fix were registered, "
                           "tried and judged before the pack was signed.")}
    links = [{"label": "See the trial on Advisories", "link": {"page": "advisories", "item": str(advisory["id"])}}] if advisory is not None else []
    if fix.get("state") == "proven":
        return _row("public", PUBLIC_LABEL, "Passed", "pass", f"{affected} fails the advisory check; {fixed} passes.", links, ledger)
    if check_wrong in (0, None) and failing >= 1:
        more = "another locked test still fails" if failing == 1 else f"{failing} other locked tests still fail"
        return _row("public", PUBLIC_LABEL, "Not proven", "warn",
                    f"{affected} fails the advisory check and {fixed} passes it, but {more} on {fixed}.", links, ledger)
    # anything else: the pack's own sentence, never one of this app's that the pack might not bear out
    return _row("public", PUBLIC_LABEL, "Not proven", "warn", str(fix.get("reason") or "The pack does not say why."), links, ledger)


def your_system_row(fix: dict, here: dict | None) -> dict:
    """The second proof row: what this assessment's own retest on the updated version shows. It repeats the
    reviewer's results; "Passed" needs the advisory check and every other pass-or-fail test of that library to have
    passed in the same retest, the rule the first row is held to."""
    here = here or {"state": "not_yet"}
    name = f"{fix.get('library')} {fix.get('version')}"
    if here.get("state") == "not_yet":
        return _row("here", HERE_LABEL, "Not yet", "neutral", NOT_YET_TEXT, note=HERE_NOTE)
    links = [{"label": "See the retest's result", "link": {"page": "evidence", "item": f"test-{here.get('item_id')}"}}]
    when = stamp(here.get("finished_at"))
    if here.get("state") == "passed":
        return _row("here", HERE_LABEL, "Passed", "pass",
                    f"On {when} the retest on {name} passed: the advisory check and every other locked pass-or-fail test.", links, note=HERE_NOTE)
    if (here.get("check") or {}).get("code") == "passed":
        failing = int(here.get("failing") or 0)
        more = "another locked test still fails" if failing == 1 else f"{failing} other locked tests still fail"
        return _row("here", HERE_LABEL, "Not proven", "warn",
                    f"On {when} the retest on {name} ran: the advisory check passed, but {more} on {fix.get('version')}.", links, note=HERE_NOTE)
    return _row("here", HERE_LABEL, "Not proven", "warn",
                f"On {when} the retest on {name} ran, and the advisory check did not pass ({(here.get('check') or {}).get('label')}).", links,
                note=HERE_NOTE)


# ---------------------------------------------------------------- Otto's proposals: a person decides

PROPOSAL_LABEL = "From Otto"
ONE_LOGIN = "This version has one login and no separate accounts. Whoever is at the keyboard records each decision, under the name shown."
ACCEPTED_WORDS = {"check": "Added", "fix": "Accepted", "plan": "Accepted", "dependency": "Accepted"}
DECISION_WORDS = {"accept": "Accepted", "reject": "Rejected", "undo": "Accept undone", "reconsider": "Taken up again"}
KIND_WORDS_PROPOSAL = {"check": "check", "fix": "fix", "plan": "plan change", "dependency": "dependency update"}
ACCEPT_NOTES = {
    "check": "Accept adds this check to the test plan, exactly as “+ Add test” would. It runs nothing.",
    "fix": "Accept records your decision. It runs nothing and changes nothing on any system.",
    "plan": "Accept adds this to the migration plan as something to fix first. It runs nothing and changes nothing on any system.",
    "dependency": "Accept marks this library “update first”. It runs nothing and changes nothing on any system.",
}
UNDO_NOTES = {
    "check": "Undo takes it out of the test plan again, until it has run.",
    "fix": "Undo is possible until the fix has run or been applied.",
    "plan": "Undo takes it off the plan again.",
    "dependency": "Undo takes the mark off again.",
}


def not_added(reason: str | None) -> str:
    return f"Not added ({reason})" if reason else "Not added (no reason given)"


def proposal_view(p: dict, ledger: list[dict] | None = None) -> dict:
    """One of Otto's proposals as a screen shows it: what Otto proposes and why, where it stands, who decided and
    when, and the buttons. It words no result. `p` comes from ProposalsMixin; `ledger`: the entries of its decisions."""
    state, kind, decisions = p["state"], p["kind"], p["decisions"]
    last = decisions[-1] if decisions else None
    if state == "accepted":
        word, tone = ACCEPTED_WORDS[kind], "pass"
        decided = (f"{DECISION_WORDS['accept']} by {last['by']} on {stamp(last['at'])}." if last
                   else "Added before decisions were recorded.")
    elif state == "rejected":
        word, tone = not_added(last["reason"] if last else None), "neutral"
        decided = ((f"{DECISION_WORDS['reject']} by {last['by']} on {stamp(last['at'])}."
                    + (f" Reason: {last['reason']}" if last.get("reason") else " No reason was given.")) if last else "")
    else:
        word, tone = "Proposed", "warn"
        decided = (f"{DECISION_WORDS[last['decision']]} by {last['by']} on {stamp(last['at'])}. It is open for a decision again."
                   if last else "Nobody has decided this yet.")
    labels = {"accept": "Accept", "reject": "Reject", "undo": "Undo", "reconsider": "Reconsider"}
    buttons = [{"key": key, "label": labels[key], "can": p["actions"][key] is None, "blocked_reason": p["actions"][key]}
               for key in ("accept", "reject", "undo", "reconsider") if key in p["actions"]]
    notes = []
    if "accept" in p["actions"]:
        notes.append(ACCEPT_NOTES[kind])
    if "undo" in p["actions"] and p["actions"]["undo"] is None:
        notes.append(UNDO_NOTES[kind])
    if not p.get("current", True):
        notes.append("Otto no longer proposes this here: what it was about has changed since. It stays on the record.")
    history = [{"number": d["number"], "word": DECISION_WORDS[d["decision"]], "by": d["by"], "at": d["at"], "at_text": stamp(d["at"]),
                "reason": d.get("reason"), "ledger_entry": (d.get("ledger_entry") or "")[7:19] or None,
                "line": (f"{d['number']}. {DECISION_WORDS[d['decision']]} by {d['by']} on {stamp(d['at'])}"
                         + (f": {d['reason']}" if d.get("reason") else "") + ".")}
               for d in decisions]
    return {"id": p["id"], "kind": kind, "kind_label": KIND_WORDS_PROPOSAL[kind], "label": PROPOSAL_LABEL, "title": p["title"], "why": p["why"],
            "why_label": "Why it applies" if kind == "check" else "Why Otto proposes it", "lines": p["lines"],
            "status": {"key": state, "word": word, "tone": tone}, "decided_line": decided, "effect": _effect(p),
            "buttons": buttons, "note": " ".join(notes) or None,
            "reject_dialog": ({"title": "Reject this proposal?", "line": "It is not deleted: it stays on the record as “Not added”, "
                                                                             "with your reason, and can be taken up again later.",
                               "reason_label": "Reason (optional, one short line)", "max": 300, "confirm": "Reject", "cancel": "Cancel"}
                              if "reject" in p["actions"] else None),
            "history": {"title": "Decisions on this proposal", "count": len(history), "rows": history, "footnote": ONE_LOGIN,
                        "ledger": ({"title": "Otto ledger entries for these decisions", "count": len(ledger), "entries": _entries(ledger),
                                    "note": ("Each decision is written to this assessment's Otto ledger with who and when. The ledger "
                                             "holds no result.")} if ledger else None)},
            "link": p["link"], "proposed_at": p.get("proposed_at")}


def result_block(*, advisory_id: str, plain_name: str | None, pack_version: str, design_sha256: str, trial: list[str],
                 ledger: list[dict], proposal: dict | None) -> dict:
    """Evidence, on a result of an advisory check: what stands behind the check. Which advisory and which signed pack
    it came from, the test's design by its fingerprint, how the test did when it was tried on public copies, every
    decision on Otto's proposal with who and when, and the Otto ledger entries of the check and of those decisions.
    It repeats records. It words no result: the result is the test's, above it on the same panel.
    `proposal`: its `proposal_view` (None when the installed packs no longer hold this check's proposal)."""
    history = (proposal or {}).get("history") or {}
    rows = list(history.get("rows") or [])
    decided = (proposal or {}).get("decided_line") or "Added before decisions were recorded."
    name = f"{plain_name} ({advisory_id})" if plain_name else advisory_id
    return {"label": PROPOSAL_LABEL, "title": "Where this check came from",
            "line": f"Otto proposed this check from the advisory “{name}”, in test pack {pack_version}. {decided}",
            "advisory": {"label": "Open the advisory", "link": {"page": "advisories", "item": advisory_id}},
            "design": {"title": "The test's design",
                       "lines": [f"Design fingerprint (SHA-256): {design_sha256}",
                                 "Its question, its control that must fail and its pass rule are in the test details, locked before the run."]},
            "trial": {"title": "How the test did when it was tried on public copies", "lines": trial} if trial else None,
            "decisions": {"title": "Decisions on Otto's proposal", "count": len(rows), "rows": rows, "footnote": ONE_LOGIN,
                          "empty": None if rows else "No decision is on record: this check was added before decisions were recorded."},
            "ledger": {"title": "Otto ledger entries for this check and its decisions", "count": len(ledger), "entries": _entries(ledger),
                       "note": ("The lock entry was written before the check could run; each reviewed run and each decision added an "
                                "entry. The ledger holds no result.")},
            "note": "This says where the check came from and who decided to add it. The result comes only from the test."}


def project_block(rows: list[dict], pack: dict | None) -> dict:
    """The Project overview's block about Otto: proposals waiting in each assessment, and what changed since the newest
    test pack. `rows`: {"assessment", "waiting": counts by kind, "since": facts or None, "why"}. Counts only."""
    out = []
    for row in rows:
        a = row["assessment"]
        total = sum(row["waiting"].values())
        since_lines: list[str] = []
        s = row["since"]
        if s is not None:
            b = s["brought"]
            brought = sum(b.values())
            if brought:
                parts = [f"{b['proposed']} waiting" if b["proposed"] else "", f"{b['accepted']} added" if b["accepted"] else "",
                         f"{b['rejected']} not added" if b["rejected"] else ""]
                since_lines.append(f"It brought {_count(brought, 'proposed check')} for this assessment: " + ", ".join(x for x in parts if x) + ".")
            else:
                since_lines.append("It brought no check that fits this assessment's file.")
            if s["decisions"]:
                since_lines.append(f"{_count(s['decisions'], 'decision')} recorded since.")
            if s["results"]:
                tally: dict[str, int] = {}
                for label in s["results"]:
                    tally[label] = tally.get(label, 0) + 1
                since_lines.append("Advisory checks run since: " + ", ".join(f"{n} {label}" for label, n in tally.items()) + ".")
        elif row.get("why"):
            since_lines.append(row["why"])
        out.append({"assessment_id": a.id, "title": a.name or f"Assessment {a.number}", "waiting": total,
                    "waiting_text": (f"{_count(total, 'proposal')} waiting for a decision" if total else "Nothing waiting"),
                    "link": {"page": "overview", "item": None, "group": None, "assessment_id": a.id},
                    "since": since_lines})
    return {"title": "Otto in this project",
            "note": "Otto proposes; a person decides. The counts below repeat what each assessment's own pages say.",
            "pack_line": (f"Newest test pack: {pack['version']}, installed on {stamp(pack['installed_at'])}." if pack
                          else "No test pack is installed yet, so Otto has proposed nothing."),
            "since_title": f"What changed since pack {pack['version']}" if pack else None,
            "rows": out}


def found_line(*, packs: int, ready: int, programs: list[str]) -> dict:
    """Import's line about Otto, after a file is in: how many checks of the installed test packs may apply to it.
    A count and a link; nothing is added or run by bringing a file in."""
    count = ready * len(programs)
    if not packs:
        return {"count": 0, "label": PROPOSAL_LABEL,
                "text": "Otto has nothing to propose for this file yet: no test pack is installed.",
                "note": "Test packs are installed in Settings. Nothing runs on import.",
                "link": {"page": "settings", "item": None, "section": "test-packs"}, "link_label": "Open Settings"}
    if not count:
        why = ("no signing program in this file checks ECDSA P-256 signatures" if not programs
               else "no advisory in the installed test packs has a test yet")
        return {"count": 0, "label": PROPOSAL_LABEL, "text": f"Otto found no check that may apply to this file: {why}.",
                "note": "Nothing runs on import.", "link": {"page": "advisories", "item": None}, "link_label": "Open Advisories"}
    return {"count": count, "label": PROPOSAL_LABEL,
            "text": (f"Otto found {count} {'check' if count == 1 else 'checks'} that may apply: {ready} published "
                     f"{'weakness' if ready == 1 else 'weaknesses'} with a test, for {', '.join(programs)}."),
            "note": "Nothing runs on import. You accept or reject each proposed check on Advisories.",
            "link": {"page": "advisories", "item": None}, "link_label": "Open Advisories"}


def _effect(p: dict) -> str | None:
    """What an accepted proposal has led to so far, in one line (None while it is not accepted). It repeats records; a
    "passed" in it is the reviewer's result, with its date."""
    if p["state"] != "accepted":
        return None
    facts, kind, about = p.get("facts") or {}, p["kind"], p.get("about") or {}
    if kind == "check":
        return "It is in the test plan, on Checks." + ("" if facts.get("runs") else " It has not run yet.")
    if kind == "fix" and facts.get("code"):
        return ("The code is connected: the change is on its branch and takes the proof, review and merge path below." if facts.get("connected")
                else "Next: Connect demo code. The change goes on a branch, and the proof reruns every locked test on it.")
    if kind == "fix":
        return ("A retest has run on the updated version: the two proof rows say what it showed." if facts.get("retested")
                else "Next: whoever owns the software updates it; then press Retest.")
    if kind == "plan":
        done = facts.get("done")
        if done:
            return (f"Done: a newer result of this check passed on {about.get('program', 'the program').split(' ')[0]} "
                    f"{done.get('version') or ''}".rstrip() + (f", on {stamp(done.get('at'))}." if done.get("at") else "."))
        return "On the plan: something to fix first, on the Signatures track."
    return f"Marked “update first”: to {about.get('fixed')}." if about.get("fixed") else "Marked “update first”."


MEASURED_WORDS = {"affected": ("measured affected", "fail"), "not_affected": ("measured not affected", "pass"),
                  "not_checked": ("not yet checked", "neutral")}
NOT_CHECKED_WHY = {
    "no_test": "This advisory has no test yet, so nothing can be measured.",
    "not_in_file": ("No check has run on {lib} here. An advisory check runs on the signing programs your scanner file names, and this "
                    "library is in the dependency list only."),
    "not_added": "Otto proposes a check for it on Advisories. It is not in the test plan.",
    "not_run": "Its check is in the test plan and has not run yet.",
    "couldnt": "Its check could not run, or its run could not be trusted. Checks has the reason.",
}


def named_line(n: dict, fix_link: dict | None) -> dict:
    """One line of a library's row on Dependencies: "Named by advisory X: measured affected", "measured not affected" or
    "not yet checked", with its one plain sentence. "Measured" is only ever this assessment's own reviewed result of
    that advisory's check on the same library and version; everything else reads "not yet checked", with the reason."""
    m = n["measured"]
    word, tone = MEASURED_WORDS[m["state"]]
    lib = f"{n['library']} {n['version']}"
    if m["state"] == "affected":
        detail = f"The advisory check failed on {lib} in this assessment."
    elif m["state"] == "not_affected":
        detail = (f"The advisory check passed on {lib} in this assessment: the published cases chosen for this advisory got the right "
                  "answer.")
    else:
        detail = NOT_CHECKED_WHY[m.get("why") or "not_in_file"].format(lib=lib)
    return {"id": n["advisory"], "name": n["plain_name"], "line": f"Named by advisory {n['advisory']}: {word}",
            "state": {"key": m["state"], "label": word, "tone": tone}, "detail": detail,
            "fixed_line": f"Its publisher names {n['fixed']} as the fixed version; your list has {n['version']}.",
            "advisory_link": {"page": "advisories", "item": n["advisory"]},
            "evidence_link": {"page": "evidence", "item": f"test-{m['item_id']}"} if m.get("run_id") else None,
            "fix_link": fix_link, "fix_label": "See the proposed fix" if fix_link else None}


def dependency_status(views: list[dict]) -> dict | None:
    """The status a library carries once a person accepted Otto's proposal for it."""
    accepted = [v for v in views if v["status"]["key"] == "accepted"]
    if not accepted:
        return None
    return {"label": "Update first", "tone": "warn", "lines": [v["effect"] + " " + (v["decided_line"] or "") for v in accepted]}


def plan_block(views: list[dict]) -> dict | None:
    """A system's block of Otto's proposed plan changes on Migration: each with Accept and Reject. An accepted one is
    listed as something to fix first; it changes no status, no recommendation and no measured fact."""
    if not views:
        return None
    return {"title": "From Otto: proposed changes to this system's plan",
            "note": ("Otto proposes these from results. Accept adds one to the plan as something to fix first; Reject keeps the plan as "
                     "it was, with your reason. Neither changes a status or a measurement."),
            "proposals": views}


def roadmap_mark(views: list[dict]) -> dict | None:
    """The mark on a roadmap row whose system has a proposal of Otto's: a count of those waiting, or what was accepted."""
    if not views:
        return None
    waiting = len([v for v in views if v["status"]["key"] == "proposed"])
    accepted = [v for v in views if v["status"]["key"] == "accepted"]
    if waiting:
        text = f"{_count(waiting, 'proposal')} waiting for your decision"
    elif accepted:
        text = accepted[0]["effect"] or "Accepted"
    else:
        text = views[0]["status"]["word"]
    return {"label": PROPOSAL_LABEL, "text": text, "tone": "warn" if waiting else "neutral", "waiting": waiting}


def waiting_view(counts: dict[str, int]) -> dict:
    """The Overview's "Waiting for you" line: how many of Otto's proposals nobody has decided yet, each kind linking to
    the page it lives on. It counts; it decides nothing."""
    words = {"check": ("proposed check", "proposed checks", "advisories", "Advisories"),
             "fix": ("proposed fix", "proposed fixes", "fixes", "Fixes"),
             "plan": ("proposed change to the migration plan", "proposed changes to the migration plan", "migration/systems", "Migration"),
             "dependency": ("proposed dependency update", "proposed dependency updates", "migration/dependencies", "Dependencies")}
    items = [{"kind": kind, "count": counts.get(kind, 0),
              "text": f"{counts[kind]} {one if counts[kind] == 1 else many}", "link": {"page": page, "item": None}, "page_label": label}
             for kind, (one, many, page, label) in words.items() if counts.get(kind)]
    total = sum(int(counts.get(kind) or 0) for kind in words)
    return {"title": "Waiting for you", "total": total, "items": items,
            "line": (f"{total} {'proposal' if total == 1 else 'proposals'} from Otto {'waits' if total == 1 else 'wait'} for your decision."
                     if total else "Nothing from Otto is waiting for a decision."),
            "note": "Otto proposes; a person decides. Nothing is added, run or applied by itself."}


# ---------------------------------------------------------------- the Advisories page

def _trial_lines(advisory: dict) -> list[str]:
    """How a test did when it was tried on public copies: counts only."""
    trial = advisory["test"]["trial"]
    if trial is None:
        return []
    arms, package = trial["arms"], advisory["package"]["name"]
    a, f, c = arms["affected"], arms["fixed"], arms["accept-all"]
    lines = []
    def counted(arm: dict) -> str:
        return f"{arm['wrong']} of {arm['total']} {_plural(arm['total'], 'case')} wrong"
    if "total" in a:
        lines.append(f"{package} {a.get('version')} (affected): {counted(a)}.")
    if "total" in f:
        lines.append(f"{package} {f.get('version')} (the publisher's fixed version): {counted(f)}.")
    if "total" in c:
        lines.append(f"The control that must fail (a program that accepts every signature): {counted(c)}.")
    # The replay is a second, separate step of the same build on the same computer: said as that, not as an outside check.
    lines.append(f"Otto's harness judged the trial against thresholds fixed before the first run: {trial['outcome'].replace('_', ' ')}."
                 + (" It was then run again as a separate replay step of the same build, on the same computer, and gave the same numbers."
                    if trial["replayed"] else " It was not replayed."))
    return lines


def _fix_block(advisory: dict, fix_view: dict | None, own_programs: list[str]) -> dict:
    """The fix line of an advisory's panel. `fix_view` is the entry in Fixes that answers this advisory's check here.
    `own_programs`: the assessment's own programs (our demo components, never a real library) that have this check."""
    fix = advisory["fix"]
    lines, label = [fix["reason"]], None
    if fix["kind"] == "update":
        label = FIX_LABEL
        lines = [f"Otto proposes: update {fix['library']} to {fix['version']} or later.", fix["summary"], fix["reason"]]
    elif advisory["reading"] and advisory["reading"].get("fixed"):
        fixed = advisory["reading"]["fixed"]
        lines = [f"The publisher names {fixed['version']} as the fixed version.", fix["reason"]]
    quote = None
    if fix["quote"] is not None:
        quote = _quoted(advisory, fix["quote"])
    elif advisory["reading"] and advisory["reading"].get("fixed"):
        quote = _quoted(advisory, advisory["reading"]["fixed"]["quote"])
    link = None
    if fix_view is not None:
        link = {"label": "View in Fixes", "link": {"page": "fixes", "item": fix_view["id"]},
                "line": f"In this assessment: {fix_view['title']} ({fix_view['status']['word']})."}
    elif own_programs and advisory["test"]["state"] == "ready":
        lines.append(f"For your own code ({', '.join(own_programs)}): if this advisory's check fails here, Fixes shows what can be offered. "
                     "A change Otto wrote is offered only when it can be proven on this computer. Where it can't be, the fix template is "
                     "offered if it answers the failure; if not, Fixes lists the failure with a plain suggestion and offers no code change.")
    return {"title": "Fix", "label": label, "state": fix["state"], "lines": lines, "quote": quote, "here": link}


def _quoted(advisory: dict, quote: dict) -> dict:
    source = next((s for s in advisory["sources"] if s["label"] == quote["source"]), advisory["sources"][0])
    # the link goes to the address the quoted text was read from on that day, so "read on" is true of what it opens
    return {"text": quote["text"], "source": source["title"], "publisher": source["publisher"],
            "href": present_advisory.safe_href(source["read_from"]), "read_on": day(source["fetched"]), "tag": PUBLISHER_TAG}


def _steps(advisory: dict) -> list[dict]:
    out = []
    for step in advisory["steps"]:
        where = step["how"] if step["source"] == "recorded" else f"Live: Claude ({step['model']})"
        out.append({"step": STEP_WORDS.get(step["step"], step["step"]), "source": step["source"],
                    "line": f"{STEP_WORDS.get(step['step'], step['step'])}: {where}, {day(step['at'])}."
                            + ("" if step["outcome"] == "used" else f" The answer was not used: {step['refusal']}"),
                    "prompt_sha256": step["prompt_sha256"], "answer_sha256": step["answer_sha256"]})
    return out


def _notes(advisory: dict) -> dict | None:
    """What Claude noted when it read the advisory, as that: its words, where they came from, and the kind of weakness
    it recorded (the notes can refer to it). Information, never a result."""
    reading = advisory["reading"]
    if not reading:
        return None
    kind = KIND_WORDS.get(str(reading["kind"]), "has a weakness of another kind")
    area = AREA_WORDS.get(str(reading["area"]), "outside signature checking")
    read = next((s for s in advisory["steps"] if s["step"] == "read_advisory" and s["outcome"] == "used"), None)
    where = (read["how"] if read["source"] == "recorded" else f"Live: Claude ({read['model']})") if read else None
    return {"title": "Otto's notes on reading it",
            "kind_line": f"Kind of weakness, as Otto recorded it: the affected software {kind}, {area}.",
            "text": reading["notes"] or None,
            "caption": ("Claude's words from reading the advisory" + (f" ({where})" if where else "") + ". S1, S2 and so on are the "
                        "sources listed above. Information, not a result.")}


def _proposal_cell(views: list[dict]) -> dict:
    """The Proposal cell of an advisory's row: where Otto's proposed check stands, or the counts when it fits several
    programs. A count never merges two states."""
    if not views:
        return {"key": "none", "label": "Nothing proposed", "tone": "neutral", "text": None}
    if len(views) == 1:
        status = views[0]["status"]
        return {"key": status["key"], "label": status["word"], "tone": status["tone"], "text": None}
    counts = {key: sum(1 for v in views if v["status"]["key"] == key) for key in ("proposed", "accepted", "rejected")}
    words = {"proposed": "proposed", "accepted": "added", "rejected": "not added"}
    lead = next(key for key in ("proposed", "accepted", "rejected") if counts[key])
    label = {"proposed": "Proposed", "accepted": "Added", "rejected": "Not added"}[lead]
    same = counts[lead] == len(views)
    return {"key": lead if same else "mixed", "label": label if same else "Mixed", "tone": "warn" if counts["proposed"] else "neutral",
            "text": ", ".join(f"{counts[key]} {words[key]}" for key in ("proposed", "accepted", "rejected") if counts[key]),
            "keys": [key for key in ("proposed", "accepted", "rejected") if counts[key]]}


def advisories_view(*, rows: list[dict], packs: list, fitting: list[str], closed: bool, harness_status: dict, answers_line: str,
                    assessment_id: int | None) -> dict:
    out = []
    waiting = 0
    for row in rows:
        pack, advisory, design = row["pack"], row["advisory"], row["design"]
        reading = advisory["reading"]
        state = advisory["test"]["state"]
        label, tone = TEST_LABELS[state]
        name = reading["plain_name"] if reading else "An advisory Otto could not read"
        here = []
        for entry in row["here"]:
            result = entry["result"]
            proposal = proposal_view(entry["proposal"], entry.get("decision_ledger")) if entry.get("proposal") is not None else None
            if proposal is not None and proposal["status"]["key"] == "proposed":
                waiting += 1
            if entry["item_id"] is None:
                status = proposal["status"]["word"] if proposal is not None else "Not in the test plan"
            elif result is None:
                status = "Not run yet"
            else:
                status = None
            here.append({"program": entry["program"], "status": status, "proposal": proposal,
                         "result": ({"label": result["label"], "tone": result["tone"], "plain": result["plain"],
                                     "component": result.get("component"), "finished_at": result.get("finished_at")} if result else None),
                         "checks_link": {"page": "checks", "item": f"test-{entry['item_id']}"} if entry["item_id"] is not None else None,
                         "evidence_link": {"page": "evidence", "item": f"test-{entry['item_id']}"} if result else None,
                         "ledger": {"title": "Otto ledger entries for this check", "count": len(entry["ledger"]),
                                    "entries": _entries(entry["ledger"]),
                                    "note": ("The ledger shows that each run belongs to the test locked before it. It holds no result.")}
                         if entry["ledger"] else None})
        results = [h["result"] for h in here if h["result"]]
        # The latest result of its check here, in the reviewer's words. With more than one program, the one that says most.
        shown = next((r for r in results if r["tone"] == "fail"), None) or next((r for r in results if r["tone"] != "pass"), None) \
            or (results[0] if results else None)
        if shown is not None:
            # for the Result filter: Failed, Passed, or the one option for every result that is neither
            same, ran = sum(1 for r in results if r["label"] == shown["label"]), len(results)
            if len(here) == 1:
                counted = None
            elif ran == len(here):
                counted = f"{same} of {ran} programs"
            else:       # some programs have no result yet: the count is of the ones that ran, and says how many have not
                counted = f"{same} of {ran} run so far; {len(here) - ran} with no result yet"
            result_cell = {"key": shown["tone"] if shown["tone"] in ("pass", "fail") else "warn", "label": shown["label"], "tone": shown["tone"],
                           "text": counted}
        elif state != "ready":
            result_cell = {"key": "none", "label": "No check", "tone": "neutral", "text": None}
        elif not here:
            result_cell = {"key": "none", "label": "Fits no program here", "tone": "neutral", "text": None}
        elif any(h["status"] == "Not run yet" for h in here):
            result_cell = {"key": "not_run", "label": "Not run yet", "tone": "neutral", "text": None}
        else:
            result_cell = {"key": "not_added", "label": "Not in the test plan", "tone": "neutral", "text": None}
        proposal_cell = _proposal_cell([h["proposal"] for h in here if h["proposal"] is not None])
        fits = ([h["program"] for h in here] if state == "ready" else [])
        test_block, no_test = None, None
        if design is not None:
            cases = design["cases"]
            total = len(cases["ids"])
            parts = f"{cases['must_reject']} that must be rejected" + (f" and {cases['must_accept']} that must be accepted" if cases["must_accept"] else "")
            test_block = {
                "title": "The test",
                "question": design["question"].replace("{program}", "the program"),
                "cases_line": f"{_count(total, 'published case')} from Project Wycheproof, pinned by SHA-256: {parts}.",
                "control": designs.BLOCKS[designs.BLOCK]["controls"][designs.CONTROL],
                "rule": designs.BLOCKS[designs.BLOCK]["rule"],
                "design_fingerprint": advisory["test"]["design_sha256"],
                "trial": {"title": "How it did when tried on public copies", "lines": _trial_lines(advisory)},
                "ledger": {"title": "Otto ledger entries", "count": len(advisory["ledger"]),
                           "entries": _entries(advisory["ledger"]),
                           "note": ("From Otto's research ledger, a hash chain kept with the Otto harness: the test was registered, tried and "
                                    "judged before the pack was signed.")}}
        else:
            no_test = {"label": label, "reason": advisory["test"]["reason"],
                       "trial": ({"title": "How its design did when tried on public copies", "lines": _trial_lines(advisory)}
                                 if advisory["test"]["trial"] else None),
                       "ledger": ({"title": "Otto ledger entries", "count": len(advisory["ledger"]),
                                   "entries": _entries(advisory["ledger"]),
                                   "note": "From Otto's research ledger, a hash chain kept with the Otto harness."} if advisory["ledger"] else None)}
        own = [entry["program"] for entry in row["here"] if entry["own_code"] and entry["item_id"] is not None]
        out.append({
            "id": advisory["id"], "name": name, "published": advisory["published"], "published_text": day(advisory["published"]),
            "package": f"{advisory['package']['name']} ({advisory['package']['ecosystem']})", "pack": pack.version,
            "fits": fits, "fits_text": (", ".join(fits) if fits else ("No signing program in this assessment" if state == "ready" else "")),
            "test": {"key": state, "label": label, "tone": tone, "reason": advisory["test"]["reason"]},
            "proposal": proposal_cell,
            "result": result_cell,
            "search": " ".join([advisory["id"], name, advisory["package"]["name"], *advisory["aliases"], *fits]).lower(),
            "panel": {
                "sentence": reading["weakness"] if reading else advisory["reading_refused"],
                "publisher": _quoted(advisory, reading["weakness_quote"]) if reading else None,
                "affected": ({"line": f"Affected versions, in the publisher's terms: {reading['affected']['versions']}",
                              "quote": _quoted(advisory, reading["affected"]["quote"])} if reading else None),
                "notes": _notes(advisory),
                "also_known_as": advisory["aliases"],
                "sources": [{"label": s["label"], "title": s["title"], "publisher": s["publisher"],
                             "href": present_advisory.safe_href(s["read_from"]), "read_on": day(s["fetched"])} for s in advisory["sources"]],
                "test": test_block, "no_test": no_test,
                "here": {"title": "Otto's proposed check, in this assessment", "rows": here,
                         "note": ("Otto proposes; you decide for each program by itself. Accepting adds the check to the test plan and "
                                  "runs nothing.") if here else None,
                         "empty": (None if here else
                                   "This advisory has no test, so there is nothing to run here." if state != "ready" else
                                   "No signing program in this assessment's file checks ECDSA P-256 signatures, so the test fits nothing here.")},
                "fix": _fix_block(advisory, row["fix"], own),
                "claude": {"title": "What Otto asked Claude", "steps": _steps(advisory),
                           "note": "Every prompt and answer is in Otto's research ledger, with its SHA-256. What Claude writes is data: a "
                                   "quote must stand in the publisher's text, a design can only pick published cases, and a fix is offered "
                                   "only after its proof."},
                "related_key": f"advisory:{advisory['id']}",
            },
        })
    installed = bool(harness_status["installed"])
    if closed:
        blocked = "This assessment is closed, so nothing more can be decided in it."
    elif not installed:
        blocked = ("Otto is not installed on this computer, so nothing can be decided: a decision is recorded in Otto's "
                   "ledger.")      # the reason is in the Otto line
    elif not packs:
        blocked = "No test pack is installed. Install one in Settings, under Test packs."
    elif not fitting:
        blocked = "No signing program in this assessment's file checks ECDSA P-256 signatures, so no pack test fits it."
    else:
        blocked = None
    versions = ", ".join(p.version for p in packs)
    return {
        "title": "Advisories",
        "subline": ("Every published advisory in the installed test packs. Where one has a test that fits a signing program of this "
                    "assessment, Otto proposes its check: you accept or reject it. A result shown here is the reviewer's, in its words."),
        "standing_line": DISCLAIMER,
        "packs_line": ((f"Test packs installed when this assessment was closed: {versions}." if closed else f"Test packs installed: {versions}.")
                       if packs else "No test pack is installed yet. Settings, Test packs, Check for updates."),
        "packs_link": {"page": "settings", "item": None, "section": "test-packs"},
        "answers_line": answers_line,
        "otto": {"installed": installed, "line": harness_status["sentence"] + ("" if installed else NOT_INSTALLED_TAIL)},
        # Otto proposes; a person decides. There is no button that decides several at once.
        "waiting": {"count": waiting, "blocked_reason": blocked,
                    "line": ((f"{waiting} proposed {'check waits' if waiting == 1 else 'checks wait'} for your decision. Open an advisory "
                              "to accept or reject its check.") if waiting else
                             "No proposed check is waiting for a decision." if blocked is None else blocked),
                    "note": "Otto proposes; you decide each one by itself. Accepting adds a check to the test plan. It runs nothing."},
        "filters": {"test": [{"key": "all", "label": "Any test"}] + [{"key": k, "label": v[0]} for k, v in TEST_LABELS.items()],
                    "decision": [{"key": "all", "label": "Any decision"}, {"key": "proposed", "label": "Proposed"},
                                 {"key": "accepted", "label": "Added"}, {"key": "rejected", "label": "Not added"}],
                    "result": [{"key": "all", "label": "Any result"}, {"key": "fail", "label": "Failed"}, {"key": "pass", "label": "Passed"},
                               {"key": "warn", "label": "Couldn't run or trust"}, {"key": "not_run", "label": "Not run yet"},
                               {"key": "not_added", "label": "Not in the test plan"}, {"key": "none", "label": "No check"}]},
        "columns": ["Advisory", "Published", "Fits", "Test", "Otto's proposal", "Result here"],
        "rows": out,
        "empty": None if out else ("No test pack is installed yet. In Settings, under Test packs, Check for updates looks in the updates "
                                   "folder on this computer."),
        "assessment_id": assessment_id,
    }
