"""Every word of the Dependencies view (phase 4d), and of its Fixes entries and evidence part. Decides nothing: the
answers come from the knowledge base (lookups) and from the reviewer (measurements), already worked out.

Wording rules (tested): every answer carries one label and its reason; a lookup is never called a pass or measured;
no "secure", no score."""
from __future__ import annotations

from app.knowledge.versions import read_version

QUESTIONS = (
    ("ml_kem_768", "ML-KEM-768 key exchange", "Key exchange"),
    ("x25519mlkem768", "X25519MLKEM768 hybrid TLS", "Hybrid TLS"),
    ("ml_dsa_65", "ML-DSA-65 signatures", "Signatures"),
)
QUESTION_WORDS = {k: w for k, w, _ in QUESTIONS}
LABEL_WORDS = {"release_notes": "Release notes say", "public_copy": "Measured on a public copy",
               "your_environment": "Measured in your environment"}
ANSWER_WORDS = {"yes": "Yes", "no": "No", "doesnt_apply": "Doesn't apply", "not_in_knowledge_base": "Not in our knowledge base yet",
                "couldnt_tell_version": "Couldn't tell the version", "needs_your_environment": "Needs your environment"}
TONES = {"yes": "pass", "no": "fail"}
STATE_WORDS = {"measured": "Measured", "not_measured": "Not measured yet", "couldnt_check": "Couldn't check",
               "couldnt_trust": "Couldn't trust this run", "not_offered": "Not measured here"}
TRACK_WORDS = {"kex": "key exchange", "auth": "authentication", "signatures": "signatures"}
KIND_LABELS = {"server": "Server", "software": "Signing program"}
DISCLAIMER = "Passing these tests doesn't prove a system secure. It shows these specific checks passed."
ENVIRONMENT_LINE = ("Whether this system really loads these libraries is what your file says, not something we measured: "
                    "that Needs your environment.")


def described_label(parsed: dict) -> str | None:
    key = parsed.get("described")
    comp = next((c for c in parsed.get("components", []) if c.get("key") == key), None) if key else None
    if not comp:
        return None
    return f"{comp['name']} {comp['version']}".strip() if comp.get("version") else comp["name"]


def first_version_words(question: str, version: str | None, library: str | None) -> str | None:
    if version is None:
        return None
    if version == "none_known":
        return f"No version of {library or 'this library'} is known to do this."
    return f"{version} or later can."


def _cell(row: dict, q: str) -> dict:
    a = row["answers"][q]
    lookup = a["lookup"]
    if a["answer"] in ("yes", "no"):
        reason = (f"{a['library_says']}" if a["state"] == "measured" and a["answer"] == "no" and a["library_says"]
                  else MADE_WORDS[q] if a["state"] == "measured"
                  else lookup["reason"])
        if a["state"] == "measured" and a["answer"] == "no":
            reason = f"The library itself said no: {reason}" if a["library_says"] else "The library itself said no."
    else:
        reason = lookup["reason"]
    agreement = None
    if a["agreement"] == "agrees":
        agreement = "The release notes say the same."
    elif a["agreement"] == "differs":
        agreement = (f"The release notes say {ANSWER_WORDS[lookup['answer']].lower()}; the measurement says "
                     f"{ANSWER_WORDS[a['measured']].lower()}. The measurement counts.")
    return {"question": q, "answer": a["answer"], "answer_words": ANSWER_WORDS[a["answer"]], "tone": TONES.get(a["answer"], "neutral") if a["state"] == "measured" else "neutral",   # a lookup is never a pass
            "label": a["label"], "label_words": LABEL_WORDS.get(a["label"] or "", None), "reason": reason,
            "first_version": a["first_version"],
            "first_version_words": first_version_words(q, a["first_version"], row["library_label"] or row["name"]) if a["answer"] == "no" else None,
            "state": a["state"], "state_words": STATE_WORDS[a["state"]] + (f" ({a['state_reason']})" if a["state_reason"] and a["state"] != "not_offered" else ""),
            "agreement": a["agreement"], "agreement_words": agreement}


