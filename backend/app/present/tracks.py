"""Words for the two tracks of the Migration step (phase 4b): key exchange and authentication for a server, signatures
for a signing program; the target (post-quantum on every track); each track's next step and why; the roadmap by track;
and the "Also noticed" notes.

Words only. Each track's status comes from a reviewed measurement (reviewer.py), its roadmap place from the fixed
rules in migration_rules.py. Never "secure", never a score, nothing beyond what was measured."""

from __future__ import annotations

from app.migration import rules
from app.present import pq as present_pq
from app.engine.guidance import PQ_DATES
from app.names import join_and

MEASURED = "measured"
NIST_TAG = PQ_DATES["tag"]
TRACK_TITLES = {
    "kex": ("Track 1 · Key exchange", "Key exchange"),
    "auth": ("Track 2 · Authentication", "Authentication"),
    "signatures": ("Signatures", "Signatures"),
}
TRACK_LABELS = {
    "classical": "Classical",
    "hybrid": "Hybrid (interim)",
    "pq_only": "Post-quantum only",
    "post_quantum": "Post-quantum",
    "couldnt_check": "Couldn't check",
    "not_measured": "Not measured yet",
}
BANDS = {
    "target": ("At the target", "Post-quantum on this track, measured. Keep measuring after any change.", "plain"),
    "done_for_now": (
        "Done for now",
        "The interim step (hybrid) is in place. The next step waits for your clients.",
        "plain",
    ),
    "phase1": (
        "Phase 1",
        "Hybrid key exchange on internet-facing, long-lived systems with nothing in the way.",
        "highlight",
    ),
    "phase2": (
        "Phase 2",
        "Authentication and signatures, and key exchange on systems with something to fix or check first.",
        "plain",
    ),
    "later": ("Later", "Kept classical for now, each with a review date. Never “forever”.", "plain"),
    "wrapped": ("Wrapped", "Planned: a gateway in front does the post-quantum part. Shown separately.", "plain"),
    "not_placed": ("Not placed yet", "The status couldn't be measured, so there is no plan.", "dashed"),
}


def _t(v: str) -> dict:
    return {"t": "text", "v": v}


def _tag(v: str) -> dict:
    return {"t": "tag", "v": v}


def _parts(*items) -> list[dict]:
    return [(_t(p) if isinstance(p, str) else p) for p in items]


def tracks_of(state: dict) -> dict:
    """Each track's status code (classical | hybrid | pq_only | post_quantum), or None when there is none."""
    if state["kind"] == "software":
        return {"signatures": state["status"]}
    auth = (state.get("detail") or {}).get("auth") or {}
    return {
        "kex": state["status"],
        "auth": auth.get("status") if state["status"] and auth.get("status") in ("classical", "post_quantum") else None,
    }


def _code(state: dict, status: str | None) -> str:
    if status:
        return status
    return "not_measured" if state["code"] is None else "couldnt_check"


def target_line(state: dict) -> str:
    if state["kind"] == "software":
        return "Target: post-quantum signatures (ML-DSA), with signing with both as an interim step."
    return "Target: post-quantum on both tracks. Hybrid is an interim step, never the end. No system is “done” until both are there."


# ------------------------------------------------------------------ one track


