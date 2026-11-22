"""Where it came from (22 November 2026, Kevin's plan and his decisions A, B and C): one tag on every result, every system
status and every fix, beside its own word, saying what that line rests on. Live = observe; lab = test.

- Observed live: read from a system at an address in the file that the person confirmed, with handshakes only.
- Proven in the lab: run on a copy on this computer (a copy of the signing program, a public copy of a library, a test
  copy of a server, our own test server or the reference library).
- From your file: nothing has been observed or run for it; it rests only on the scanner file or the dependency list.
- Published: the library's maker (its release notes) or a published standard says it; the app has not measured it.

Words only. A tag is chosen from what the app already recorded about how a line was made: what a test runs on, how a
claim was checked, what kind of system was measured, how an answer is labelled, what a fix came from. It decides nothing,
changes no result, and nothing about it is stored. A check of ours that has not run, couldn't run or couldn't be trusted
has no tag: nothing was observed or proven. Something the file named (a claim, a system, a library's answer) that the app
couldn't check rests only on the file, and reads From your file."""
from __future__ import annotations

from typing import Any

from app.engine.research import SERVER_KINDS

LIVE, LAB, FILE, PUBLISHED = "live", "lab", "file", "published"
KEYS = (LIVE, LAB, FILE, PUBLISHED)
LABELS = {LIVE: "Observed live", LAB: "Proven in the lab", FILE: "From your file", PUBLISHED: "Published"}
# One line for each tag: what it means wherever it is shown (the tag's own explanation; a panel adds the item's sentence).
MEANINGS = {
    LIVE: "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
    LAB: "Run on a copy on this computer, never on your live system.",
    FILE: "Nothing has been observed or run for it yet: it rests only on your file.",
    PUBLISHED: "Said by the library's maker or a published standard. The app has not measured it.",
}
# A result that is no result: nothing was observed or proven.
NO_RESULT = frozenset({"couldnt_run", "couldnt_trust", "couldnt_check"})
VERIFY_COULDNT = "Couldn't check"
MODE_WORDS = {"demo": "in demo mode (a plain process on this computer, not isolated)",
              "isolated": "in isolated mode (a locked-down container with no network)"}
UNTOUCHED = "Your live system was not touched."


def tag(key: str, note: str | None = None) -> dict:
    """The tag as every view carries it: its key (which decides its look), its words, what it means, and, where the
    item says more, one sentence about this item."""
    return {"key": key, "label": LABELS[key], "meaning": MEANINGS[key], "note": note}


# ---------------------------------------------------------------- the four, with the item's own sentence

def live(where: str | None) -> dict:
    return tag(LIVE, f"Read from {where or 'the server'}, an address in your file that you confirmed, with handshakes only.")


def after_change(where: str | None, rolled_back: bool = False) -> dict:
    what = "after the earlier settings were put back" if rolled_back else "right after the change was applied there"
    return tag(LIVE, f"Measured again on {where or 'the server'} {what}, with handshakes only.")


def lab_copy(what: str | None, mode: str | None = None, real: bool = False) -> dict:
    """A test of a signing program (or a library) on a copy on this computer."""
    if real:
        return tag(LAB, f"Run on a public copy of {what or 'the library'} on this computer, in its own locked-down container. {UNTOUCHED}")
    if not what:
        return tag(LAB, f"Run on the reference library on this computer. {UNTOUCHED}")
    how = f", {MODE_WORDS[mode]}" if mode in MODE_WORDS else ""
    return tag(LAB, f"Run on a copy of {what} on this computer{how}. {UNTOUCHED}")


def lab_try(clients: bool = False) -> dict:
    note = "Run on a test copy of the server on this computer, with the change. Your live server was not changed."
    if clients:
        note += " The same client stand-ins were also connected to the server as it is today, with handshakes only, to compare."
    return tag(LAB, note)


def lab_proof() -> dict:
    """A fix's proof: the plan's tests, rerun on the changed code on this computer."""
    return tag(LAB, "Run on the changed code, a copy on this computer. Nothing was merged or deployed.")


def lab_public_copy(library: str | None) -> dict:
    return tag(LAB, f"Measured on a public copy of {library or 'the library'} on this computer, in its own locked-down container. {UNTOUCHED}")