SHORT_QUESTIONS = {"ml_kem_768": "Key exchange", "x25519mlkem768": "Hybrid", "ml_dsa_65": "Signatures"}
NUMBER_WORDS = {2: "both", 3: "all three"}


def version_words(version: str | None) -> str | None:
    """The version as the lookup reads it (a distribution's package as its upstream version: "3.0.22-1~deb12u2" is 3.0.22)."""
    read = read_version(version)
    if read is None:
        return version
    numbers, letter = read
    return ".".join(str(n) for n in numbers) + letter


def no_reason(row: dict, cell: dict) -> str | None:
    """Phase 5b: under every No, the reason in one line, from the first version the knowledge base names and the version in
    the file ("OpenSSL added this in 3.5.0; you have 3.0.22."), or the library's own words when it was measured."""
    if cell["answer"] != "no":
        return None
    if cell["state"] == "measured":
        return cell["reason"]
    library = row.get("library_label") or row.get("name") or "This library"
    first = cell.get("first_version")
    have = version_words(row.get("version"))
    if first == "none_known":
        return f"No version of {library} is known to do this; you have {have}." if have else f"No version of {library} is known to do this."
    if first and have:
        return f"{library} added this in {first}; you have {have}."
    return cell["reason"]


def answers_short(cells: list[dict]) -> str:
    """Phase 5b: a row's answers in a few words, for the compact table ("No to all three", "Key exchange: No · Signatures:
    Yes"). Only the answers already worded for the row are used."""
    asked = [c for c in cells if c["answer"] != "doesnt_apply"]
    if not asked:
        return "Doesn't apply"
    words = {c["answer_words"] for c in asked}
    if len(words) == 1 and len(asked) > 1:
        return f"{asked[0]['answer_words']} to {NUMBER_WORDS.get(len(asked), f'all {len(asked)}')}"
    if len(asked) == 1:
        return asked[0]["answer_words"]
    return " · ".join(f"{SHORT_QUESTIONS.get(c['question'], c['question'])}: {c['answer_words']}" for c in asked)


def _without_answer_words(n: int) -> str | None:
    if not n:
        return None
    return ("1 of its libraries has no answer yet: a thing to check, not a blocker." if n == 1 else
            f"{n} of its libraries have no answer yet: things to check, not blockers.")


MADE_WORDS = {"ml_kem_768": "Our pinned copy did one key exchange, and the reference library got the same shared secret.",
              "x25519mlkem768": "Our pinned copy completed a handshake with the app's test server, which accepts only X25519MLKEM768.",
              "ml_dsa_65": "Our pinned copy made a signature, and the reference library checked it."}


def _lookup_evidence(row: dict) -> list[dict]:
    out, seen = [], set()
    for q, words, _ in QUESTIONS:
        src = row["answers"][q]["lookup"].get("source")
        if not src:
            continue
        key = (src["url"], src["quote"])
        out.append({"question": q, "question_words": words, "title": src["title"], "url": src["url"], "quote": src["quote"],
                    "checked": src["checked"], "repeat": key in seen})
        seen.add(key)
    return out


def _via_words(row: dict) -> str:
    if not row["via"]:
        return "direct"
    return "through " + ", then ".join(row["via"])


