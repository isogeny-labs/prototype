"""The words of "New advisories" on the Advisories page (phase 6, Otto's research loop). It words no result.

Two buttons, each with a box that says what it will do before anything is sent or started: **Look for new advisories**
(a read of one public source) and **Design and prove tests** (the research step, tried on public copies). A proposal
appears on Advisories only for a test that was proven; an advisory with no proven test says why.
"""

from __future__ import annotations

from app.names import join_and
from app.present.otto import day, stamp

TITLE = "New advisories"
INTRO = (
    "Published advisories about the libraries this assessment names, read from a public source. A check is proposed "
    "only after its test was proven on public copies: it fails on the affected version, passes on the fixed version, "
    "and the control that must fail does."
)
CLOSED_SENTENCE = "This assessment is closed. Start a new one to continue."
ECOSYSTEM_WORDS = "npm, PyPI, Go, Maven, crates.io, NuGet and RubyGems"
LOOK_LABEL, RESEARCH_LABEL = "Look for new advisories", "Design and prove tests"
LOOK_NOTHING_TO_ASK = (
    f"This assessment names no library the source keeps by name. It keeps packages of {ECOSYSTEM_WORDS}; "
    "other libraries, such as OpenSSL and Java, are not kept there by name."
)
NO_FIXED_VERSION = "No test yet: the source names no fixed version, so there is nothing to prove a test against."
# Sandbox research (a prototype): the reasons a test can't be tried on public copies made from a public registry.
HARMFUL_PACKAGE = (
    "No test yet: the source marks this record as a package that was published to do harm. Such a package is never "
    "fetched or run here."
)
NO_VERSION_FIELDS = (
    "No test yet: the source gives no version fields for this advisory, so the versions of a trial can't be chosen "
    "by fixed rules. Nothing is guessed."
)
WATCH_LINK = "On the Watch list"
SANDBOX_COVERS = (
    "Sandbox research is on (a prototype): for a library the app holds no pinned copy of, public copies are fetched from "
    "npm or PyPI by the research run, checked against the registry's own fingerprint, and run only in locked containers "
    "on this computer. Where no code of ours asks the library its questions, Claude writes it, and it is used only "
    "after fixed checks; the separate reviewer still decides every run from the publisher's own answers."
)
CANT_TELL_VERSION = (
    "No test yet: it could not be told whether this advisory names the version you have, because a version could "
    "not be read. Nothing is guessed, so no test was designed."
)
RESEARCH_RUNNING = "A research run is going on. Wait for it to finish."
RESEARCH_NOTHING = (
    "No new advisory can be tried here. Look for new advisories first, or see the reason beside each one."
)
RESEARCH_NEEDS_ISOLATED = (
    "Trying a test on public copies needs isolated mode (Docker): a real library runs only in its own "
    "locked-down container."
)
RESEARCH_NO_PACK = "The research run ended without a test pack."
RESEARCH_STOPPED = "The research run stopped before it finished."
RESEARCH_TOO_LONG = (
    "The research run took longer than this version allows (four hours) and was ended. No test pack was made by it."
)
INTERRUPTED = "This run was interrupted (the app was stopped while it ran). It made no test pack. Start it again."
# Two lines of the research command that the app reads from what the command said (the app never imports the research
# side, so these exact beginnings are what the two share). "Left for a later run: <advisory id>: <why>": the run could
# not settle that advisory (no answer, or a trial that did not finish), signed nothing about it, and it can be tried
# again. "No test pack was made: ...": it settled none, so there is no pack.
LEFT_PREFIX = "Left for a later run: "
NO_PACK_PREFIX = "No test pack was made: "
COVERS = (
    "What this covers: libraries published on "
    + ECOSYSTEM_WORDS
    + ", asked about by name at OSV (osv.dev). A test can be "
    "proven only for a library this version of the app has public copies of, in an affected and a fixed version "
    "(of the libraries the source keeps by name, today: python-ecdsa and elliptic, in the versions pinned in the app), "
    "and only from published test cases it can run today (ECDSA P-256 signature checks). Anything else reads “No test "
    "yet”, with the reason."
)
STATES = {
    "in_pack": ("In a test pack", "neutral"),
    "in_waiting_pack": ("In a built-in test pack", "neutral"),
    "new": ("New: not tried yet", "warn"),
    "no_test": ("No test yet", "neutral"),
    "not_yours": ("Not about a version you have", "neutral"),
    "proven": ("Proven on public copies", "pass"),
    "being_tried": ("Being tried", "warn"),
    "still_open": ("Still open", "warn"),
}


