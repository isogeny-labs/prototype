"""Words for a change and what happened to it (phase 4b): the change box shown in the Migration step and in Fixes —
what it changes, the exact lines, "Try on a test copy" with its before and after, the approvals, Apply and Roll back.

Words only. The change comes from change_builder.py, the records from system_changes.py, and every verdict (did the try
pass, does the measurement after Apply match it, did Roll back put things back) from the fixed rules in reviewer.py.
Never "secure", never a score, nothing beyond what was measured."""
from __future__ import annotations

from datetime import datetime, timezone

from app.servers import lab_servers
from app.fixes.changes import REVIEWERS
from app.present import clients as present_clients
from app.present import source as present_source
from app.present import times
from app.present.tracks import TRACK_LABELS, hybrid_client

DEMO_REVIEWERS = ("a", "b")
FOOTNOTE = "This version has one login and no separate accounts. Whoever is at the keyboard records each approval, under the name shown."
TITLES = {"hybrid": "turn on hybrid key exchange on {name}", "full_pq": "move {name} to post-quantum only (key exchange and certificate)",
          "tls13": "switch TLS 1.2 off on {name}", "keep": "keep {name} classical for now", "wrap": "wrap the connection to {name}",
          "sign_both": "make {name} sign with both", "mldsa_only": "make {name} sign with ML-DSA only"}
FACT_WORDS = {"kex": "Key exchange", "auth": "Authentication", "classical_client": "Classical-only clients", "tls": "Server protocol check"}


def _t(v: str) -> dict:
    return {"t": "text", "v": v}


def _tag(v: str) -> dict:
    return {"t": "tag", "v": v}


def _m(v: str) -> dict:
    return {"t": "mono", "v": v}


def _cell(text: str, tag: str | None = None) -> list[dict]:
    return [_t(text)] + ([_t(" "), _tag(tag)] if tag else [])


