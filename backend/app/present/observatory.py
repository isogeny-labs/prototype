"""The Observatory's own words (design refactor, section 5): the map of the systems as the files describe them.

Words only. The map draws no box, line, tie or word that the files or a check do not support, and it words no result:
every result word on it ("False", "Failed", "Classical", "No to all three") is taken as it stands from the page the
result lives on (app/observatory puts them in). What is written here is only what no page says yet: the names of the
places cryptography sits in a box, what the files say and do not say, and the labels of the lines. Never "secure",
never a score, nothing about how serious anything is.
"""

from __future__ import annotations

from app.names import ALGORITHM_NAMES, join_and

TITLE = "Observatory"
SUBLINE = (
    "Your systems as your files describe them, where the cryptography is, and what each check found there. "
    "The map fills in as checks run. Looking at it runs nothing."
)
MAP_TITLE = "Map"

# ---------------------------------------------------------------- nothing yet

EMPTY_TEXT = "No file has been brought in yet. The map is drawn from your scanner file, so bring one in on Import."
EMPTY_LINK_LABEL = "Open Import"
BANNER_STRONG = "Nothing has been checked yet."
BANNER_TEXT = (
    "This is what your scanner file says. Verify checks each claim on your live systems, and the map fills in as each "
    "check runs."
)
BANNER_LINK_LABEL = "Open Verify"

NOT_CHECKED = "Not checked yet"
NOT_MEASURED = "Not measured yet"
NOT_IN_FILE = "Not in your file"

# ---------------------------------------------------------------- what the map was built from

NO_COPY_NOTE = (
    "This file was brought in before the app kept a copy of each scanner file, so its structure can't be read again: "
    "the map is drawn from its claims alone, one box for each server and each signing program."
)
CSV_NOTE = (
    "A CSV scanner file lists claims and no structure, so the map is drawn from its claims alone: one box for each "
    "server and each signing program."
)
COPY_CHANGED_NOTE = (
    "The kept copy of this scanner file no longer matches its fingerprint, so it is not read: the map is drawn from "
    "the file's claims alone, one box for each server and each signing program."
)


def unreadable_note(reason: str) -> str:
    """The kept copy could not be read for the map. `reason` is the reader's own plain sentence."""
    return f"The map is drawn from the file's claims alone, because its structure could not be read. {reason}"


def built_from(files: list[str], checked: bool, at: str | None, changed: bool) -> list[dict]:
    """One line: the files the map was built from, and when it last changed (a time part: the screen writes it in the
    viewer's own time zone)."""
    parts: list[dict] = [{"t": "text", "v": "Built from "}]
    for n, name in enumerate(files):
        if n:
            parts.append({"t": "text", "v": " and " if n == len(files) - 1 and not checked else ", "})
        parts.append({"t": "mono", "v": name})
    if checked:
        parts.append(
            {"t": "text", "v": " and the checks of this assessment" if files else "the checks of this assessment"}
        )
    parts.append({"t": "text", "v": "."})
    if at:
        parts += [
            {"t": "text", "v": " Last changed " if changed else " Brought in "},
            {"t": "time", "v": at},
            {"t": "text", "v": "."},
        ]
    return parts


# ---------------------------------------------------------------- the four counts

COUNT_LINES = {
    "live": "on your systems",
    "lab": "on copies on this computer",
    "published": "said by a library's maker",
    "file": "only in your files: nothing observed or run yet",
}
COUNTS_NOTE = (
    "The same counts as the Overview's: every check of this assessment by what its result rests on, wherever it was "
    "started."
)

# ---------------------------------------------------------------- the boxes

THIS_COMPUTER = "This computer"
THIS_COMPUTER_SUB = "Evidence Lab · handshakes only"
THIS_COMPUTER_IDLE = "Evidence Lab · no handshake made yet"
CLIENTS = "Clients"
CLIENTS_SUB = "Outside your systems. Who connects is not in your files."

IN_SCANNER, IN_LIST, IN_BOTH = "in your scanner file", "in your dependency list", "in both files"
SERVICE_BOTH = "Named in both files, with the same name and version"
SERVICE_SCANNER = "Named in your scanner file"
SERVICE_LIST = "Named in your dependency list"
SERVICE_UNNAMED = "Your scanner file names no service: these are the systems its claims name"
LIST_UNNAMED = "Your dependency list does not say what it describes: these are the parts it names"

KIND_WORDS = {
    "server": "Server",
    "program": "Signing program",
    "key_exchange_program": "Key exchange program",
    "software": "Software",
    "service": "Service",
    "own_software": "Your software",
}
NO_ADDRESS = "no address in your scanner file"
NOTHING_HERE = "Nothing observed or run here."
NO_CRYPTOGRAPHY_NAMED = "Your scanner file names it, and no cryptography on it, so there is nothing to check here."