def _row(row: dict, state: dict, busy: bool, isolated: bool) -> dict:
    blocks = []
    for system in state["systems"].values():
        for track, blockers in system["blockers"].items():
            if any(b["row"] == row["id"] for b in blockers):
                blocks.append({"system": system["name"], "track": track, "track_words": TRACK_WORDS[track],
                               "fix_id": next(b["fix_id"] for b in blockers if b["row"] == row["id"]),
                               # phase 5b: the Blocks marker on the row, and which system it opens
                               "system_key": system.get("key"), "words": f"Blocks {system['name']} · {TRACK_WORDS[track]}"})
    m = row["measurement"]
    running = bool(m and m.get("job"))
    if not row["measurable"]:
        measure = {"label": "Measure on a public copy", "enabled": False, "blocked_reason": "Not on the approved pinned list.", "busy": False}
    elif not isolated:
        measure = {"label": "Measure on a public copy", "enabled": False, "blocked_reason": "Measuring needs isolated mode (Docker).", "busy": False}
    else:
        measure = {"label": "Measure again on a public copy" if (m or {}).get("code") else "Measure on a public copy",
                   "enabled": not running, "blocked_reason": "This library is being measured." if running else None, "busy": running}
    same = row.get("same_copy_as_control")
    note = (f"This copy is also the {'capable' if same == 'capable' else 'incapable'} control of every check, so only the other control "
            "is an independent check here.") if same else None
    measurement = None
    if m and m.get("code"):
        measurement = {"copy_label": row["copy_label"], "code": m["code"], "run_id": m["run_id"], "finished_at": m.get("finished_at"),
                       "result": m.get("result"), "controls": m.get("control"), "controls_words": ("Both control copies answered as they must." if m.get("control") == "as_expected"
                                                                        else "A control copy did not answer as it must, so this run can't be trusted.")}
    cells = [_cell(row, q) for q, _, _ in QUESTIONS]
    for c in cells:
        c["no_reason"] = no_reason(row, c)
    return {"id": row["id"], "label": row["label"], "via_words": _via_words(row), "library": row["library_label"],
            "cells": cells, "answers_short": answers_short(cells), "blocks": blocks, "measure": measure,
            "same_copy_note": note, "lookups": _lookup_evidence(row), "measurement": measurement,
            "job": (m or {}).get("job") if running else None}


def _otto_row(entry: dict | None) -> dict:
    """Phase 5c: what a library's row carries about Otto. `advisories`: one line for each published advisory that names
    it ("Named by advisory X: measured affected / not affected / not yet checked"). `otto_proposals`: Otto's proposals
    to change its status, each with its buttons. `otto_status`: the status a person accepted."""
    entry = entry or {}
    return {"advisories": entry.get("advisories") or [], "otto_proposals": entry.get("proposals") or [], "otto_status": entry.get("status")}


