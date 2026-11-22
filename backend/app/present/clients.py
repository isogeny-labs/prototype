"""Who can still connect (phase 4e, first half): the words of the client stand-ins' table in a try, and of its result on
Checks and in Evidence.

Words only. Each stand-in's word (Connects, Falls back, Breaks, Didn't connect before either, Couldn't check) is the
separate reviewer's (engine/reviewer.py, client_reach_review). It is information: the try is decided by the system's own
measurement, and a Breaks holds nothing off. No severity, no score: the table says what happened to each stand-in.
"""

from __future__ import annotations

from app.clients import profiles

TITLE = "Who can still connect"
WORDS = {
    "connects": "Connects",
    "falls_back": "Falls back",
    "breaks": "Breaks",
    "not_before": "Didn't connect before either",
    "couldnt_check": "Couldn't check",
}
TONES = {
    "connects": "pass",
    "falls_back": "neutral",
    "breaks": "fail",
    "not_before": "neutral",
    "couldnt_check": "warn",
}
COLUMNS = ["Client stand-in (Demo data)", "Today", "On the test copy", "Result"]
ALERTS = {40: "handshake failure", 70: "protocol version", 71: "insufficient security"}
KIND_WORDS = {"hybrid": "hybrid", "post_quantum": "ML-KEM by itself", "classical": "classical"}
DECIDES_NOTHING = (
    "This is information. Whether the try passed is decided by the system's own measurement above, and Apply is "
    "not held off by it: you decide."
)
CONTROL_TEXT = (
    "Control: the same stand-ins on our own hybrid and classical test servers, started for this run, read as they must."
)
SHOWS = [
    "It shows how four demo client stand-ins, each offering exactly what its profile says, connect to the server as it is "
    "today and to a test copy with the change.",
    "It doesn't show how your own clients connect: the stand-ins are our own OpenSSL, not your devices, and a network device "
    "between a client and the server (a proxy) is not tried.",
]