def waiting_made_here(version: str) -> str:
    return (
        f"Test pack {version}, made on this computer, is waiting to be installed. Install it first: Settings, Test packs, "
        "Check for updates."
    )


def no_registry(library: str, ecosystem: str) -> str:
    return (
        f"No test yet: {library} is published on {ecosystem}, and this version can make a public copy only of a package on npm or "
        "PyPI."
    )


def can_try_line(copies: dict) -> str:
    """Beside a new advisory that can be tried on sandbox copies: what would be fetched, as far as the app knows it
    (the exact versions are chosen by the research run, from the registry's own list of releases)."""
    library, where = copies["library"], copies["registry_words"]
    if copies.get("fixed"):
        pair = f"{library} {copies['fixed']}, the fixed version, and the release before it"
    else:
        pair = f"{library} {copies['after']}, the last version the source names as affected, and the release after it"
    return f"A test can be tried on public copies from {where}: {pair}."


def fetch_lines(rows: list[dict]) -> list[str]:
    """For the box of Design and prove tests: what a run would fetch for the advisories that need sandbox copies."""
    wanted = [r["sandbox"] for r in rows if r.get("state") == "new" and r.get("sandbox")]
    if not wanted:
        return []
    out = ["What will be fetched, from the public package registry and nowhere else:"]
    for copies in {(c["library"], c["registry"]): c for c in wanted}.values():
        library, where = copies["library"], copies["registry_words"]
        named = (
            f"{library} {copies['fixed']} (the fixed version) and the release before it"
            if copies.get("fixed")
            else f"{library} {copies['after']} (the last version named as affected) and the release after it"
        )
        yours = [v for v in copies.get("yours") or [] if v != copies.get("fixed")]
        out.append(
            f"From {where}: {named}"
            + (f"; {join_and([f'{library} {v}' for v in yours])}, which your file names" if yours else "")
            + "; up to two further versions on each side; and the helper libraries those versions say they need."
        )
    out.append(
        "What is sent to the registry: the package's name and a version, as part of the address of a public file. Nothing of "
        "your assessment is sent."
    )
    out.append(
        "Each file is checked against the registry's own fingerprint. Nothing of a package runs while it is fetched or "
        "unpacked, and a copy runs only in a locked container on this computer, with no network."
    )
    out.append(
        "Where the app has no code of its own that asks a library the test's questions, that code is written for it "
        "(by Claude with Live Otto on, otherwise from a recorded answer), twice, apart. It is used only after fixed checks, it "
        "never sees a right answer, and the separate reviewer decides every run."
    )
    return out


def no_copy_of(library: str) -> str:
    return (
        f"No test yet: this version of the app has no public copy of {library} to try a test on, so none was designed."
    )


def no_copy_of_version(library: str, fixed: str, have: list[str]) -> str:
    return (
        f"No test yet: a test is proven against the fixed version, {library} {fixed}, and this version of the app has no public "
        f"copy of it (it has {join_and([f'{library} {v}' for v in have])}), so none was designed."
    )


def _fits_line(row: dict) -> str:
    library, fits = row["library"], row["fits"]
    if not fits:
        return f"About {library}."
    said = []
    for f in fits:
        label, where = f["label"], f["where"]
        if f["state"] == "affected":
            said.append(
                f"Names {label}, which {where} lists"
                + (f"; fixed in {f['fixed']}." if f.get("fixed") else "; no fixed version is named.")
            )
        elif f["state"] == "not_affected":
            said.append(f"{label}, which {where} lists, is not among the versions it names.")
        elif f["state"] == "cant_tell":
            said.append(
                f"It could not be told whether it names {label}: a version could not be read. Nothing is guessed."
            )
        else:
            said.append(
                f"About {library}; {where} lists {label}. The versions it names are read from the publisher's text when its test is designed."
            )
    return " ".join(dict.fromkeys(said))