def view(*, plan_id: int, import_id: int, is_demo: bool, state: dict | None, busy: bool, isolated: bool, otto: dict | None = None,
         impact: dict | None = None) -> dict:
    base = {"plan_id": plan_id, "import_id": import_id, "is_demo": is_demo, "title": "Dependencies", "disclaimer": DISCLAIMER,
            "busy": busy, "questions": [{"key": k, "title": w, "short": s} for k, w, s in QUESTIONS],
            "legend": [{"key": k, "words": w} for k, w in LABEL_WORDS.items() if k != "your_environment"],
            "upload": {"label": "Add dependency list",
                       "note": "A CycloneDX (1.5 or 1.6) or SPDX (2.3) JSON file from your scanner, for example Syft or Trivy. "
                               "It is data: nothing in it is run, and nothing connects to your systems."}}
    if state is None:
        return {**base, "subline": "Add the list of what your software depends on to see which libraries can do post-quantum "
                                   "key exchange and signatures.",
                "list_file": None, "measure_all": None, "systems": [], "groups": [], "empty_text": "No dependency list added yet."}
    any_measurable = any(r["measurable"] for r in state["rows"])
    measure_all = {"label": "Measure all", "enabled": isolated and any_measurable and not busy,
                   "blocked_reason": None if isolated and any_measurable and not busy else
                   ("Measuring needs isolated mode (Docker). Lookups work as they are." if not isolated else
                    "A measurement is running." if busy else "No library in this list is on the approved pinned list.")}
    systems = []
    rows_by_id = {r["id"]: r for r in state["rows"]}
    for system in state["systems"].values():
        lines = []
        for track, blockers in system["blockers"].items():
            for b in blockers:
                lines.append({"text": f"Blocks its {TRACK_WORDS[track]} track: {b['label']} ({_via_words({'via': b['via']})}), "
                                      f"{LABEL_WORDS.get(b['answer_label'] or '', '').lower()}. "
                                      + (first_version_words(b["question"], b["first_version"], b["library_label"]) or ""),
                              "fix_id": b["fix_id"]})
        # Phase 5c: what a person accepted from Otto for a library of this system (never among the blockers above)
        otto_lines = [line for top in state["tops"] if top["tie"]["system"] == system["key"]
                      for row_id in top["rows"] for line in (((otto or {}).get(rows_by_id[row_id]["key"]) or {}).get("status") or {}).get("lines") or []]
        systems.append({"key": system["key"], "name": system["name"], "kind_label": KIND_LABELS[system["kind"]],
                        "tied_from": " and ".join(system["tops"]), "otto_lines": otto_lines,
                        "blocker_lines": lines or [{"text": "No library in your list blocks a track of this system.", "fix_id": None}],
                        "without_answer": system["without_answer"],
                        "without_answer_text": _without_answer_words(system["without_answer"]),
                        "environment_line": ENVIRONMENT_LINE})
    rows = {r["id"]: r for r in state["rows"]}
    choices = [{"key": "", "name": "None of these"}] + [{"key": s["key"], "name": f"{KIND_LABELS[s['kind']]}: {s['name']}"}
                                                       for s in state["system_choices"]]
    groups = []
    for top in state["tops"]:
        tie = top["tie"]
        name = next((s["name"] for s in state["system_choices"] if s["key"] == tie["system"]), None)
        words = (f"Part of {name}, tied by name and version." if tie["source"] == "name_version" and name else
                 f"Part of {name}, set by you." if name else
                 "Not tied to a system in your file: its libraries are answered and block nothing.")
        groups.append({"key": top["key"], "label": top["label"], "tie_words": words, "system": tie["system"], "tie_source": tie["source"],
                       "picker": {"label": "Part of", "options": choices, "selected": tie["system"] or ""},
                       "empty_text": None if top["rows"] else "Your file lists no libraries under it.",
                       "rows": [{**_row(rows[i], state, busy, isolated), **_otto_row((otto or {}).get(rows[i]["key"])),
                                 "impact": (impact or {}).get(rows[i]["key"])} for i in top["rows"]]})
    lst = state["list"]
    return {**base, "subline": (f"From your file {lst['filename']} ({lst['format']})"
                                + (f", which describes {state['described']}" if state.get("described") else "") + "."),
            "list_file": {"filename": lst["filename"], "format": lst["format"], "at": lst["at"], "sha256": lst["sha256"],
                     "not_libraries_text": (f"{state['not_libraries']} entries that are not libraries (for example the operating system) "
                                            "are not looked up." if state["not_libraries"] else None)},
            "measure_all": measure_all, "systems": systems, "groups": groups, "empty_text": None}


# ---------------------------------------------------------------- one measurement, as a result (the Lab's result view)

RUN_ANSWER_WORDS = {"yes": "Yes", "no": "No", "couldnt_check": "Couldn't check"}