def _n(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def summary(counts: dict, brings_post_quantum: bool) -> str:
    """ "1 breaks, 2 connect, 1 didn't connect before either." or "None break. 1 connects with hybrid ...; 2 fall back ...".
    "None break." only when every stand-in has a clear word: a stand-in that couldn't be checked is not one that
    doesn't break ("2 connect; 2 couldn't be checked.")."""
    rest = []
    if counts.get("connects"):
        rest.append(
            _n(counts["connects"], "connects", "connect")
            + (" with hybrid or post-quantum key exchange" if brings_post_quantum else "")
        )
    if counts.get("falls_back"):
        rest.append(_n(counts["falls_back"], "falls back", "fall back") + " to classical key exchange")
    if counts.get("not_before"):
        rest.append(f"{counts['not_before']} didn't connect before either")
    if counts.get("couldnt_check"):
        rest.append(_n(counts["couldnt_check"], "couldn't be checked", "couldn't be checked"))
    if counts.get("breaks"):
        return ", ".join([_n(counts["breaks"], "breaks", "break"), *rest]) + "."
    joined = "; ".join(rest)
    if counts.get("couldnt_check"):
        return f"{joined[0].upper()}{joined[1:]}."
    return "None break." + (f" {joined[0].upper()}{joined[1:]}." if joined else "")


def warning(counts: dict) -> str | None:
    n = counts.get("breaks") or 0
    if not n:
        return None
    return f"Sort out the {n} that {'breaks' if n == 1 else 'break'} before you apply this change."


def handshake_words(side: dict, reached: bool = True, problem: str | None = None) -> str:
    if not reached:
        return f"Not reached: {problem}" if problem else "Not reached"
    kind = side.get("kind")
    if kind in KIND_WORDS:
        group = f" ({side['group']})" if side.get("group") else ""
        return f"{side.get('tls_version') or 'TLS'}, {KIND_WORDS[kind]}{group}"
    if kind == "refused":
        code = side.get("alert")
        alert = ALERTS.get(code) if isinstance(code, int) else None
        return f"Refused ({alert})" if alert else "Refused"
    return "No clear answer"


def _names(spec: dict) -> dict:
    return {s["id"]: s for s in (spec.get("inputs") or {}).get("stand_ins") or []}


def rows(spec: dict, detail: dict) -> list[dict]:
    named = _names(spec)
    reached, problem = bool(detail.get("today_reached")), detail.get("today_problem")
    out = []
    for r in detail.get("stand_ins") or []:
        s = named.get(r["id"], {"name": r["id"], "offers": ""})
        out.append(
            {
                "id": r["id"],
                "name": s["name"],
                "offers": s.get("offers") or "",
                "label": profiles.DEMO_LABEL,
                "today": handshake_words(r["today"], reached, problem),
                "on_copy": handshake_words(r["copy"]),
                "word": WORDS[r["word"]],
                "word_key": r["word"],
                "tone": TONES[r["word"]],
                "note": "New: it can't connect today." if r.get("new") else None,
            }
        )
    return out


def try_block(clients: dict | None) -> dict | None:
    """The table in a try's result, or None for a try made before this check existed."""
    if not clients:
        return None
    base = {
        "title": TITLE,
        "running": None,
        "summary": None,
        "warning": None,
        "columns": COLUMNS,
        "rows": [],
        "note": profiles.STAND_IN_NOTE,
        "decides": DECIDES_NOTHING,
        "control": None,
        "no_answer": None,
    }
    if clients.get("running"):
        return {
            **base,
            "running": {
                "status": "running",
                "status_text": "Running",
                "progress": {"text": "connecting the client stand-ins", "percent": None},
            },
        }
    measured = clients.get("run") or {}
    result = measured.get("result") or {}
    if measured.get("code") != "measured":
        return {
            **base,
            "no_answer": f"No answer from the client stand-ins: {result.get('summary') or result.get('label') or 'the run gave no result'}",
        }
    detail = measured.get("detail") or {}
    counts = detail.get("counts") or {}
    return {
        **base,
        "summary": summary(counts, bool(detail.get("brings_post_quantum"))),
        "warning": warning(counts),
        "rows": rows(clients.get("spec") or {}, detail),
        "control": CONTROL_TEXT,
    }


# ---------------------------------------------------------------- the result on Checks and in Evidence


def client_reach(w, spec: dict, run: dict, review: dict, ctx: dict) -> None:
    """The words of one reviewed "Who can still connect" run (present/results.py's filler for its kind)."""
    detail = review.get("detail") or {}
    counts = detail.get("counts") or {}
    said = summary(counts, bool(detail.get("brings_post_quantum")))
    table = rows(spec, detail)
    breaking = [r["name"] for r in table if r["word_key"] == "breaks"]
    address = spec["target"]["address"]
    w.plain = (
        f"On a test copy of {address} with the change, of the four demo client stand-ins: {said[0].lower() + said[1:]}"
        + (f" Breaks: {', '.join(breaking)}." if breaking else "")
        + " "
        + DECIDES_NOTHING.split(". ")[0]
        + "."
    )
    w.summary = said
    w.short = said
    w.what = [
        f"{r['name']}: today {r['today'][0].lower() + r['today'][1:]}; on the test copy {r['on_copy'][0].lower() + r['on_copy'][1:]}. "
        f"{r['word']}." + (f" {r['note']}" if r["note"] else "")
        for r in table
    ]
    w.shows = list(SHOWS)
    w.evidence = [
        {
            "type": "table",
            "title": TITLE,
            "tag": "measured on the copy",
            "columns": [{"label": c, "align": "left"} for c in COLUMNS],
            "rows": [[r["name"], r["today"], r["on_copy"], r["word"]] for r in table],
            "meta": [],
            "note": profiles.STAND_IN_NOTE,
        }
    ]
    raw: dict = run["raw"] if isinstance(run.get("raw"), dict) else {}
    evidence = (raw.get("subject") or {}).get("evidence") or []
    text = "\n\n".join(
        f"{e.get('title', '')}\n$ {e.get('command', '')}\n{e.get('output', '')}".strip()
        for e in evidence
        if isinstance(e, dict)
    )
    if text:
        w.evidence.append({"type": "text", "title": "The handshakes", "tag": "measured", "text": text})
    w.command = "One full TLS handshake per stand-in, today and on the test copy, by the OpenSSL inside the cryptography library"
    w.outputs = [{"title": "Each stand-in, as reviewed", "text": "\n".join(w.what)}]
    w.control_text = CONTROL_TEXT
    w.fix = None


__all__ = ["try_block", "client_reach", "summary", "warning", "WORDS", "TITLE"]