def not_drawn(n: int) -> str:
    """Software components of the scanner file that nothing puts on the map: counted, not drawn."""
    one = n == 1
    return (
        f"Your scanner file also names {n} software {'component' if one else 'components'} with no cryptography of "
        f"{'its' if one else 'their'} own and no service that names {'it' if one else 'them'}: "
        f"{'it is' if one else 'they are'} not drawn."
    )


def box_sub(kind: str, address: str | None, files: list[str]) -> str:
    """The line under a box's title: what it is, and which file names it."""
    words = KIND_WORDS.get(kind, "Part")
    if kind == "server":
        return f"{words} · {address}" + (f" · {IN_BOTH}" if len(files) > 1 else "")
    if kind == "service":
        return f"{words} · {NO_ADDRESS}"
    where = IN_BOTH if len(files) > 1 else IN_LIST if files == ["dependencies"] else IN_SCANNER
    return f"{words} · {where}"


def tie_words(top: str, source: str | None) -> str:
    """A top entry of the dependency list that is the same box as a system of the scanner file."""
    how = "by name and version" if source == "name_version" else "by you, with Part of on Dependencies"
    return f"In both files: {top} in your dependency list is tied to it {how}."


def join_or(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " or " + items[-1]


def not_tied(names: list[str]) -> str:
    """An untied top entry: built from the real names of the scanner file's servers and programs."""
    if not names:
        return "Not tied to a system: your scanner file names none."
    if len(names) > 3:
        return f"Not tied to any of the {len(names)} systems in your scanner file."
    first, rest = names[0], names[1:]
    return "Not tied to " + first + "".join(f" or to {n}" for n in rest) + "."


# ---------------------------------------------------------------- where the cryptography is

SPOT_TITLES = {
    "tls_versions": "TLS versions",
    "cipher_suites": "Cipher suites",
    "certificate": "Certificate",
    "key_exchange": "Key exchange",
    "signatures": "Signs",
    "signs": "Signs",
    "checks_signatures": "Checks signatures",
    "speed_size": "Speed and size",
    "other": "Other checks",
}
CLAIM_NAME = "The claim"
STATUS_NAME = "Post-quantum status"
# Which spot of a server a claim, a test or a track of its post-quantum status belongs to; the same for a program.
SERVER_CLAIM_SPOT = {
    "protocol_versions": "tls_versions",
    "cipher_suites": "cipher_suites",
    "certificate": "certificate",
    "key_exchange": "key_exchange",
    "post_quantum": "key_exchange",
    "signature_algorithm": "signatures",
}
SERVER_TEST_SPOT = {"tls_versions": "tls_versions", "certificate": "certificate", "pq_readiness": "key_exchange"}
SOFTWARE_CLAIM_SPOT = {"signature_algorithm": "signs", "key_exchange": "key_exchange"}
SOFTWARE_TEST_SPOT = {
    "official_vectors": "checks_signatures",
    "bad_signatures": "checks_signatures",
    "advisory_cases": "checks_signatures",
    "mldsa_vectors": "checks_signatures",
    "speed_size": "speed_size",
    "mldsa_compare": "speed_size",
    "mlkem_vectors": "key_exchange",
}
TRACK_SPOT = {"kex": "key_exchange", "auth": "certificate", "signatures": "signs"}
SERVER_SPOTS = ("tls_versions", "cipher_suites", "certificate", "key_exchange", "signatures", "other")
SOFTWARE_SPOTS = ("signs", "key_exchange", "checks_signatures", "speed_size", "other")
TRACK_WORDS = {"kex": "key exchange", "auth": "authentication", "signatures": "signatures"}


def claim_says(kind: str, claimed: str, detail: dict) -> str:
    """What one claim says, in the file's own terms ("TLS 1.3 only", "ECDSA P-256")."""
    if kind == "protocol_versions" and detail.get("versions"):
        return f"{join_and([str(v) for v in detail['versions']])} only"
    if kind in ("cipher_suites", "key_exchange") and (detail.get("suites") or detail.get("groups")):
        return f"only {claimed}"
    return claimed


def file_says(said: list[str]) -> str:
    return f"The file says {join_and(said)}" if said else NOT_IN_FILE


def claim_name(said: str, alone: bool) -> str:
    return CLAIM_NAME if alone else f"{CLAIM_NAME}: {said}"


def retest_label(component: str | None, own: str | None) -> str:
    """A retest's result beside the first one: labelled with the version it ran on, never put in its place. A server,
    or a program the retest did not move, was tested again as it is."""
    if component and component != own:
        return f"Retest on {component}"
    return "Retest, tested again as it is"


# ---------------------------------------------------------------- the cryptography lane

ALGORITHM_KIND = "Algorithm"
ALGORITHM_NAMED = "named in your scanner file"
LIBRARY_KIND, LIBRARIES_KIND = "Library", "Libraries"
LIBRARIES_FROM = "From your dependency list"
LIBRARIES_NO_ENTRY = "Libraries under no entry of your dependency list"
MORE_LINK_LABEL = "on Dependencies"
NO_LIST_TITLE = "Libraries"
NO_LIST_SUB = "Not brought in yet"
NO_LIST_TEXT = (
    "Add your dependency list on Migration plan, under Dependencies, to see your own software and the libraries "
    "inside it."
)


def plain_name(technical: str) -> str | None:
    """The plain name the app draws first for an algorithm ("Classical signatures" for "ECDSA P-256"), by the app's own
    pairs (names.ALGORITHM_NAMES; a whole word only, the longer names first), or None when it has none."""
    for known, plain in ALGORITHM_NAMES:
        at = technical.find(known)
        if at < 0:
            continue
        before = technical[at - 1] if at else " "
        after = technical[at + len(known)] if at + len(known) < len(technical) else " "
        if before.isalnum() or after.isalpha():
            continue
        return plain
    return None


def use_words(through: str, name: str, on_server: bool) -> str:
    """One place an algorithm is used, from the file's own references: "the certificate on localhost:8443"."""
    if through == "certificate":
        return f"the certificate on {name}" if on_server else f"a certificate of {name}"
    if through == "protocol":
        return f"TLS on {name}" if on_server else f"a protocol of {name}"
    if through == "key":
        return f"a key on {name}" if on_server else f"a key of {name}"
    if through == "signature":
        return f"the signatures of {name}"
    if through == "key_exchange":
        return f"the key exchange of {name}"
    return name


def used_in(places: list[str]) -> str:
    if not places:
        return "Your scanner file names it, and no system that uses it."
    return f"Used in {len(places)} {'place' if len(places) == 1 else 'places'}: {join_and(places)}."


USE_LABELS = {
    "certificate": "its certificate",
    "protocol": "its TLS",
    "key": "its key",
    "signature": "signs with",
    "key_exchange": "key exchange",
    "direct": "uses",
}
USES = "uses"
ASK_LABEL = "?"


def libraries_title(owner: str | None, n: int) -> str:
    return f"{owner}'s libraries · {n}" if owner else f"{LIBRARIES_NO_ENTRY} · {n}"


def libraries_line(n: int, via: str | None) -> str:
    """The label of the line from your own software to its library, or to its group of libraries."""
    if n == 1:
        return via if via and via != "direct" else USES
    return f"uses {n} libraries"


def more_libraries(n: int) -> str:
    return f"{n} more"


def live_label(accepted: list[str] | None) -> str:
    """What the app saw on the connections it made to a server ("TLS · 1.3 and 1.2 accepted"), from the recorded
    handshakes. `accepted`: the TLS versions the newest record shows as accepted, newest first; None when no record
    lists them."""
    if accepted is None:
        return "Handshakes only"
    if not accepted:
        return "TLS · no version accepted"
    return f"TLS · {join_and([v.replace('TLS ', '') for v in accepted])} accepted"


LEGEND = [
    {"kind": "uses", "text": "Your files say one uses the other"},
    {"kind": "live", "text": "A connection we made from this computer (handshakes only)"},
    {"kind": "ask", "text": "Your files don't say"},
    {"kind": "unobserved", "text": "Nothing observed or run here yet"},
]
LEGEND_NOTE = "Chips are the checks' own words"

# ---------------------------------------------------------------- what the files don't say

GAPS_TITLE = "What your files don't say"
GAPS_NOTE = "The map draws no line it can't show from your files or a check."
BOX_GAPS_TITLE = "What your files don't say about it"
DEPENDENCIES_LABEL = "Dependencies"
IMPORT_LABEL = "Import"


def _addresses(addresses: list[str]) -> str:
    return join_and(addresses) if len(addresses) <= 4 else f"{len(addresses)} server addresses"


def gap_software(addresses: list[str], untied: list[str], listed: bool) -> str:
    """Which software answers on a server's address. Every untied top entry of the dependency list is named, none is
    picked."""
    head = f"Which software answers on {_addresses(addresses)}."
    one = len(addresses) == 1
    if untied:
        n = len(untied)
        return (
            f"{head} Your dependency list names {n} {'part that is' if n == 1 else 'parts that are'} not tied to a system "
            f"of your scanner file: {join_and(untied)}. The map does not guess which, if any, runs "
            f"{'it' if one else 'them'}. If one does, tie it on Dependencies (Part of)."
        )
    if listed:
        return (
            f"{head} No part of your dependency list is tied to {'it' if one else 'them'}. If one runs "
            f"{'it' if one else 'one of them'}, tie it on Dependencies (Part of)."
        )
    return (
        f"{head} Your scanner file names no software for {'it' if one else 'them'}. A dependency list can: add one on "
        "Dependencies, then tie the part that runs it (Part of)."
    )


def gap_clients(addresses: list[str]) -> str:
    return (
        f"Who connects to {_addresses(addresses)}. Your files name the "
        f"{'server' if len(addresses) == 1 else 'servers'}, not {'its' if len(addresses) == 1 else 'their'} clients, so "
        "the map draws a question mark and no line."
    )


GAP_DATA_FLOWS = (
    "Which data flows between the parts. A scanner file can name data flows, but this version does not read them, so "
    "the map draws none."
)
GAP_NO_SERVICE = (
    "What these parts belong to. Your scanner file does not name the service or product it describes, so the map "
    "draws no box around them."
)
GAP_NO_LIST = (
    "Which of your own software and which libraries are inside. No dependency list has been added: add one on "
    "Dependencies."
)


def gap_unplaced(said: list[str]) -> str:
    n = len(said)
    return (
        f"Where {n} {'claim applies' if n == 1 else 'claims apply'}. Your scanner file does not say which system uses "
        f"{join_and(said[:4])}{' and others' if n > 4 else ''}, so {'it is' if n == 1 else 'they are'} on no box. "
        "Import lists every claim."
    )


def gap_part_of(names: list[str]) -> str:
    """For an untied top entry's own panel."""
    if not names:
        return "Which system it is part of. Your scanner file names none."
    return (
        f"Which system of your scanner file it is part of, if any ({join_or(names[:4])}"
        f"{' or another' if len(names) > 4 else ''}). If it runs one of them, tie it on Dependencies (Part of)."
    )


def gap_libraries(listed: bool) -> str:
    """For a signing program's own panel, when no top entry of a dependency list is tied to it."""
    if listed:
        return (
            "Which libraries it uses. No part of your dependency list is tied to it: if one is this program, tie it on "
            "Dependencies (Part of)."
        )
    return "Which libraries it uses. No dependency list has been added: add one on Dependencies."


GAP_WHERE_IT_RUNS = "Which of your systems run it. Your files name the program, not where it is installed."
GAP_NO_LIBRARIES_LISTED = "Which libraries it uses. Your dependency list names it, and lists no libraries under it."


def gap_clients_of(address: str) -> str:
    return f"Who connects to {address}. Your files name the server, not its clients."


# ---------------------------------------------------------------- a box's panel


def _tally(words: list[str]) -> str:
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return ", ".join(f"{n} {w}" for w, n in counts.items())


def summary(
    claims: list[str], tests: list[str], statuses: list[tuple[str, str]], retests: dict[str, list[str]], server: bool
) -> str:
    """One sentence for a box's panel, built only from counts of the checks' own words: "2 claims: 1 False, 1 True.
    2 server tests: 1 Failed, 1 Passed. Post-quantum status: Classical." `statuses`: (track words, the status word)."""
    parts = []
    if claims:
        n = len(claims)
        parts.append(f"{n} {'claim' if n == 1 else 'claims'}: {_tally(claims)}.")
    if tests:
        n = len(tests)
        kind = "server test" if server else "test"
        parts.append(f"{n} {kind if n == 1 else kind + 's'}: {_tally(tests)}.")
    for label, words in retests.items():
        parts.append(f"{label}: {_tally(words)}.")
    if statuses:
        said = list(dict.fromkeys(word for _, word in statuses))
        if len(said) == 1:
            parts.append(f"{STATUS_NAME}: {said[0]}.")
        else:
            parts.append(f"{STATUS_NAME}: " + ", ".join(f"{track} {word}" for track, word in statuses) + ".")
    return " ".join(parts) or NOTHING_HERE


LAST_WORDS = {"live": "Last observed", "lab": "Last run", "published": "Last read", "file": "Brought in"}
PANEL_KIND = "System · Observatory"
FILE_LINES_SCANNER = "In your scanner file"
FILE_LINES_LIST = "In your dependency list"
CLAIMS_LINES = "The claims that name it"
LIBRARIES_TITLE = "Its libraries, from your dependency list"
LINK_CLAIM = "The claim on Verify"
LINK_CLAIM_IMPORT = "The claim on Import"
LINK_EVIDENCE = "The result on Evidence"
LINK_TEST = "The test on Checks"
LINK_SYSTEM = "The system on Migration plan"
LINK_FIX = "The fix on Fixes"
LINK_LIBRARY = "The library on Dependencies"

# ---------------------------------------------------------------- from a result back to the map

PLACE_LABEL = "On your map"
PLACE_LINK_LABEL = "Show on the map"


def dependency_line(label: str, kind: str | None) -> str:
    return f"{label} ({kind})" if kind else label


def depends_on_line(label: str, n: int) -> str:
    return f"{label} depends on {n} {'component' if n == 1 else 'components'}"