def from_file(note: str | None = None) -> dict:
    return tag(FILE, note or "Nothing has been observed or run for it yet: it rests only on what your file says.")


def published(note: str | None = None) -> dict:
    return tag(PUBLISHED, note or "From the maker's release notes, quoted under Details and evidence. The app has not measured it.")


# ---------------------------------------------------------------- the rule, for each kind of item

def of_test(kind: str | None, result: dict | None, where: str | None = None) -> dict | None:
    """A result of a test of the plan (its first run, a retest, a proof, a watch run). A server test is handshakes to the
    server (live); every other test runs a copy of a program or a library on this computer (lab). Whatever started it:
    a retest or a proof reruns a server test against the server as it is."""
    code = (result or {}).get("code")
    if result is None or code is None or code in NO_RESULT:
        return None
    if kind in SERVER_KINDS:
        return live(where)
    return lab_copy(result.get("component"), result.get("mode"), bool(result.get("real")))


def of_verify(result: dict | None) -> dict | None:
    """A Verify result: a server claim is checked with handshakes to the confirmed address (live); a signing program's
    claim by running a copy of that program (lab). A claim the app couldn't check rests only on the file."""
    if not isinstance(result, dict):
        return None
    claim = result.get("claim") or {}
    if result.get("result") not in ("True", "False"):
        return from_file("The app couldn't check this claim, so it rests only on what your file says.")
    if claim.get("location_kind") == "server":
        return live(claim.get("location"))
    return tag(LAB, f"Checked by running a copy of {claim.get('location') or 'the program'} on this computer. {UNTOUCHED}")


def of_system(kind: str | None, status: str | None, name: str | None) -> dict:
    """A system's post-quantum status on Migration. Measured on a server: live. Measured on a signing program: lab (a copy
    of the program runs here). Not measured yet, or couldn't be measured: it rests only on the file."""
    if status in (None, "not_measured", "couldnt_check"):
        return from_file("This system has no measurement yet, so what is shown rests only on your file.")
    if kind == "server":
        return live(name)
    return tag(LAB, f"Measured by running a copy of {name or 'the program'} on this computer. {UNTOUCHED}")


def of_answer(label: str | None, answer: str | None) -> dict:
    """One answer about a library on Dependencies, by the label it already carries (Release notes say, Measured on a
    public copy). An answer with no label says what the app does not know: it rests only on the dependency list."""
    if label == "release_notes":
        return published()
    if label == "public_copy":
        return tag(LAB, f"Measured on a public copy of this version on this computer, in its own locked-down container. {UNTOUCHED}")
    if label == "your_environment":    # defined, and nothing in this version can produce it
        return tag(LIVE, "Measured in your environment.")
    if answer == "doesnt_apply":       # the knowledge base, from what the library's maker publishes, says what kind it is
        return published("This question is not asked of this kind of library, by what its maker publishes. The app has not measured it.")
    return from_file("The app has no answer for this yet: it rests only on your dependency list.")


def of_claim(filename: str | None) -> dict:
    """A claim as the file states it (Import): it is there because the file says so, until Verify checks it."""
    return from_file(f"Taken from {filename or 'your file'}. The app has not checked it here: Verify does.")


def of_library() -> dict:
    """A library of the dependency list: it is there because the list names it."""
    return from_file("Listed in your dependency list. The app has not checked that your system loads it.")


def of_answers(cells: list[dict]) -> dict:
    """A library's answers taken together (Evidence lists a library as one row): measured if any was measured, else
    published if any came from release notes, else only the list."""
    labels = {c.get("label") for c in cells or []}
    if "public_copy" in labels:
        return of_answer("public_copy", None)
    if "release_notes" in labels:
        return published()
    return of_library()