def when(value) -> str:
    """A time as the screens write it, in UTC: 14 Nov 2026, 17:14 UTC."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    # For a file: the UTC words, as always. For a browser that asked: a mark, which the browser writes in the viewer's
    # own time zone (app/present/times.py).
    return times.written(value, f"{value.day} {value.strftime('%b %Y, %H:%M')} UTC")


def _fact_words(fact: str, value) -> str:
    if fact in ("kex", "auth"):
        return TRACK_LABELS.get(value, str(value))
    if fact == "classical_client":
        return {"connects": "connect", "cannot": "can't connect", "unknown": "not clear"}.get(value, str(value))
    return {"passed": "Passed", "failed": "Failed"}.get(value, str(value))


# ------------------------------------------------------------------ the before and after table

def _hello_sizes(detail: dict) -> dict:
    """The sizes of the handshake that stands for the measured status (hybrid, ML-KEM by itself, or classical)."""
    sizes = detail.get("sizes") or {}
    status = detail.get("status")
    pick = sizes.get("hybrid") if status == "hybrid" else sizes.get("pure") if status == "pq_only" else sizes.get("classical")
    return pick or {}


def _column(measured: dict | None, tag: str, skipped: str | None, accepted: str | None) -> dict:
    """One column of the before and after table, as cells by row label."""
    if measured is None:
        return {"_first": _cell("Not tried: " + skipped.rstrip(".").lower()[0] + skipped.rstrip(".")[1:] if skipped else "Running"), "_all": _cell("—")}
    code, detail = measured["code"], measured.get("detail") or {}
    if code in ("couldnt_run", "couldnt_trust"):
        label = (measured.get("result") or {}).get("label") or "Couldn't check"
        return {"_all": _cell(label.replace("Couldn't run", "Couldn't check"))}
    if code in ("passed", "failed"):                       # the server protocol check (SPEC 7c)
        versions = ((measured.get("raw") or {}).get("subject") or {}).get("versions") or {}
        accepted_versions = [v for v in ("TLS 1.3", "TLS 1.2", "TLS 1.1", "TLS 1.0") if (versions.get(v) or {}).get("state") == "accepted"]
        return {"TLS versions accepted": _cell(" and ".join(accepted_versions) or "none", tag),
                "Server protocol check": _cell({"passed": "Passed", "failed": "Failed"}[code], tag),
                "The settings were taken": _cell(accepted or "n/a", tag if accepted else None)}
    auth = detail.get("auth") or {}
    hello = _hello_sizes(detail)
    choice = detail.get("default_choice")
    out = {"Key exchange": _cell(TRACK_LABELS.get(code, code), tag),
           "Authentication": _cell(f"{TRACK_LABELS.get(auth.get('status'), 'Couldn’t check')} ({auth.get('certificate') or 'not read'})", tag),
           "Classical-only clients": _cell(_fact_words("classical_client", detail.get("classical_client")), tag),
           "Hybrid-only clients": _cell(_fact_words("classical_client", hybrid_client(detail)) if hybrid_client(detail) else "not clear", tag),
           "Hybrid chosen when a client offers both": _cell(("yes" if choice.get("hybrid_first") == "hybrid" else "no") if choice
                                                            else "not asked: no hybrid offered", tag if choice else None)}
    for label, key in (("First message", "client_hello_bytes"), ("Key share, client to server", "client_share_bytes"),
                       ("Key share, server to client", "server_share_bytes"), ("Certificate message", "certificate_message_bytes"),
                       ("Handshake signature", "signature_bytes")):
        value = hello.get(key)
        out[label] = _cell(f"{value:,} bytes" if isinstance(value, int) else "not measured", tag if isinstance(value, int) else None)
    out["The settings were taken"] = _cell(accepted or "n/a", tag if accepted else None)
    return out


MIGRATION_ROWS = ("Key exchange", "Authentication", "Classical-only clients", "Hybrid-only clients", "Hybrid chosen when a client offers both", "First message",
                  "Key share, client to server", "Key share, server to client", "Certificate message", "Handshake signature",
                  "The settings were taken")
TLS_ROWS = ("TLS versions accepted", "Server protocol check", "The settings were taken")


def _try_view(change: dict, rec: dict) -> dict | None:
    row = rec.get("try")
    if row is None:
        return None
    outcome = rec.get("try_outcome") or {}
    if outcome.get("code") == "running":
        return {"title": "Try on a test copy: running", "running": {"status": "running", "status_text": "Running",
                                                                    "progress": {"text": "measuring the copies", "percent": None}},
                "verdict": None, "columns": [], "rows": [], "notes": [], "results": [], "clients": None, "source_tag": None,
                "column_source_tags": []}
    name = change["name"]
    columns = ["", f"Before: {name} as measured"]
    cols = [_column(rec.get("try_before"), "measured", None, None)]
    # where each column came from (22 November 2026): the server as it is today is a reading of it (live); each copy is a
    # test copy on this computer (lab)
    # (a column that measured nothing, a copy that couldn't be checked or was skipped, rests on nothing: no tag)
    column_sources: list[dict | None] = [None, present_source.live(name) if _observed(rec.get("try_before")) else None]
    results = []
    if rec.get("try_before") and rec["try_before"].get("result"):
        results.append({"label": f"{name} as measured before the try", "result": rec["try_before"]["result"]})
    notes = []
    for copy in rec.get("try_copies") or []:
        measured = copy.get("measured")
        is_nginx = copy["phase"] == "try_nginx" or change.get("target") == "lab_nginx"
        tag = "measured on nginx" if is_nginx else "measured on the copy"
        columns.append(f"After: {copy['label']}")
        accepted = None
        if measured is not None:
            raw_copy = (measured.get("raw") or {}).get("copy") or {}
            accepted = ("yes: nginx -t passed and nginx started" if is_nginx and not raw_copy.get("problem") else
                        "yes: the copy started" if not raw_copy.get("problem") else f"no: {raw_copy['problem']}")
            if measured.get("result"):
                results.append({"label": copy["label"], "result": measured["result"]})
        cols.append(_column(measured, tag, copy.get("skipped"), accepted))
        column_sources.append(present_source.lab_try() if _observed(measured) and not copy.get("skipped") else None)
        if copy.get("skipped"):
            notes.append(f"{copy['skipped'].rstrip('.')}. So the try is decided on the test copy alone.")
    labels = TLS_ROWS if change["kind"] == "tls" else MIGRATION_ROWS
    rows = []
    for n, label in enumerate(labels):
        cells = [c.get(label) or (c.get("_first") if n == 0 and c.get("_first") else c.get("_all")) or _cell("") for c in cols]
        rows.append({"label": label, "cells": cells})
    code = outcome.get("code")
    failed_checks = [chk for c in outcome.get("checks") or [] for chk in c.get("checks") or [] if not chk["ok"]]
    if code == "passed":
        verdict = {"label": "Try passed.", "look": "pass",
                   "text": ("Every copy that was tried measures what the change promises, and the controls were read correctly. "
                            + _cost_words(change))}
    elif code == "failed":
        what = "; ".join(f"{FACT_WORDS[c['fact']]}: expected {_fact_words(c['fact'], c['want'])}, measured {_fact_words(c['fact'], c['got'])}"
                         for c in failed_checks) or "the copy did not measure what the change promises"
        verdict = {"label": "Try did not pass.", "look": "fail", "text": f"{what}. Apply stays off. Nothing real has changed."}
    else:
        verdict = {"label": "No answer from the try.", "look": "warn",
                   "text": "A copy could not be measured, or its control did not behave, so the try gives no answer either way. Apply stays off. "
                           "Try again."}
    title = {"passed": "passed", "failed": "did not pass"}.get(code, "no answer")
    notes.append(f"Tried {when(row.created_at)}. The test certificate and its test key were made for the try and thrown away; the key is "
                 "never shown or stored.")
    # Phase 4e: who can still connect, measured on the first copy. Information: it decides nothing about the verdict above.
    clients = present_clients.try_block(rec.get("clients"))
    measured_clients = (rec.get("clients") or {}).get("run") or {}
    if measured_clients.get("result"):
        results.append({"label": "who can still connect (the client stand-ins)", "result": measured_clients["result"]})
    return {"title": f"Try on a test copy: {title}", "running": None, "verdict": verdict, "columns": columns, "rows": rows,
            "notes": notes, "results": results, "clients": clients,
            # (a try that gave no answer either way proved nothing: no tag)
            "source_tag": present_source.lab_try(clients=bool(measured_clients.get("result"))) if code in ("passed", "failed") else None,
            "column_source_tags": column_sources}


def _observed(measured: dict | None) -> bool:
    """Did this measurement read something (not missing, not couldn't run, check or trust)?"""
    return measured is not None and measured.get("code") not in present_source.NO_RESULT


def _cost_words(change: dict) -> str:
    return {"hybrid": "What it costs, plainly: bigger first messages; classical-only clients keep connecting.",
            "full_pq": ("What it costs, plainly: clients that can't do ML-KEM, or can't check an ML-DSA certificate, can no longer connect. "
                        "This app can't see your clients."),
            "tls13": "What it costs, plainly: clients that can't use TLS 1.3 can no longer connect."}.get(change["option"], "")


# ------------------------------------------------------------------ approvals, Apply, Roll back

def _approvals(change: dict, rec: dict, gates: dict) -> dict | None:
    if not change.get("settings_after") or change.get("target") is None:
        return None
    request = rec.get("request")
    picker = None
    rows = []
    if request is None:
        picker = {"options": [{"id": r, "name": n, "demo": r in DEMO_REVIEWERS, "checked": r == "you"} for r, n in REVIEWERS.items()],
                  "button": "Ask for approval", "enabled": gates["ask"] is None, "reason": gates["ask"]}
    else:
        for reviewer in request.reviewers:
            done = rec["approvals"].get(reviewer)
            label = "Approve for You" if reviewer == "you" else f"Approve as {REVIEWERS[reviewer]}"
            rows.append({"reviewer": reviewer, "name": REVIEWERS[reviewer], "demo": reviewer in DEMO_REVIEWERS,
                         "approved_at": when(done.approved_at) if done else None,
                         "status_text": f"approved {when(done.approved_at)}" if done else "not yet",
                         "approve": None if done else {"label": label, "enabled": gates["approve"] is None}})
    return {"title": "Who must approve before Apply", "picker": picker, "rows": rows, "footnote": FOOTNOTE}


def _applied(change: dict, rec: dict) -> dict | None:
    row = rec.get("apply")
    if row is None:
        return None
    history = []
    for kind, event, at in reversed(rec.get("events") or []):
        if kind == "apply":
            history.append(f"Applied {when(at)}: {lab_servers.groups_words(event.settings_after)}; TLS {lab_servers.versions_words(event.settings_after)}.")
        else:
            history.append(f"Rolled back {when(at)}.")
    if not row.accepted:
        return {"title": "After Apply", "badge": {"label": "Not applied: the server refused the settings", "look": "fail"},
                "paragraphs": [[_t(f"Apply was pressed {when(row.applied_at)}, and the server refused the settings: {row.words}. "
                                   "Its earlier settings stayed in force.")]], "differences": [], "history": history, "source_tag": None}
    back = rec.get("rollback")
    if back is not None and back.accepted:
        outcome = rec.get("rollback_outcome") or {}
        after = rec.get("rollback_after")
        if outcome.get("code") == "measuring" or after is None:
            text = f"Rolled back {when(back.rolled_back_at)}: the earlier settings are back. Measuring again now."
            badge = {"label": "Rolled back · measuring", "look": "neutral"}
        elif outcome.get("code") == "as_before":
            text = (f"Rolled back {when(back.rolled_back_at)}: the earlier settings are back. Measured again {when(after['finished_at'])}: "
                    f"{_status_words(after)}, as before the change.")
            badge = {"label": "Rolled back · measured as before", "look": "neutral"}
        else:
            text = (f"Rolled back {when(back.rolled_back_at)}. Measured again {when(after['finished_at'])}: {_status_words(after)}, which is not "
                    "how it measured before the change.")
            badge = {"label": "Rolled back · not as before", "look": "fail"}
        diffs = [f"{FACT_WORDS[d['fact']]}: before the change {_fact_words(d['fact'], d['before'])}, now {_fact_words(d['fact'], d['after'])}."
                 for d in outcome.get("differences") or []]
        # (a measurement that gave no answer either way observed nothing: no tag)
        measured_back = (present_source.after_change(change["name"], rolled_back=True)
                         if after is not None and outcome.get("code") not in ("measuring", "no_answer") else None)
        return {"title": "After Roll back", "badge": badge, "paragraphs": [[_t(text)]], "differences": diffs, "history": history,
                "source_tag": measured_back}
    outcome = rec.get("apply_outcome") or {}
    after = rec.get("apply_after")
    who = f"Applied to {change['name']} {when(row.applied_at)} by the person logged in, after the try passed and every reviewer approved."
    if outcome.get("code") == "measuring" or after is None:
        return {"title": "After Apply", "badge": {"label": "Applied · measuring", "look": "neutral"},
                "paragraphs": [[_t(who + " The app is measuring it again now.")]], "differences": [], "history": history, "source_tag": None}
    if outcome.get("code") == "matches":
        return {"title": "After Apply", "badge": {"label": "Applied · matches the try", "look": "pass"},
                "paragraphs": [[_t(f"{who} The app measured again by itself {when(after['finished_at'])}: {_status_words(after)} "), _tag("measured"),
                                _t(". That matches the try.")]], "differences": [], "history": history,
                "source_tag": present_source.after_change(change["name"])}
    diffs = [f"{FACT_WORDS[d['fact']]}: the try measured {_fact_words(d['fact'], d['tried'])}, the server now measures {_fact_words(d['fact'], d['after'])}."
             for d in outcome.get("differences") or []]
    if outcome.get("code") == "no_answer":
        diffs = ["The measurement after Apply gave no answer either way."]
    return {"title": "After Apply", "badge": {"label": "Applied · does not match the try", "look": "fail"},
            "paragraphs": [[_t(f"{who} The app measured again by itself {when(after['finished_at'])}, and the result does not match the try. "
                               "Roll back puts the earlier settings back.")]], "differences": diffs, "history": history,
            # (a measurement that gave no answer either way observed nothing: no tag)
            "source_tag": None if outcome.get("code") == "no_answer" else present_source.after_change(change["name"])}


def _status_words(measured: dict) -> str:
    code, detail = measured["code"], measured.get("detail") or {}
    if code in ("passed", "failed"):
        return f"the server protocol check {'passed' if code == 'passed' else 'failed'}"
    auth = (detail.get("auth") or {}).get("status")
    client = _fact_words("classical_client", detail.get("classical_client"))
    return (f"Key exchange {TRACK_LABELS.get(code, code)}, Authentication {TRACK_LABELS.get(auth, 'couldn’t check')}, "
            f"classical-only clients {client}")


# ------------------------------------------------------------------ the whole box

def change_view(change: dict, rec: dict, gates: dict) -> dict:
    # Where it came from (22 November 2026): every small tag of the box in its source's look. A change is made to a server,
    # so a bare "measured" is a reading of the server itself (live); "measured on the copy" and "on nginx" are the try (lab).
    return present_source.colour_tags(_change_view(change, rec, gates), present_source.LIVE)


def _change_view(change: dict, rec: dict, gates: dict) -> dict:
    name, option = change["name"], change["option"]
    title = "Your change: " + TITLES.get(option, "change {name}").format(name=name)
    source = change.get("_plan_source")
    triable = bool(change.get("settings_after"))
    target = change.get("target")
    sections: list[dict] = []
    if change.get("table"):
        sections.append({"kind": "table", "title": "What it changes" + (" on " + change["target_words"] if change.get("target_words") else ""),
                         "columns": change["table"]["columns"], "rows": [[[_t(c)] for c in r] for r in change["table"]["rows"]]})
    if change.get("lines"):
        tried_nginx = any(c.get("phase") == "try_nginx" and c.get("measured") for c in rec.get("try_copies") or [])
        rows = [{"place": line["place"], "lead": line["lead"] if not (tried_nginx and line["place"] == "nginx")
                 else line["lead"].rstrip(":") + ", and again in your try:", "code": line["code"]} for line in change["lines"]]
        sections.append({"kind": "lines", "title": "The same change on your own server software", "rows": rows,
                         "note": "Change every existing line rather than adding another one, then reload the server."})
    if change.get("certificate"):
        cert = change["certificate"]
        sections.append({"kind": "lines", "title": "Your own ML-DSA certificate", "rows": [{"place": "OpenSSL 3.5", "lead": cert["lead"], "code": cert["code"]}],
                         "note": cert["note"]})
    if change.get("warnings"):
        sections.append({"kind": "text", "title": "Before you change it", "paragraphs": [[_t(w)] for w in change["warnings"]]})
    if change.get("text"):
        sections.append({"kind": "text", "title": "What this means", "paragraphs": [[_t(w)] for w in change["text"]]})
    if change.get("recheck"):
        sections.append({"kind": "text", "title": "What the gateway must do" if option == "wrap" else "What to recheck on the review date",
                         "paragraphs": [[_t("• " + w)] for w in change["recheck"]]})
    if change.get("review_date"):
        sections.append({"kind": "text", "title": "Review date", "paragraphs": [[_t(change["review_date"])]]})
    outcome = (rec.get("try_outcome") or {}).get("code")
    in_force = rec.get("in_force")
    applied_this = in_force is not None and in_force.change_fp == change["fingerprint"]
    buttons = []
    if triable:
        buttons.append({"action": "try", "label": "Try again on a test copy" if rec.get("try") else "Try on a test copy",
                        "primary": rec.get("try") is None, "enabled": gates["try"] is None, "reason": gates["try"]})
        buttons.append({"action": "apply", "label": f"Apply to {name}", "primary": outcome == "passed" and gates["apply"] is None,
                        "enabled": gates["apply"] is None, "reason": gates["apply"]})
        if in_force is not None:
            buttons.append({"action": "rollback", "label": "Roll back", "primary": False, "enabled": gates["rollback"] is None,
                            "reason": gates["rollback"]})
    buttons.append({"action": "download", "label": "Download change", "primary": False, "enabled": True, "reason": None})
    steps = []
    if triable and target is not None:
        req, approvals = rec.get("request"), rec.get("approvals") or {}
        n_ok = len([r for r in (req.reviewers if req else []) if r in approvals])
        a_out = (rec.get("apply_outcome") or {}).get("code")
        steps = [
            {"key": "built", "label": "Built", "state": "done", "text": "from your choice" if source == "choice" else
             "from the recommendation" if source == "recommendation" else "from the finding"},
            {"key": "tried", "label": "Tried on a test copy", "state": {"passed": "done", "failed": "failed", "running": "now",
                                                                         "couldnt_run": "failed"}.get(outcome, "now" if rec.get("try") else "off"),
             "text": {"passed": "passed", "failed": "did not pass", "running": "running", "couldnt_run": "no answer"}.get(outcome, "not yet")
             + (f", {when(rec['try'].created_at)}" if rec.get("try") and outcome not in (None, "running") else "")},
            {"key": "approvals", "label": "Approvals", "state": "done" if req and n_ok == len(req.reviewers) else "now" if req else "off",
             "text": (f"{n_ok} of {len(req.reviewers)}" + ("" if n_ok == len(req.reviewers) else ": waiting")) if req else "not asked yet"},
            {"key": "applied", "label": "Apply", "state": "done" if applied_this else "off",
             "text": f"applied {when(in_force.applied_at)}" if applied_this else ("rolled back" if rec.get("rollback") else "not applied")},
            {"key": "measured", "label": "Measured after", "state": ("done" if a_out == "matches" else "failed" if a_out in ("differs", "no_answer")
                                                                     else "now" if a_out == "measuring" else "off") if applied_this else "off",
             "text": {"matches": "matches the try", "differs": "does not match", "measuring": "measuring", "no_answer": "no answer"}.get(a_out, "the app measures again by itself") if applied_this else "the app measures again by itself"},
        ]
    if not triable:
        badge = {"label": "Text only", "look": "neutral"}
    elif rec.get("in_place") and (applied_this or target is None):
        badge = {"label": "In place (measured)", "look": "pass"}
    elif applied_this:
        a_out = (rec.get("apply_outcome") or {}).get("code")
        badge = {"label": {"matches": "Applied · matches the try", "differs": "Applied · does not match the try"}.get(a_out, "Applied · measuring"),
                 "look": {"matches": "pass", "differs": "fail"}.get(a_out, "neutral")}
    elif target is None:
        badge = {"label": "Ready to download", "look": "neutral"}
    elif rec.get("rollback") is not None and rec["rollback"].accepted and in_force is None and \
            (rec.get("try") is None or rec["try"].created_at <= rec["rollback"].rolled_back_at):
        badge = {"label": "Rolled back", "look": "neutral"}
    elif outcome == "running":
        badge = {"label": "Try running", "look": "neutral"}
    elif outcome in ("failed", "couldnt_run"):
        badge = {"label": "Try did not pass", "look": "fail"}
    elif outcome == "passed" and gates["apply"] is None:
        badge = {"label": "Ready to apply", "look": "pass"}
    elif outcome == "passed" and rec.get("request") is None:
        badge = {"label": "Try passed", "look": "pass"}          # nobody has been asked yet
    elif outcome == "passed":
        badge = {"label": "Waiting for approval", "look": "warn"}
    else:
        badge = {"label": "Ready to try", "look": "neutral"}
    intro_text = {
        "hybrid": "It adds the hybrid key exchange next to the classical ones, so clients that can't do hybrid keep connecting. Key exchange track only; authentication doesn't change.",
        "full_pq": "It accepts ML-KEM key exchange by itself and nothing else, and presents an ML-DSA certificate: both tracks at the target. There is no classical fallback.",
        "tls13": "It switches TLS 1.2 (and anything older) off on the demo server, so it accepts TLS 1.3 only, as the file claims.",
    }.get(option, "")
    built_from = {"choice": "Built from your choice.", "recommendation": "Built from the recommendation (you haven't chosen yet).",
                  "fix": "Built from the failed Old TLS versions test."}.get(source, "")
    where = (f" It can be tried and applied on {change['target_words']}." if target else
             f" {change['no_target']}" if change.get("no_target") and triable else "")
    note = None
    if triable and target is not None:
        note = ("The app changes a system only when a person presses Apply, after a passing try on a test copy and every approval asked for. "
                "It measures again right after, and Roll back is then always there.")
    return {"id": change["key"], "title": title, "badge": badge, "intro": [_t(" ".join(p for p in (built_from, intro_text) if p) + where)],
            "steps": steps, "sections": sections, "try": _try_view(change, rec), "approvals": _approvals(change, rec, gates),
            "applied": _applied(change, rec), "buttons": buttons, "note": note, "busy": bool(rec.get("busy"))}


def export(change: dict, rec: dict) -> dict:
    """The change and every step taken with it, for the evidence file (the runs themselves go in with their records)."""
    tried = rec.get("try")
    return {"change": {k: v for k, v in change.items() if not k.startswith("_")},
            "try": ({"tried_at": when(tried.created_at), "copies": [{"label": c["label"], "skipped": c.get("skipped"),
                                                                     "run_id": (c.get("measured") or {}).get("run_id")} for c in rec.get("try_copies") or []],
                     "before_run_id": tried.before_run_id, "outcome": (rec.get("try_outcome") or {}).get("code"),
                     "checks": (rec.get("try_outcome") or {}).get("checks")} if tried else None),
            "approval_request": ({"reviewers": [REVIEWERS[r] for r in rec["request"].reviewers], "asked_at": when(rec["request"].created_at),
                                  "approvals": [{"name": a.name, "approved_at": when(a.approved_at)} for a in rec["approvals"].values()]}
                                 if rec.get("request") else None),
            "applies": [{"applied_at": when(a.applied_at), "target": a.target, "accepted": a.accepted, "server_words": a.words,
                         "settings_before": a.settings_before, "settings_after": a.settings_after} for a in rec.get("applies") or []],
            "after_apply": ({"outcome": (rec.get("apply_outcome") or {}).get("code"), "differences": (rec.get("apply_outcome") or {}).get("differences"),
                             "run_id": (rec.get("apply_after") or {}).get("run_id")} if rec.get("apply") else None),
            "rollback": ({"rolled_back_at": when(rec["rollback"].rolled_back_at), "accepted": rec["rollback"].accepted, "server_words": rec["rollback"].words,
                          "outcome": (rec.get("rollback_outcome") or {}).get("code"), "run_id": (rec.get("rollback_after") or {}).get("run_id")}
                         if rec.get("rollback") else None),
            "in_place_now": rec.get("in_place")}


def export_history(history: dict) -> dict:
    """Every round of one change, for the evidence file (from system_changes.change_history), in time order."""
    def run_id(measured):
        return (measured or {}).get("run_id")
    def clients(t: dict) -> dict:
        """Phase 4e, only on a try that has the client stand-ins' run (an earlier try's entry reads as it did)."""
        measured = ((t.get("clients") or {}).get("run")) or None
        if measured is None:
            return {}
        detail = measured.get("detail") or {}
        return {"clients": {"run_id": measured.get("run_id"), "code": measured.get("code"),
                            "summary": (present_clients.try_block(t["clients"]) or {}).get("summary") if measured.get("code") == "measured" else None,
                            "counts": detail.get("counts"),
                            "stand_ins": [{"id": r.get("id"), "word": r.get("word"), "new": r.get("new")} for r in detail.get("stand_ins") or []],
                            "decides": present_clients.DECIDES_NOTHING}}
    return {
        "tries": [{"tried_at": when(t["row"].created_at), "change_fingerprint": t["row"].change_fp, "before_run_id": t["row"].before_run_id,
                   "copies": [{"label": c["label"], "skipped": c["skipped"], "run_id": run_id(c["measured"])} for c in t["copies"]],
                   "outcome": t["outcome"].get("code"), "checks": t["outcome"].get("checks"), **clients(t)} for t in history["tries"]],
        "approval_requests": [{"asked_at": when(r["row"].created_at), "change_fingerprint": r["row"].change_fp,
                               "reviewers": [REVIEWERS.get(x, x) for x in r["row"].reviewers],
                               "approvals": [{"name": a.name, "approved_at": when(a.approved_at)} for a in r["approvals"]]}
                              for r in history["approval_requests"]],
        "applies": [{"applied_at": when(a["row"].applied_at), "from_this_import": a["from_this_import"],
                     "change_fingerprint": a["row"].change_fp, "target": a["row"].target,
                     "accepted": a["row"].accepted, "server_words": a["row"].words, "settings_before": a["row"].settings_before,
                     "settings_after": a["row"].settings_after, "measured_after_run_id": run_id(a["after"]),
                     "after_apply": (a["outcome"] or {}).get("code"), "differences": (a["outcome"] or {}).get("differences"),
                     "rollback": ({"rolled_back_at": when(a["rollback"].rolled_back_at), "accepted": a["rollback"].accepted,
                                   "server_words": a["rollback"].words, "measured_after_run_id": run_id(a["after_rollback"]),
                                   "outcome": (a["rollback_outcome"] or {}).get("code")} if a["rollback"] is not None else None)}
                    for a in history["applies"]],
    }


__all__ = ["change_view", "export", "export_history", "when"]
