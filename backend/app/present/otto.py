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
PUBLISHER_TAG = "from the advisory, not a result"
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
                  limit_nano: int, key_present: bool, answers_line: str) -> dict:
    cards = [pack_card(pack, at) for at, pack in installed]
    newest = cards[-1] if cards else None
    box = None
    if update is not None:
        adds = pack_adds(update)
        box = {"version": update.version, "button": "Install update",
               "line": f"Test pack {update.version} is in the updates folder.",
               "dialog": {"title": f"Install test pack {update.version}?",
                          "lines": [pack_card(update)["line"], f"Signed by: {update.signer}.",
                                    "It adds:"] + adds +
                                   ["Nothing in a pack runs. Installing adds no check to any assessment: you add its checks on the Advisories page.",
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
                               else "No test pack is installed yet."),
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


# ---------------------------------------------------------------- the Advisories page

def _trial_lines(advisory: dict) -> list[str]:
    """How a test did when it was tried on public copies: counts only."""
    trial = advisory["test"]["trial"]
    if trial is None:
        return []
    arms, package = trial["arms"], advisory["package"]["name"]
    a, f, c = arms["affected"], arms["fixed"], arms["accept-all"]
    lines = []
    if "total" in a:
        lines.append(f"{package} {a.get('version')} (affected): {a['wrong']} of {a['total']} cases wrong.")
    if "total" in f:
        lines.append(f"{package} {f.get('version')} (the publisher's fixed version): {f['wrong']} of {f['total']} cases wrong.")
    if "total" in c:
        lines.append(f"The control that must fail (a program that accepts every signature): {c['wrong']} of {c['total']} cases wrong.")
    lines.append(f"Otto's harness judged the trial against thresholds fixed before the first run: {trial['outcome'].replace('_', ' ')}."
                 + (" A second author replayed it with the same numbers." if trial["replayed"] else " It was not replayed."))
    return lines


def _fix_block(advisory: dict, fix_view: dict | None, own_program: bool) -> dict:
    """The fix line of an advisory's panel. `fix_view` is the entry in Fixes that answers this advisory's check here."""
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
    elif own_program and advisory["test"]["state"] == "ready":
        lines.append("For your own code: if this advisory's check fails here, Fixes offers a change. A change Otto wrote is offered only "
                     "when it can be proven on this computer; otherwise the fix template takes its place.")
    return {"title": "Fix", "label": label, "state": fix["state"], "lines": lines, "quote": quote, "here": link}


def _quoted(advisory: dict, quote: dict) -> dict:
    source = next((s for s in advisory["sources"] if s["label"] == quote["source"]), advisory["sources"][0])
    return {"text": quote["text"], "source": source["title"], "publisher": source["publisher"], "href": present_advisory.safe_href(source["url"]),
            "read_on": day(source["fetched"]), "tag": PUBLISHER_TAG}


def _steps(advisory: dict) -> list[dict]:
    out = []
    for step in advisory["steps"]:
        where = step["how"] if step["source"] == "recorded" else f"Live: Claude ({step['model']})"
        out.append({"step": STEP_WORDS.get(step["step"], step["step"]), "source": step["source"],
                    "line": f"{STEP_WORDS.get(step['step'], step['step'])}: {where}, {day(step['at'])}."
                            + ("" if step["outcome"] == "used" else f" The answer was not used: {step['refusal']}"),
                    "prompt_sha256": step["prompt_sha256"], "answer_sha256": step["answer_sha256"]})
    return out


def advisories_view(*, rows: list[dict], packs: list, to_add: int, fitting: list[str], closed: bool, harness_status: dict, answers_line: str,
                    assessment_id: int | None, items: dict) -> dict:
    out = []
    for row in rows:
        pack, advisory, design = row["pack"], row["advisory"], row["design"]
        reading = advisory["reading"]
        state = advisory["test"]["state"]
        label, tone = TEST_LABELS[state]
        name = reading["plain_name"] if reading else "An advisory Otto could not read"
        here = []
        for entry in row["here"]:
            result = entry["result"]
            if entry["item_id"] is None:
                status = "Not added yet"
            elif result is None:
                status = "Not run yet"
            else:
                status = None
            here.append({"program": entry["program"], "status": status,
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
            result_cell = {"key": shown["tone"] if shown["tone"] in ("pass", "fail") else "warn", "label": shown["label"], "tone": shown["tone"],
                           "text": (f"{sum(1 for r in results if r['label'] == shown['label'])} of {len(here)} programs" if len(here) > 1 else None)}
        elif state != "ready":
            result_cell = {"key": "none", "label": "No check", "tone": "neutral", "text": None}
        elif not here:
            result_cell = {"key": "none", "label": "Fits no program here", "tone": "neutral", "text": None}
        elif any(h["status"] == "Not run yet" for h in here):
            result_cell = {"key": "not_run", "label": "Not run yet", "tone": "neutral", "text": None}
        else:
            result_cell = {"key": "not_added", "label": "Not added yet", "tone": "neutral", "text": None}
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
        own = any(items.get(entry["item_id"]) is not None for entry in row["here"])
        out.append({
            "id": advisory["id"], "name": name, "published": advisory["published"], "published_text": day(advisory["published"]),
            "package": f"{advisory['package']['name']} ({advisory['package']['ecosystem']})", "pack": pack.version,
            "fits": fits, "fits_text": (", ".join(fits) if fits else ("No signing program in this assessment" if state == "ready" else "")),
            "test": {"key": state, "label": label, "tone": tone, "reason": advisory["test"]["reason"]},
            "result": result_cell,
            "search": " ".join([advisory["id"], name, advisory["package"]["name"], *advisory["aliases"], *fits]).lower(),
            "panel": {
                "sentence": reading["weakness"] if reading else advisory["reading_refused"],
                "publisher": _quoted(advisory, reading["weakness_quote"]) if reading else None,
                "affected": ({"line": f"Affected versions, in the publisher's terms: {reading['affected']['versions']}",
                              "quote": _quoted(advisory, reading["affected"]["quote"])} if reading else None),
                "notes": (reading["notes"] or None) if reading else None,
                "also_known_as": advisory["aliases"],
                "sources": [{"label": s["label"], "title": s["title"], "publisher": s["publisher"], "href": present_advisory.safe_href(s["url"]),
                             "read_on": day(s["fetched"])} for s in advisory["sources"]],
                "test": test_block, "no_test": no_test,
                "here": {"title": "In this assessment", "rows": here,
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
        blocked = "This assessment is closed, so nothing can be added to it."
    elif not installed:
        blocked = "Otto is not installed on this computer, so nothing can be added."      # the reason is in the Otto line
    elif not packs:
        blocked = "No test pack is installed. Install one in Settings, under Test packs."
    elif to_add == 0:
        blocked = ("Every test of the installed packs that fits this assessment is already in the test plan." if fitting else
                   "No signing program in this assessment's file checks ECDSA P-256 signatures, so no pack test fits it.")
    else:
        blocked = None
    versions = ", ".join(p.version for p in packs)
    return {
        "title": "Advisories",
        "subline": ("Every published advisory in the installed test packs: whether it has a test, which signing programs of this assessment "
                    "it fits, and the latest result of its check here, in the reviewer's words."),
        "standing_line": DISCLAIMER,
        "packs_line": ((f"Test packs installed when this assessment was closed: {versions}." if closed else f"Test packs installed: {versions}.")
                       if packs else "No test pack is installed yet. Settings, Test packs, Check for updates."),
        "packs_link": {"page": "settings", "item": None, "section": "test-packs"},
        "answers_line": answers_line,
        "otto": {"installed": installed, "line": harness_status["sentence"] + ("" if installed else NOT_INSTALLED_TAIL)},
        "add": {"button": f"Add new checks ({to_add})" if to_add else "Add new checks", "count": to_add, "can": blocked is None,
                "blocked_reason": blocked,
                "note": "Adds every pack test that fits a program in this assessment and is not in the test plan yet. It runs nothing."},
        "filters": {"test": [{"key": "all", "label": "Any test"}] + [{"key": k, "label": v[0]} for k, v in TEST_LABELS.items()],
                    "result": [{"key": "all", "label": "Any result"}, {"key": "fail", "label": "Failed"}, {"key": "pass", "label": "Passed"},
                               {"key": "warn", "label": "Couldn't run or trust"}, {"key": "not_run", "label": "Not run yet"},
                               {"key": "not_added", "label": "Not added yet"}, {"key": "none", "label": "No check"}]},
        "columns": ["Advisory", "Published", "Fits", "Test", "Result here"],
        "rows": out,
        "empty": None if out else ("No test pack is installed yet. In Settings, under Test packs, Check for updates looks in the updates "
                                   "folder on this computer."),
        "assessment_id": assessment_id,
    }