def of_check_row(row: dict) -> dict | None:
    """A row of Checks (and of Evidence's other groups), from what the row already holds: its kind, what started it
    and its result."""
    result = row.get("result") or None
    code = (result or {}).get("code")
    origin = (row.get("came_from") or {}).get("key")
    kind = row.get("kind")
    where = row.get("ran_on") or None
    if origin == "verify":
        return of_verify(row.get("verify"))
    if result is None or code is None:
        return None
    if code in NO_RESULT:
        # a system that couldn't be measured still stands on the file; a check of ours that couldn't run has no tag
        return of_system(None, "couldnt_check", None) if kind in ("pq_status", "signing_status") else None
    if origin == "try":
        return lab_try(clients=kind == "client_reach")
    if origin in ("after_apply", "after_rollback"):
        return after_change(where, rolled_back=origin == "after_rollback")
    if kind == "pq_status":
        return live(where)
    if kind == "signing_status":
        return of_system("software", "measured", where)
    if kind == "capability":
        return lab_public_copy(row.get("name"))
    if kind in SERVER_KINDS:
        return live(where)
    return lab_copy(where)


def of_fix(fix: dict, address: str | None = None) -> dict:
    """A fix carries the tag of the finding it came from (its "Came from" line names it). `fix` is its state (fix_states);
    `address` is the server a text-only fix's failed test was about (None for a signing program)."""
    kind = fix.get("source_kind")
    if kind == "dependency":
        return from_file("From your dependency list. The app has not checked that your system loads this library.")
    if kind == "developer_change":
        return tag(LAB, "From the tests picked for a developer's change, run on a copy of that code on this computer. Nothing was merged.")
    if kind == "applied_change":
        return after_change(address)
    if kind == "migration":
        system = str((fix.get("migration") or {}).get("system") or "")
        if fix.get("test_kind") == "pq_status":
            return live(system.split(":", 1)[1] if system.startswith("server:") else None)
        return of_system("software", "measured", None)
    if fix.get("kind") == "code":
        component = fix.get("component") or {}
        words = " ".join(str(x) for x in (component.get("name"), component.get("version")) if x)
        return tag(LAB, f"From tests that failed on a copy of {words or 'the program'} on this computer. {UNTOUCHED}")
    if address:
        return live(address)
    return tag(LAB, f"From tests that failed on a copy on this computer. {UNTOUCHED}")


# ---------------------------------------------------------------- the small tags a panel already has

# The small grey tags the pages already show beside a number ("measured", "measured on our test server", "published: FIPS
# 203"), each given the look of the source it belongs to. Their words stay exactly as they are.
_LAB_TAGS = ("measured on our test server", "measured on the reference library", "measured on the copy", "measured on nginx",
             "measured on a public copy")


def family_of(text: str, measured: str | None) -> str | None:
    """The source of one small tag, by its words. `measured`: what the bare word "measured" means where it stands (live on
    a server, lab on a signing program); None where it is not said."""
    words = str(text or "").strip().lower()
    if words == "measured":
        return measured
    if words in _LAB_TAGS:
        return LAB
    if words.startswith("published"):
        return PUBLISHED
    if words == "from the file":
        return FILE
    return None


def colour_tags(value: Any, measured: str | None) -> Any:
    """Every small tag in a view (the {"t": "tag"} parts of its sentences) gets "s", the source it belongs to, where its
    words say one. Nothing else is touched; the words stay."""
    if isinstance(value, dict):
        if value.get("t") == "tag" and "v" in value:
            family = family_of(value["v"], measured)
            if family is not None:
                value["s"] = family
        else:
            for v in value.values():
                colour_tags(v, measured)
    elif isinstance(value, list):
        for v in value:
            colour_tags(v, measured)
    return value


def counted(sources: list[dict | None], extra_file: int = 0) -> list[dict]:
    """How many items rest on each source, in the fixed order, the ones with none left out (the Overview's line)."""
    n = {k: 0 for k in KEYS}
    for s in sources:
        if s is not None:
            n[s["key"]] += 1
    n[FILE] += extra_file
    return [{"key": k, "label": LABELS[k], "meaning": MEANINGS[k], "count": n[k]} for k in KEYS if n[k]]


__all__ = ["FILE", "KEYS", "LAB", "LABELS", "LIVE", "MEANINGS", "PUBLISHED", "after_change", "colour_tags", "counted", "family_of",
           "from_file", "lab_copy", "lab_proof", "lab_public_copy", "lab_try", "live", "of_answer", "of_answers", "of_check_row", "of_claim", "of_fix",
           "of_library", "of_system", "of_test", "of_verify", "published", "tag"]