def capability_result(w, spec: dict, run: dict, review: dict, ctx: dict) -> None:
    """The words of one reviewed capability check (kind "capability"). Decides nothing: the answers are the reviewer's."""
    import json
    d = review["detail"]
    target, control = spec["target"], spec["control"]
    name = target.get("label") or f"{target.get('name')} {target.get('version')}"
    questions = [q for q, _, _ in QUESTIONS if q in (d.get("questions") or [])]
    answers, says, why = d.get("answers") or {}, d.get("library_says") or {}, d.get("why") or {}
    worded = [f"{QUESTION_WORDS[q]}: {RUN_ANSWER_WORDS.get(str(answers.get(q)), 'Couldn' + chr(39) + 't check')}" for q in questions]
    w.plain = f"We asked the pinned public copy of {name} to do each one itself. " + "; ".join(worded) + "."
    w.summary = f"{name}, measured on a public copy: " + "; ".join(worded) + "."
    w.short = "Measured on a public copy."
    w.what = [f"We ran the pinned public copy of {name} in its own locked-down container and asked it for each algorithm. Where it had "
              "one, it did one round trip and the app's reference library checked the result.",
              f"We asked the same of two control copies: {control['capable']} must do all of it, and {control['incapable']} must refuse "
              "all of it in its own words."]
    same = d.get("same_copy_as_control")
    if same:
        w.what.append(f"This copy is also the {'capable' if same == 'capable' else 'incapable'} control, so here only the other control "
                      "is an independent check.")
    for q in questions:
        if answers.get(q) == "no" and says.get(q):
            w.what.append(f"{QUESTION_WORDS[q]}: the library itself said: {says[q]}")
        elif answers.get(q) == "couldnt_check":
            w.what.append(f"{QUESTION_WORDS[q]}: couldn't check ({why.get(q) or 'no clear answer'}).")
    w.shows = ["It shows what this exact version can do, measured on a public copy of it.",
               "It doesn't show which version your systems really load, or how they are set up: that needs your environment."]
    controls = d.get("controls") or {}
    rows = [[QUESTION_WORDS[q], RUN_ANSWER_WORDS.get(str(answers.get(q)), "Couldn't check"),
             RUN_ANSWER_WORDS.get(str((controls.get("capable") or {}).get(q)), "Couldn't check"),
             RUN_ANSWER_WORDS.get(str((controls.get("incapable") or {}).get(q)), "Couldn't check")] for q in questions]
    w.evidence = [{"type": "table", "title": "What each copy answered", "tag": "measured on a public copy",
                   "columns": [{"label": c, "align": "left"} for c in ("Question", name, control["capable"] + " (must do it)",
                                                                       control["incapable"] + " (must refuse)")],
                   "rows": rows, "meta": [], "note": None}]
    w.command = (f"{target.get('name')} {target.get('version')}, pinned public copy, in its own container: key pair, round trip and, where "
                 "measured, a TLS 1.3 handshake with the app's own test server; the reference library checks each one")
    raw = run.get("raw") or {}
    w.outputs = [{"title": "Raw output, this copy", "text": json.dumps(raw.get("subject") or {}, indent=1)[:20_000]},
                 {"title": "Raw output, the two control copies", "text": json.dumps(raw.get("controls") or {}, indent=1)[:20_000]}]
    w.control_text = (f"Both control copies answered as they must: {control['capable']} did all of it and {control['incapable']} refused "
                      "all of it, and still completed an ordinary handshake where one was made.")
    w.fix = None


# ---------------------------------------------------------------- a blocker, in the Migration step

def blocker_words(blocker: dict) -> tuple[str, str, str]:
    """(the claim, its label words, the first-version sentence) of one named dependency blocker, for the Migration
    step's lines. The label goes right after the claim it labels: "... which can't do X [release notes say]. 3.5.0 or later can." """
    question = QUESTION_WORDS[blocker["question"]]
    via = "" if not blocker["via"] else f" ({_via_words({'via': blocker['via']})})"
    first = first_version_words(blocker["question"], blocker["first_version"], blocker["library_label"]) or ""
    return (f"It relies on {blocker['label']}{via}, which can't do {question}",
            LABEL_WORDS.get(blocker["answer_label"] or "", "").lower(), first)


# ---------------------------------------------------------------- Fixes