def _row_view(row: dict, running_ids: set[str], left_open: dict[str, str] | None = None) -> dict:
    advisory = row["advisory"]
    source = advisory["sources"][0]
    state, reason, link = row["state"], row.get("why"), None
    label, tone = STATES[state]
    entry = row.get("entry")
    if state == "in_pack" and entry is not None:
        link = {"page": "advisories", "item": entry["id"]}
        test = entry.get("test") or {}
        if test.get("state") == "ready":
            label, tone = f"Proven on public copies (test pack {row['pack']})", "pass"
            reason = "It is in the list below."
        else:
            label = f"No test yet (test pack {row['pack']})"
            reason = str(test.get("reason") or "")
            if entry.get("reading") is None and entry.get("reading_refused"):
                reason = str(entry["reading_refused"])
    elif state == "in_waiting_pack" and row.get("pack_made_here"):
        label = f"In test pack {row['pack']}, made on this computer, which is not installed yet"
        reason = "Install it in Settings, under Test packs."
    elif state == "in_waiting_pack":
        label = f"In built-in test pack {row['pack']}, which is not installed yet"
        reason = "It is installed from Settings, or by Design and prove tests."
    elif state == "new" and advisory["id"] in running_ids:
        label, tone = STATES["being_tried"]
    elif state == "new" and advisory["id"] in (left_open or {}):
        # the last research run could not settle it: nothing was signed about it, and it can be tried again
        label, tone = STATES["still_open"]
        reason = f"The last research run left it open: {(left_open or {})[advisory['id']]} It can be tried again."
    elif state == "new" and row.get("sandbox"):
        reason = can_try_line(row["sandbox"])
    watch = None
    if state == "no_test" and row.get("watch_item"):
        # (sandbox research: a weakness with no fix yet is kept on the Watch list, which says when a fix is published)
        watch = {
            "label": WATCH_LINK,
            "link": {"page": "change-watch", "item": row["watch_item"], "section": "watch-list"},
        }
    return {
        "id": advisory["id"],
        "title": source["title"],
        "library": row["library"],
        "published": day(advisory["published"]),
        "fits": _fits_line(row),
        "state": {"key": state, "label": label, "tone": tone},
        "reason": reason,
        "link": link,
        "publisher": source["publisher"],
        "url": source["url"],
        "sandbox": bool(row.get("sandbox")),
        "watch": watch,
    }