def _kex_facts(detail: dict, raw: dict) -> list[dict]:
    out = []
    for fact in present_pq.server_facts(detail, raw):
        if fact["label"] in ("Hybrid key exchange", "ML-KEM by itself", "Classical key exchange"):
            out.append({"label": fact["label"], "value": _parts(fact["text"] + " ", _tag(MEASURED))})
    choice = detail.get("default_choice")
    if choice:
        first = choice.get("hybrid_first")
        out.append(
            {
                "label": "Chosen by default?",
                "value": _parts(
                    (
                        "Yes: offered both keys in one hello with hybrid listed first, it took "
                        + str(choice.get("hybrid_first_group"))
                        + " "
                    )
                    if first == "hybrid"
                    else (
                        f"No: offered both keys with hybrid listed first, it took {choice.get('hybrid_first_group')} "
                    )
                    if first
                    else "Not clear: that handshake did not complete ",
                    _tag(MEASURED),
                ),
            }
        )
        second = choice.get("classical_first")
        if second:
            words = (
                "It still takes hybrid: this server prefers it"
                if second == "hybrid"
                else f"It takes {choice.get('classical_first_group')}: this server follows the client's order"
            )
            out.append({"label": "If the client lists classical first", "value": _parts(words + " ", _tag(MEASURED))})
    client = detail.get("classical_client")
    if client:
        text = {
            "connects": "Still connect",
            "cannot": "Can't connect: the server refused it",
            "unknown": "Not clear",
        }.get(client, "Not clear")
        version = ((raw.get("subject") or {}).get("classical_client") or {}).get("tls_version")
        if client == "connects" and version:
            text += f", with {version}"
        extra = (
            [_t(" · information, not a failure, during a transition")]
            if client == "connects" and detail.get("hybrid_groups")
            else []
        )
        out.append({"label": "Classical-only clients", "value": _parts(text + " ", _tag(MEASURED), *extra)})
    hybrid_only = hybrid_client(detail)
    if hybrid_only:
        out.append(
            {
                "label": "Hybrid-only clients",
                "value": _parts(
                    {"connects": "Connect", "cannot": "Can't connect: the server refused it"}[hybrid_only] + " ",
                    _tag(MEASURED),
                ),
            }
        )
    return out


def hybrid_client(detail: dict) -> str | None:
    """Can a client that offers only hybrid key exchange connect? From the full hybrid handshake: connects | cannot | None."""
    outcome = (detail.get("witnesses") or {}).get("builtin")
    return {"completed": "connects", "refused": "cannot"}.get(outcome)


def _auth_facts(detail: dict) -> list[dict]:
    auth, cert, sizes = detail.get("auth") or {}, detail.get("certificate") or {}, detail.get("sizes") or {}
    sig_bytes = next(
        (
            h.get("signature_bytes")
            for h in (sizes.get("classical"), sizes.get("hybrid"), sizes.get("pure"))
            if h and h.get("signature_bytes")
        ),
        None,
    )
    out = []
    if cert.get("name"):
        size = f", {cert['public_key_bytes']:,} bytes" if cert.get("public_key_bytes") else ""
        out.append({"label": "Certificate key", "value": _parts(f"{cert['name']}{size} ", _tag(MEASURED))})
    if auth.get("signature"):
        size = f", {sig_bytes:,} bytes" if sig_bytes else ""
        out.append({"label": "Handshake signature", "value": _parts(f"{auth['signature']}{size} ", _tag(MEASURED))})
    return out


def _auth_sentence(state: dict) -> str:
    auth = (state.get("detail") or {}).get("auth") or {}
    status, cert, sig = auth.get("status"), auth.get("certificate"), auth.get("signature")
    if status == "classical":
        return f"Its certificate key is {cert} and it signs the handshake with {sig}: both classical."
    if status == "post_quantum":
        return f"Its certificate key is {cert} and it signs the handshake with {sig}: both post-quantum."
    if not state["status"]:
        return _couldnt_check(state)
    return {
        "no_certificate": "No certificate could be read, so this track couldn't be checked.",
        "no_signature": "The handshake signature could not be read, so this track couldn't be checked.",
        "mixed": f"Its certificate key is {cert} and it signs the handshake with {sig}: one classical, one post-quantum, so this track "
        "couldn't be given one status.",
    }.get(auth.get("why"), "This track couldn't be checked.")