def fix_view(fix: dict, system: dict, row: dict, blockers: list[dict], is_demo: bool) -> dict:
    versions = [b["first_version"] for b in blockers]
    known = [v for v in versions if v and v != "none_known"]
    from app.knowledge.versions import key, read_version
    target = max(known, key=lambda v: key(read_version(v))) if known and len(known) == len(versions) else None   # type: ignore[arg-type]
    name = row["library_label"] or row["name"]
    title = (f"Update {name} to {target} or later" if target else f"{row['label']}: no version is known that can do this")
    tracks = sorted({TRACK_WORDS[t] for t, bs in system["blockers"].items() for b in bs if b["row_key"] == row["key"]})
    sources = [src for src in _lookup_evidence(row) if not src["repeat"] and row["answers"][src["question"]]["answer"] == "no"]
    intro = [f"{row['label']} ({_via_words(row)}) can't do what the {' and '.join(tracks)} track of {system['name']} needs.",
             (f"The first version that can do all of it is {target}." if target else "No version of this library is known to do it, so the "
              "way forward is another library, or asking its makers."),
             "This is about other people's software: the app offers no code change and no pull request for it. Update it where you build or "
             "install it, then add the new dependency list here."]
    where = None
    if sources:
        where = {"title": "Where this comes from", "note": "Official sources, quoted as they were on the date checked.",
                 "columns": ["Source", "What it says", "Checked"],
                 "rows": [{"place": s["title"], "setting": s["quote"], "lead": s["checked"], "code": s["url"]} for s in sources],
                 "after": []}
    return {
        "id": fix["id"], "kind": "text", "title": title, "list_source": f"Dependencies: {system['name']}",
        "source": [{"t": "text", "v": "From the Dependencies view: "}, {"t": "mono", "v": row["label"]},
                   {"t": "text", "v": f" blocks the {' and '.join(tracks)} track of "}, {"t": "mono", "v": system["name"]}, {"t": "text", "v": "."}],
        "status": {"key": "text_only", "word": "Text only", "busy": False}, "labels": [], "is_demo": is_demo,
        "what": {"label": "What it suggests", "paragraphs": [[{"t": "text", "v": title + "."}]], "server_line": None},
        "proof": {"state": "none", "badge": None, "muted": None,
                  "text": "None. This suggestion is text only: the app has not changed anything in your software."},
        "pull_request": None,
        "approvers": {"text": "Whoever builds or installs this software, outside this app.", "options": None, "rows": None, "footnote": None},
        "actions": {"buttons": [], "note": None}, "patch": None, "merge_dialog": None,
        "sections": [{"key": "suggestion", "title": "The suggestion", "line": "Update the library, then add the new list", "open": True,
                      "suggestion": {"intro": intro, "warning": None, "where": where, "options": None, "exact": None}}],
        "sections_note": None, "change_box": None, "advisories": None,
    }


# ---------------------------------------------------------------- the evidence file

def export(state: dict) -> dict:
    rows = []
    for r in state["rows"]:
        rows.append({"id": r["id"], "name": r["name"], "version": r["version"], "purl": r["purl"], "under": r["owner"], "via": r["via"],
                     "library": r["library"], "measurable": r["measurable"], "copy": r["copy_label"],
                     "answers": {q: {k: a[k] for k in ("answer", "label", "first_version", "state", "state_reason", "measured", "agreement",
                                                       "library_says")} | {"lookup": a["lookup"]} for q, a in r["answers"].items()},
                     "measurement": {k: v for k, v in (r["measurement"] or {}).items() if k in ("run_id", "code", "control", "finished_at", "target_kind")}
                     or None})
    return {"list": state["list"], "described": state.get("described"),
            "tops": [{"key": t["key"], "label": t["label"], "tie": t["tie"], "rows": t["rows"]} for t in state["tops"]],
            "rows": rows, "systems": [{"key": s["key"], "name": s["name"], "kind": s["kind"], "blockers": s["blockers"],
                                       "without_answer": s["without_answer"]} for s in state["systems"].values()],
            "not_libraries": state["not_libraries"]}
