"""Where it is used (change impact, phase 4e, first half): the words of the block on a fix and on a library.

Words only. The places come from impact/reach.py, which reads the scanner files, the dependency lists and the
knowledge base. Nothing here decides a result, rates anything or says how serious anything is: it says where a part
is used, how that was matched, and what the app does not know.
"""

from __future__ import annotations

FROM_FILE = "from your file"
HOW_WORDS = {
    "address": "the same address",
    "package": "the same package address and version",
    "knowledge_base": "the knowledge base recognises it as {library}, at the same version",
    "name_version": "the same name and version",
}
AS_WORDS = {
    "server": "as a server",
    "signing program": "as a signing program",
    "key exchange program": "as a key exchange program",
    "dependency list": "in its dependency list",
}
TIE_WORDS = {"user": "set by you", "name_version": "tied by name and version"}
ENVIRONMENT_NOTE = (
    "A dependency list says what is installed, not what a program really loads: that needs your environment."
)
NO_LIST_NOTE = (
    "This assessment has no dependency list, so only its scanner file was read. Add one on Migration, under "
    "Dependencies, to see your own software that uses it."
)
CLOSED_NOTE = (
    "This assessment is closed, so other assessments are not read: only its own scanner file and dependency list are."
)
APPLY_NOTE = "Apply changes this one server for every assessment that names it."
COMPATIBLE_UNKNOWN = (
    "Not known. Your dependency list names the exact version installed, not the versions each part that uses it "
    "accepts."
)
COMPATIBLE_UNKNOWN_NO_LIST = (
    "Not known. The app holds no record of which versions the parts that use it accept: a dependency list "
    "names exact versions only."
)
CONNECT_SEE_TRY = (
    "This change alters what the server offers on the network. Try on a test copy, in the change box below, also "
    "connects four demo client stand-ins and shows who can still connect."
)
CONNECT_NO_SETTING = "This option changes no setting on the server here, so there is no client check."
CONNECT_NO_TRY = (
    "This change alters what the server offers on the network, but it can't be tried on a test copy here (the change "
    "box says why), so who can still connect can't be shown."
)
CONNECT_TEXT_ONLY = (
    "This change alters what the server offers on the network, but this app has no test copy of it to try, so who "
    "can still connect can't be shown."
)
CONNECT_SIGNING = (
    "Not in this version: the machines that check this program's signatures would have to check the new ones, and "
    "they can't be tried here."
)
CONNECT_PROGRAM = (
    "No client check: this fix changes {what}, not what a server offers on the network. A retest reruns every "
    "locked test on the new version."
)
CONNECT_TLS_LIBRARY = (
    "This updates a TLS library, which can change what a server that uses it offers on the network. This app can't "
    "try that on your server. After the update, press Measure again on Migration; a server's change there shows "
    "who can still connect."
)


def _how(entry: dict, library: str | None) -> str:
    return HOW_WORDS.get(entry.get("how") or "", "").format(library=library or "the same library")


def _tie_words(tie: dict) -> str:
    system = tie.get("system")
    if system is None:
        return (
            "Not tied to a system of your file: choose one with Part of on Dependencies."
            if tie.get("shown", True)
            else "Not tied to a system of your file."
        )
    return f"Part of {system['name']} ({TIE_WORDS.get(tie.get('source') or '', 'set by you')})."


def _system_link(system: dict | None) -> dict | None:
    return {"page": "migration/systems", "item": system["key"]} if system else None


def _here_line(entry: dict, library: str | None) -> dict:
    kind = entry["kind"]
    if kind == "file":
        what = {
            "server": "A server",
            "signing program": "A signing program",
            "key exchange program": "A key exchange program",
        }[entry["as"]]
        text = entry.get("label") or (entry["system"] or {}).get("name") or ""
        sub = f"{what} in your scanner file"
        if entry.get("how") == "knowledge_base":
            sub += f" ({_how(entry, library)})"
        return {
            "text": text,
            "sub": sub + ".",
            "tag": FROM_FILE,
            "link": _system_link(entry.get("system")),
            "chip": None,
        }
    if kind == "part_of":
        return {
            "text": entry["label"],
            "sub": f"From your dependency list: your own software. {_tie_words(entry['tie'])}",
            "tag": FROM_FILE,
            "link": _system_link(entry["tie"].get("system")) or {"page": "migration/dependencies", "item": None},
            "chip": None,
        }
    if kind == "top":
        what = (
            "the thing your dependency list describes"
            if entry.get("described")
            else "a top entry of your dependency list (your own software)"
        )
        return {
            "text": entry["label"],
            "sub": f"Also {what}, matched by {_how(entry, library)}. {_tie_words(entry['tie'])}",
            "tag": FROM_FILE,
            "link": _system_link(entry["tie"].get("system")) or {"page": "migration/dependencies", "item": None},
            "chip": None,
        }
    if kind == "row":
        return {
            "text": entry["label"],
            "sub": f"In your dependency list, matched by {_how(entry, library)}.",
            "tag": FROM_FILE,
            "link": {"page": "migration/dependencies", "item": entry.get("row")},
            "chip": None,
        }
    # kind == "user": a top entry that reaches it
    via = entry.get("via") or []
    how = "Uses it directly." if not via else f"Uses it, through {', then '.join(via)}."
    who = (
        "The thing your dependency list describes. "
        if entry.get("described")
        else "Your own software, from your dependency list. "
    )
    return {
        "text": entry["label"],
        "sub": f"{who}{how} {_tie_words(entry['tie'])}",
        "tag": FROM_FILE,
        "link": _system_link(entry["tie"].get("system")) or {"page": "migration/dependencies", "item": None},
        "chip": None,
    }