def _next_and_why(state: dict, track: str, status: str | None) -> tuple[list, list]:
    option, source = state.get("plan_option"), state.get("plan_source")
    yours = " (your choice)" if source == "choice" else ""
    review = (state.get("review_date") or {}).get("value")
    date_words = _day(review)
    nist = [
        f"NIST deprecates today's public-key algorithms after {PQ_DATES['deprecated_after']} and disallows them after "
        f"{PQ_DATES['disallowed_after']} ",
        _tag(NIST_TAG),
        ".",
    ]
    if status is None:
        if state["code"] is None:
            return _parts("measure this system (Measure status)."), _parts(
                "every next step starts from what was measured."
            )
        return _parts("nothing until it can be measured."), _parts("nothing is planned from a guess.")
    if status in ("pq_only", "post_quantum"):
        return _parts("keep it there: measure again after any change."), _parts(
            "this track is at the target ", _tag(MEASURED), "."
        )
    if option == "keep":
        return (
            _parts(f"review by {date_words}: measure again and decide again{yours}."),
            _parts("kept classical for now, with a date, never “forever”. ", *nist),
        )
    if option == "wrap":
        if track == "auth":
            return _parts(f"the gateway presents its own certificate{yours}; this server's stays."), _parts(
                "this server can't be changed."
            )
        return (
            _parts(f"a gateway in front that does the post-quantum part{yours}."),
            _parts("this server can't be changed, so the post-quantum part has to be done in front of it."),
        )
    if track == "kex":
        if status == "hybrid":
            if option == "full_pq":
                return (
                    _parts(
                        f"post-quantum only, ML-KEM by itself{yours}, once every client that needs this server supports it."
                    ),
                    _parts("hybrid is the interim step, not the end. ", *nist),
                )
            return (
                _parts("post-quantum only (ML-KEM by itself), once every client that needs this server supports it."),
                _parts(
                    "hybrid is the interim step, not the end. Its classical half is one of the algorithms NIST deprecates after "
                    f"{PQ_DATES['deprecated_after']} and disallows after {PQ_DATES['disallowed_after']} ",
                    _tag(NIST_TAG),
                    ".",
                ),
            )
        tls_off = (state.get("detail") or {}).get("tls13") == "off"
        if option == "full_pq":
            return (
                _parts(f"post-quantum key exchange only{yours}; first check that every client supports it."),
                _parts("there is no classical fallback, and this app can't see your clients. ", *nist),
            )
        return (
            _parts("turn on hybrid key exchange" + (" (and TLS 1.3, which it needs)" if tls_off else "") + f"{yours}."),
            _parts(
                "traffic recorded today could be decrypted later, if a large quantum computer is built. Hybrid protects against "
                "that while classical-only clients keep connecting."
            ),
        )
    if track == "auth":
        auth = (state.get("detail") or {}).get("auth") or {}
        if option == "full_pq":
            return (
                _parts(f"an ML-DSA certificate, as part of Full post-quantum{yours}."),
                _parts(f"{auth.get('certificate') or 'Its certificate'} is classical. ", *nist),
            )
        return (
            _parts("an ML-DSA certificate, once your clients can check one."),
            _parts(
                f"{auth.get('certificate') or 'Its certificate'} is deprecated after {PQ_DATES['deprecated_after']} and disallowed after "
                f"{PQ_DATES['disallowed_after']} ",
                _tag(NIST_TAG),
                ". A recording made today can't be used to forge a signature later, "
                "so this comes after key exchange: Phase 2.",
            ),
        )
    algorithm = (state.get("detail") or {}).get("algorithm")
    if option in ("hybrid", "full_pq"):
        what = "sign with both " + str(algorithm) + " and ML-DSA" if option == "hybrid" else "sign with ML-DSA only"
        if (state.get("detail") or {}).get("can_make_pq") is True:
            # Phase 4c: a real library that already makes post-quantum signatures (measured). Nothing blocks the change.
            pq = (state.get("detail") or {}).get("pq_algorithm") or "ML-DSA-65"
            return (
                _parts(
                    f"{what}{yours}. Not blocked: this library can already make {pq} signatures ", _tag(MEASURED), "."
                ),
                _parts(
                    "a signature made today has to be trusted after ",
                    f"{PQ_DATES['deprecated_after']}, when NIST deprecates {algorithm} ",
                    _tag(NIST_TAG),
                    ".",
                ),
            )
        return (
            _parts(f"{what}{yours}, once its signing library can (the blocker)."),
            _parts(
                "a signature made today has to be trusted after ",
                f"{PQ_DATES['deprecated_after']}, when NIST deprecates {algorithm} ",
                _tag(NIST_TAG),
                ".",
            ),
        )
    return _parts("measure again."), _parts("")


def _couldnt_check(state: dict) -> str:
    """A system that couldn't be measured: the same sentence, with its reason, as its "Today" box."""
    from app.present.migration import today_sentence  # (present_migration imports this module)

    return today_sentence(state)