def lookup_view(
    *,
    libraries: list[dict],
    packages: list[str],
    skipped: list[str],
    recorded: bool,
    closed: bool,
    look: dict | None,
    rows: list[dict],
    eligible: int,
    research_blocked: str | None,
    waiting_packs: list[str],
    live: bool,
    limit: str,
    isolated: bool,
    run: dict | None,
    left_open: dict[str, str] | None = None,
    sandbox: bool = False,
    sandbox_line: str | None = None,
) -> dict:
    names = join_and(packages)
    if recorded:
        look_lines = [
            "Reads the recorded answers in a folder on this computer about the libraries this assessment names.",
            "Nothing is sent anywhere.",
        ]
    else:
        look_lines = [
            "Asks OSV (osv.dev), a public database of published advisories, about the libraries this assessment names.",
            f"What is sent: {'this package name' if len(packages) == 1 else 'these package names'}, and nothing else: {names}.",
            "No version, no address and no file leaves this computer. Whether an advisory names a version you have is worked "
            "out here.",
        ]
    if skipped:
        look_lines.append(
            f"Not asked about: {join_and(skipped)}. The source keeps {'it' if len(skipped) == 1 else 'them'} nowhere by name."
        )
    look_lines.append("Reading is free: Claude is not asked, nothing runs, and nothing is proposed by looking.")
    look_blocked = CLOSED_SENTENCE if closed else (LOOK_NOTHING_TO_ASK if not packages else None)

    running = bool(run and run.get("running"))
    running_ids = set(run["advisories"]) if running and run else set()
    last = None
    if look is not None:
        shown = [_row_view(r, running_ids, left_open) for r in rows]
        new = sum(1 for r in rows if r["state"] == "new")
        packed = sum(1 for r in rows if r["state"] in ("in_pack", "in_waiting_pack"))
        none = sum(1 for r in rows if r["state"] == "no_test")
        other = sum(1 for r in rows if r["state"] == "not_yours")
        n = len(rows)
        counts = [f"{new} {'is' if new == 1 else 'are'} new and can be tried here"] if new else []
        counts += [f"{none} {'has' if none == 1 else 'have'} no test yet"] if none else []
        counts += [f"{packed} {'is' if packed == 1 else 'are'} in a test pack already"] if packed else []
        counts += [f"{other} {'is' if other == 1 else 'are'} not about a version you have"] if other else []
        notes = []
        if look["left_out"]:
            notes.append(
                f"{look['left_out']} {'record was' if look['left_out'] == 1 else 'records were'} left out: not in the shape "
                "the source documents, about no version of these libraries, or taken back by the publisher."
            )
        more_pages = [
            f"{a.get('name')} ({a.get('ecosystem')})"
            for a in look.get("asked") or []
            if isinstance(a, dict) and a.get("more_pages")
        ]
        if more_pages:
            notes.append(
                f"The source had more pages of answers about {join_and(more_pages)} than this version reads (three). What the "
                "later pages hold was not read."
            )
        if look["cut"]:
            notes.append(
                "More advisories were read than this version lists at once (40). Those that name a version you have are listed "
                "first, then the newest of the others."
            )
        last = {
            "line": (
                f"Looked on {stamp(look['at'])} by {look['by']}: {n} published {'advisory' if n == 1 else 'advisories'} about your "
                f"libraries." + (f" {join_and(counts).capitalize()}." if counts else "")
            ),
            "source_line": (
                "Read from recorded answers in a folder on this computer. Nothing was sent."
                if look["source"] == "recorded"
                else f"Read from OSV (osv.dev). Sent: {join_and(list(look['sent']))}, and nothing else."
            ),
            "notes": notes,
            "rows": shown,
            "empty": None if shown else "The source has published nothing about these libraries.",
        }

    n = eligible
    research_lines = [
        f"For {'the new advisory' if n == 1 else f'each of the {n} new advisories'}: its published text is read, a test is designed from "
        "published test cases, and the test is tried on public copies in isolated mode.",
        "A test counts as proven only when it fails on the affected version, passes on the fixed version, and the control that must "
        "fail does.",
        (
            f"Live Otto is on: Claude is asked to read each advisory, to design its test and, for a test that was proven, to name the "
            f"publisher's fix. What is sent: the advisory's published text. The most this run can cost: {limit} US dollars."
            if live
            else "Live Otto is off: only answers recorded during the build are used. An advisory with no recorded answer stays open and "
            "reads “No recorded answer: this needs Live Otto.”"
        ),
        (
            "What the run settles is signed into a test pack made on this computer, and that pack is installed by this click"
            + (
                f", after the built-in test {'pack' if len(waiting_packs) == 1 else 'packs'} not installed yet ({join_and(waiting_packs)}), in order."
                if waiting_packs
                else "."
            )
            + " An advisory the run cannot settle (no answer, or a trial that does not finish) is left out of the pack and can be tried again."
        ),
        (
            "Test packs install in one order, and a pack made here becomes the newest. In this version a built-in test pack that is "
            "published after it can then not be installed in this data folder."
        ),
        "Each proven check then arrives on this page as a proposal. Accepting or rejecting it stays with you: nothing is added to a "
        "test plan, and nothing of yours is run.",
        "This can take several minutes for each advisory.",
    ]
    fetched = fetch_lines(rows) if sandbox else []
    research_lines[2:2] = fetched  # (after what counts as proven, before what Claude is asked)
    progress = None
    if run is not None:
        end = run.get("end")
        if running:
            line = f"A research run is going on, started on {stamp(run['started_at'])}."
        elif end is None or end.get("reason") == INTERRUPTED:
            first = list(run.get("installed_first") or [])
            line = INTERRUPTED + (
                f" Before it started, this click installed the built-in test {'pack' if len(first) == 1 else 'packs'} "
                f"{join_and(first)}."
                if first
                else ""
            )
        elif end.get("pack_version"):
            line = (
                f"The research run that started on {stamp(run['started_at'])} finished on {stamp(end['at'])}. Test pack "
                f"{end['pack_version']}, made on this computer, was installed."
            )
        else:
            line = (
                f"The research run that started on {stamp(run['started_at'])} ended on {stamp(end['at'])} without a test pack: "
                f"{end.get('reason') or RESEARCH_STOPPED}"
            )
        progress = {
            "line": line,
            "running": running,
            "title": "What the research run said",
            "lines": list(run.get("lines") or [])[-60:],
        }
    return {
        "title": TITLE,
        "intro": INTRO,
        "covers": COVERS + (" " + SANDBOX_COVERS if sandbox else ""),
        "sandbox_line": sandbox_line,
        "libraries_line": (
            "This assessment names: " + join_and([lib["label"] for lib in libraries]) + "."
            if libraries
            else "This assessment names no library the app knows."
        ),
        "look": {
            "label": LOOK_LABEL,
            "can": look_blocked is None,
            "blocked_reason": look_blocked,
            "dialog": {"title": "Look for new advisories?", "lines": look_lines, "confirm": "Look", "cancel": "Cancel"},
        },
        "last": last,
        "research": {
            "label": f"{RESEARCH_LABEL} ({n})" if n else RESEARCH_LABEL,
            "can": research_blocked is None,
            "blocked_reason": research_blocked if look is not None else None,
            "shown": look is not None,
            "dialog": {
                "title": (f"Design and prove {'a test for 1 advisory' if n == 1 else f'tests for {n} advisories'}?"),
                "lines": research_lines,
                "confirm": "Start",
                "cancel": "Cancel",
            },
            "progress": progress,
        },
        "busy": running,
    }