def _elsewhere_line(entry: dict, library: str | None) -> dict:
    a = entry["assessment"]
    more = entry.get("more") or 0
    tail = "" if not more else f" And {more} more {'assessment' if more == 1 else 'assessments'} in this project."
    return {
        "text": f"{entry['project']['name']} › {a['title']}",
        "sub": f"Names {entry['label']} {AS_WORDS.get(entry['as'], '')} ({_how(entry, library)}).{tail}",
        "tag": FROM_FILE,
        "chip": "Closed" if a["closed"] else "Open",
        "link": {**entry["link"], "assessment_id": a["id"]},
    }


def count_line(count: int, on_fix: bool) -> str:
    when = "after the change" if on_fix else "if you change it"
    if count == 0:
        return (
            "No system of yours to re-check was found."
            if on_fix
            else "No system of yours to re-check was found, if you change it."
        )
    if count == 1:
        return f"Re-check this one {when}."
    return f"Re-check these {count} {when}."


def block(
    facts: dict,
    *,
    on_fix: bool,
    library_label: str | None = None,
    compatible_for: str | None = None,
    connect: str | None = None,
    apply_note: bool = False,
) -> dict:
    """The block as the screen shows it. `compatible_for`: the new version, for the line on whether the parts that use
    it take it (None: the line is not shown, because no version changes). `connect`: the "Who can still connect" line
    (None: not shown)."""
    library = library_label or facts["part"].get("library")
    here = [_here_line(e, library) for e in facts["here"]]
    elsewhere = [_elsewhere_line(e, library) for e in facts["elsewhere"]]
    notes = []
    if apply_note:
        notes.append(APPLY_NOTE)
    if (
        facts["part"]["kind"] == "software"
        and facts["listed"]
        and any(e["kind"] in ("row", "top", "user") for e in facts["here"])
    ):
        notes.append(ENVIRONMENT_NOTE)
    if not facts["listed"]:
        notes.append(NO_LIST_NOTE)
    compatible = None
    if compatible_for is not None:
        compatible = {
            "title": f"Can the parts that use it take {compatible_for}?",
            "text": COMPATIBLE_UNKNOWN if facts["listed"] else COMPATIBLE_UNKNOWN_NO_LIST,
        }
    return {
        "title": "What this change touches" if on_fix else "Where it is used",
        "part": facts["part"]["label"],
        "count": facts["count"],
        "count_line": count_line(facts["count"], on_fix),
        "here": {
            "title": "In this assessment",
            "lines": here,
            "none": None if here else "Nothing in this assessment's scanner file or dependency list names it.",
        },
        "elsewhere": {
            "title": "Elsewhere in your organization",
            "lines": elsewhere,
            "none": None
            if elsewhere
            else (CLOSED_NOTE if facts["closed"] else "No other assessment in your organization names it."),
        },
        "notes": notes,
        "compatible": compatible,
        "connect": {"title": "Who can still connect", "text": connect} if connect else None,
    }


def connect_line(part: dict, *, change: dict | None, signing_change: bool = False, what: str = "a program") -> str:
    """Which "Who can still connect" sentence a fix carries (docs/SPEC.md, the table of changes and checks)."""
    if change is not None:
        if not change.get("settings_after"):
            return CONNECT_NO_SETTING
        return CONNECT_SEE_TRY if change.get("target") else CONNECT_NO_TRY
    if signing_change:
        return CONNECT_SIGNING
    if part.get("kind") == "software" and "tls" in (part.get("roles") or []):
        return CONNECT_TLS_LIBRARY
    return CONNECT_PROGRAM.format(what=what)