def track_views(state: dict) -> list[dict]:
    if not state["status"] and state["code"] is None:
        return []
    detail, raw = state.get("detail") or {}, state.get("raw") or {}
    out = []
    for track, status in tracks_of(state).items():
        title, short = TRACK_TITLES[track]
        if track == "kex":
            sentence = present_pq.status_sentence(state["status"], detail) if state["status"] else _couldnt_check(state)
            facts = _kex_facts(detail, raw) if state["status"] else []
        elif track == "auth":
            sentence, facts = _auth_sentence(state), (_auth_facts(detail) if state["status"] else [])
        else:
            sentence = str((state.get("result") or {}).get("plain") or "") if state["status"] else _couldnt_check(state)
            facts = (
                [{"label": "It signs with", "value": _parts(f"{detail.get('algorithm')} ", _tag(MEASURED))}]
                if state["status"]
                else []
            )
        nxt, why = _next_and_why(state, track, status)
        named = (state.get("dependency_blockers") or {}).get(track) or []
        if named:  # phase 4d: a library of the dependency list stops this track
            from app.present.dependencies import blocker_words

            claim, label, first = blocker_words(named[0])
            nxt = list(nxt) + [
                {"t": "text", "v": " Blocker: " + claim[0].lower() + claim[1:] + " "},
                _tag(label),
                {"t": "text", "v": (". " + first).rstrip()},
            ]
        code = _code(state, status)
        out.append(
            {
                "key": track,
                "title": title,
                "short_title": short,
                "status": {"code": code, "label": TRACK_LABELS[code]},
                "sentence": sentence,
                "facts": facts,
                "next": nxt,
                "why": why,
                "next_label": "Next:",
                "why_label": "Why:",
            }
        )
    return out


def tracks_brief(state: dict) -> list[dict]:
    return [
        {
            "title": TRACK_TITLES[track][1],
            "status": {"code": _code(state, status), "label": TRACK_LABELS[_code(state, status)]},
        }
        for track, status in tracks_of(state).items()
    ]


def also_noticed(state: dict) -> list[str]:
    out = []
    for note in (state.get("detail") or {}).get("also_noticed") or []:
        if note.get("code") == "old_tls":
            old = join_and(note["versions"])
            out.append(
                f"This server also accepts {old}, {'both retired' if len(note['versions']) == 2 else 'retired'} in 2021. "
                "This doesn't change a status."
            )
        elif note.get("code") == "pure_too":
            out.append(
                f"It also accepts {present_pq.group_words(note['group'])} by itself, next to its other key exchanges. "
                "This doesn't change a status."
            )
    return out


# ------------------------------------------------------------------ the roadmap by track


def track_bands(state: dict) -> dict:
    blocking = state["blockers"].get(state["plan_option"], []) if state.get("plan_option") else []
    values = {f: s["value"] for f, s in state["settings"].items()}
    return {
        track: rules.track_band(state["kind"], track, status, state.get("plan_option"), values, blocking)
        for track, status in tracks_of(state).items()
    }


def plan_line(state: dict, change_line: str | None) -> str:
    """The list card's last line: what happens next for this system, or where its change stands."""
    if not state["status"]:
        return "No plan yet: status not measured" if state["code"] is None else "No plan yet: couldn't check"
    if change_line:
        return change_line
    bands, option = state["track_bands"], state["plan_option"]
    if all(b == "target" for b in bands.values()):
        return "At the target · keep measuring"
    if option == "keep":
        return f"Kept classical · review {_day((state.get('review_date') or {}).get('value'))}"
    if option == "wrap":
        return "Next: wrap the connection"
    order = ("phase1", "phase2", "done_for_now")
    for wanted in order:
        for track, band in bands.items():
            if band == wanted and wanted != "done_for_now":
                what = {
                    "kex": {"hybrid": "hybrid key exchange", "full_pq": "post-quantum key exchange"}.get(
                        option, "key exchange"
                    ),
                    "auth": "authentication",
                    "signatures": "sign with both" if option == "hybrid" else "post-quantum signatures",
                }[track]
                return f"Next: {what} · {BANDS[band][0]}"
    return "Done for now · keep measuring"


def _day(value) -> str:
    from app.present.migration import day

    return day(value)


__all__ = [
    "tracks_of",
    "track_views",
    "tracks_brief",
    "also_noticed",
    "track_bands",
    "plan_line",
    "target_line",
    "BANDS",
    "TRACK_LABELS",
    "TRACK_TITLES",
]
