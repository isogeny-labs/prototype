"""Words for the Migration step (phase 4a): the screen, the roadmap, the Fixes entries and the evidence export.

Words only. The status of a system comes from a reviewed measurement (reviewer.py), and the recommendation, the
blockers and the roadmap from the fixed rules in migration_rules.py; this module is handed all of that as one
`state` per system (migration.py builds it) and chooses the sentences.

Rules for every sentence: plain words for a busy engineer who isn't a cryptographer; never "secure", never a
score, never a judgement beyond what was measured. Every number says where it came from: "measured" (on the
system), "measured on our test server", "measured on the reference library", or "published: <source>"."""
from __future__ import annotations

from datetime import date

from app.migration import rules
from app.present import pq as present_pq
from app.present import tracks as present_tracks
from app.engine.guidance import PQ_DATES, PQ_PUBLISHED
from app.names import join_and

TITLE = "Migration plan"
DISCLAIMER = "Passing these tests doesn't prove a system secure. It shows these specific checks passed."
FILE_SETTINGS_TITLE = "System settings from the file (used by the Migration step)"
RULES_TAG = "from fixed rules, no AI model"
MEASURED, OUR_SERVER, REFERENCE, NOT_MEASURED = "measured", "measured on our test server", "measured on the reference library", "not measured"
OPTION_TITLES = {"keep": "Keep classical for now", "hybrid": "Hybrid", "full_pq": "Full post-quantum", "wrap": "Wrap the connection"}
PROGRAM_OPTION_TITLES = {**OPTION_TITLES, "hybrid": "Hybrid: sign with both", "full_pq": "Full post-quantum: ML-DSA only"}
STATUS_LABELS = {**present_pq.STATUS_LABELS, "couldnt_check": "Couldn't check", "not_measured": "Not measured yet"}
FIELD_LABELS = {"lifespan": "Data lifespan", "exposure": "Exposure", "can_change": "Can it be changed?"}
VALUE_LABELS = {"lifespan": {"long": "Long-lived", "short": "Short-lived"}, "exposure": {"internet": "Internet-facing", "internal": "Internal"},
                "can_change": {"yes": "Yes", "no": "No"}}
SOURCE_LABELS = {"file": "from the file", "user": "set by you", "assumed": "assumed"}
BANDS = {   # phase 4a's single-track bands, kept for reading older words; phase 4b places each track (present_tracks.BANDS)
    "already": ("Already there", "Measured in place. Nothing to do now.", "plain"),
    "phase1": ("Phase 1", "Hybrid key exchange on internet-facing, long-lived systems with nothing in the way.", "highlight"),
    "phase2": ("Phase 2", "Hybrid or post-quantum on the other systems, once their blockers are fixed.", "plain"),
    "later": ("Later", "Kept classical for now, each with a review date.", "plain"),
    "wrapped": ("Wrapped", "Planned: a gateway in front does the post-quantum part. Shown separately.", "plain"),
    "not_placed": ("Not placed yet", "The status couldn't be measured, so there is no plan.", "dashed"),
}
BAND_WORDS = {"already": "already there", "phase1": "Phase 1", "phase2": "Phase 2", "later": "later", "wrapped": "wrapped", "not_placed": "not placed"}
# Config lines are either checked on real software (and say on what) or labelled as not checked.
NGINX_CHECKED = "Checked on nginx 1.31.8 with OpenSSL 3.5.9:"
NOT_CHECKED = "Not checked on real software:"
NGINX_HYBRID_LINE = "ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;"
APACHE_HYBRID_LINE = "SSLOpenSSLConfCmd Groups X25519MLKEM768:X25519:prime256v1"
APACHE_CHECKED: str | None = "Checked on Apache 2.4.71 with OpenSSL 3.5.9:"


def _t(value: str) -> dict:
    return {"t": "text", "v": value}


def _tag(value: str) -> dict:
    return {"t": "tag", "v": value}


def _m(value: str) -> dict:
    return {"t": "mono", "v": value}


def _line(*parts, fix_id: str | None = None) -> dict:
    return {"text": [(_t(p) if isinstance(p, str) else p) for p in parts], "fix_id": fix_id}


def _n(value: object) -> str:
    return f"{int(value):,}" if isinstance(value, (int, float)) else "not measured"


def _bytes(value: object) -> str:
    return f"{_n(value)} bytes" if isinstance(value, (int, float)) else "not measured"


def _ms(value: float) -> str:
    return f"{value:.2f} ms" if abs(value) < 1 else f"{value:.1f} ms"


def day(value: str | date | None) -> str:
    """A date as the screens write it: 14 Nov 2027."""
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return ""
    return f"{d.day} {d.strftime('%b %Y')}"


def option_title(kind: str, option: str) -> str:
    return (OPTION_TITLES if kind == "server" else PROGRAM_OPTION_TITLES)[option]


def _setting(state: dict, field: str) -> tuple[str, dict]:
    """A setting as words and its source tag: ("Long-lived data", tag "from the file")."""
    s = state["settings"][field]
    words = {("lifespan", "long"): "Long-lived", ("lifespan", "short"): "Short-lived", ("exposure", "internet"): "Internet-facing",
             ("exposure", "internal"): "Internal", ("can_change", "yes"): "It can be changed", ("can_change", "no"): "It can't be changed"}
    return words[(field, s["value"])], _tag(SOURCE_LABELS[s["source"]])


def file_settings(rows: list[tuple[str, str, str]]) -> list[dict]:
    """The settings an imported file gave, one line per system, for the Import screen. rows: (system name, field, value)."""
    by_system: dict[str, list[str]] = {}
    for name, field, value in rows:
        by_system.setdefault(name, []).append(f"{FIELD_LABELS[field].rstrip('?')}: {VALUE_LABELS[field][value].lower()}.")
    return [{"location": name, "text": " ".join(parts)} for name, parts in by_system.items()]


# ------------------------------------------------------------------ today

def status_of(state: dict) -> dict:
    code = state["status"] or ("not_measured" if state["code"] is None else "couldnt_check")
    return {"code": code, "label": STATUS_LABELS[code]}


def today_sentence(state: dict) -> str:
    code, detail = state["code"], state["detail"]
    it = "its status" if state["kind"] == "server" else "what it signs with"
    if code is None:
        return "Not measured yet. Press Measure status."
    if state["status"]:
        return present_pq.status_sentence(code, detail) if state["kind"] == "server" else str((state["result"] or {}).get("plain") or "")
    reason = state["reason_code"]
    if code == "couldnt_run":
        if reason == "not_a_demo_component":
            return "Couldn't check: only our own demo components can run in this version. So there is no status either way."
        if reason == "needs_isolated_mode":
            return ("Couldn't check: this is real software from outside, which runs only in isolated mode (Docker), and this run is in "
                    "demo mode. So there is no status either way.")
        if reason == "real_image_missing":
            return ("Couldn't check: this library's container image is not prepared on this computer (./run-demo.sh prepares it). "
                    "So there is no status either way.")
        if reason == "address_not_confirmed":
            return ("Couldn't check: you haven't confirmed you're allowed to test this address. Tick the box for it on Import, "
                    "then press Measure again.")
        if reason == "pq_engine_unavailable":
            return "Couldn't check: this computer's crypto library can't run post-quantum TLS. Nothing was guessed."
        if reason == "unclear_answer":
            return present_pq.unclear_sentence(detail)
        why = str(state["reason"] or "the measurement could not be run").rstrip(".")
        return f"Couldn't check {it}: {why}. So there is no status either way."
    return f"Couldn't check {it}: the measurement's own control didn't come out as it must, so its answer can't be relied on. Press Measure again."


def _facts(state: dict) -> list[dict]:
    if not state["status"]:
        return []
    detail = state["detail"]
    if state["kind"] == "server":
        return [{"label": f["label"], "value": [_t(f["text"])] + ([_t(" "), _tag(f["tag"])] if f["tag"] else [])}
                for f in present_pq.server_facts(detail, state["raw"])]
    out = [{"label": "It signs with", "value": [_t(str(detail.get("algorithm"))), _t(" "), _tag(MEASURED)]}]
    c = (detail.get("cost") or {}).get("component")
    if c:
        out += [{"label": "Signature size", "value": [_t(_bytes(c.get("signature_bytes"))), _t(" "), _tag(MEASURED)]},
                {"label": "Public key size", "value": [_t(_bytes(c.get("public_key_bytes"))), _t(" "), _tag(MEASURED)]},
                {"label": "Signing, median", "value": [_t(_ms(c["sign"]["median_ms"])), _t(" "), _tag(MEASURED)]}]
    return out


def _general_facts(state: dict) -> list[dict]:
    """The facts that belong to no one track (phase 4b): the TLS versions, and the container's second opinion."""
    if state["kind"] != "server":
        return []
    return [f for f in _facts(state) if f["label"] in ("TLS versions", "Second opinion (OpenSSL 3.5 container)")]


def _file_note(state: dict) -> str | None:
    claim = state["claim"]
    if not claim:
        return None
    said = f"this server is {claim['claimed']}" if state["kind"] == "server" else f"it signs with {claim['claimed']}"
    verify = {"True": " Verify marked that claim True.", "False": " Verify marked that claim False.",
              "Couldn't check": " Verify couldn't check that claim."}.get(claim.get("verify") or "", "")
    return f"The file says: {said}.{verify}"


# ------------------------------------------------------------------ cost

def _reference(detail: dict) -> dict:
    sizes = detail.get("sizes") or {}
    return {"classical": sizes.get("reference_classical") or {}, "hybrid": sizes.get("reference_hybrid") or {},
            "timing": detail.get("reference_timing") or {}, "client": detail.get("reference_classical_client")}


def _hybrid_cost(detail: dict) -> dict:
    """The numbers of the hybrid step for a server, each with where it came from: measured on the server when it
    offers hybrid, otherwise published sizes and what our own hybrid test server measured."""
    sizes, ref, pub = detail.get("sizes") or {}, _reference(detail), PQ_PUBLISHED["x25519_ml_kem_768"]
    own, timing = sizes.get("hybrid"), detail.get("timing") or {}
    if own:
        diff = timing.get("difference_ms") if timing.get("pairs") else None
        return {"client_share": (own.get("client_share_bytes"), MEASURED), "server_share": (own.get("server_share_bytes"), MEASURED),
                "hello": (own.get("client_hello_bytes"), MEASURED), "time": (diff, MEASURED, timing.get("beyond_noise")),
                "classical_hello": ((sizes.get("classical") or {}).get("client_hello_bytes"), MEASURED),
                "client": ("connects" if detail.get("classical_client") == "connects" else detail.get("classical_client"), MEASURED)}
    t = ref["timing"]
    return {"client_share": (pub["client_share_bytes"], pub["tag"]), "server_share": (pub["server_share_bytes"], pub["tag"]),
            "hello": (ref["hybrid"].get("client_hello_bytes"), OUR_SERVER),
            "time": (t.get("difference_ms") if t.get("pairs") else None, OUR_SERVER, t.get("beyond_noise")),
            "classical_hello": (ref["classical"].get("client_hello_bytes"), OUR_SERVER),
            "client": ("connects" if ref["client"] == "completed" else None, OUR_SERVER)}


def _time_words(value: object, beyond_noise: object) -> str:
    if not isinstance(value, (int, float)):
        return "not measured"
    if not beyond_noise:
        return "no difference beyond noise"
    return f"{'+' if value >= 0 else '−'}{_ms(abs(value))}"


def _cell(text: str, tag: str | None = None) -> list[dict]:
    return [_t(text)] + ([_t(" "), _tag(tag)] if tag else [])


def _server_cost(state: dict) -> dict | None:
    detail, status = state["detail"], state["status"]
    if not status:
        return None
    sizes, cert, timing = detail.get("sizes") or {}, detail.get("certificate") or {}, detail.get("timing") or {}
    classical, pure, hybrid = sizes.get("classical") or {}, sizes.get("pure") or {}, _hybrid_cost(detail)
    kem, dsa = PQ_PUBLISHED["ml_kem_768"], PQ_PUBLISHED["ml_dsa_65"]
    pq_cert = bool(cert.get("post_quantum"))
    none = _cell("not offered by this server")

    def today(text: str) -> str:
        return text + " (today)"

    def c(key: str) -> list[dict]:   # the classical column: only what was measured on this server
        return _cell(_bytes(classical.get(key)), MEASURED if classical.get(key) is not None else None) if classical else none

    def p(key: str, published: int, tag: str) -> list[dict]:   # the full post-quantum column
        return _cell(_bytes(pure[key]), MEASURED) if pure.get(key) is not None else _cell(_bytes(published), tag)

    def h(key: str) -> list[dict]:
        value, tag = hybrid[key][0], hybrid[key][1]
        return _cell(_bytes(value), tag if value is not None else None)

    classical_time = timing.get("classical_median_ms")
    rows = [
        {"label": "Key share, client to server", "cells": [c("client_share_bytes"), h("client_share"), p("client_share_bytes", kem["encapsulation_key_bytes"], kem["tag"])]},
        {"label": "Key share, server to client", "cells": [c("server_share_bytes"), h("server_share"), p("server_share_bytes", kem["ciphertext_bytes"], kem["tag"])]},
        {"label": "First handshake message", "cells": [c("client_hello_bytes"), h("hello"),
                                                        _cell(_bytes(pure["client_hello_bytes"]), MEASURED) if pure.get("client_hello_bytes") else _cell("not measured")]},
        {"label": "Certificate public key",
         "cells": [none if pq_cert else _cell(_bytes(cert.get("public_key_bytes")), MEASURED if cert.get("public_key_bytes") else None),
                   none if pq_cert else _cell("no change"),
                   _cell(_bytes(cert.get("public_key_bytes")), MEASURED) if pq_cert and cert.get("public_key_bytes") else _cell(_bytes(dsa["public_key_bytes"]), dsa["tag"])]},
        {"label": "Handshake signature",
         "cells": [none if pq_cert else c("signature_bytes"), none if pq_cert else _cell("no change"),
                   _cell(_bytes(pure["signature_bytes"]), MEASURED) if pure.get("signature_bytes") else _cell(_bytes(dsa["signature_bytes"]), dsa["tag"])]},
        {"label": f"Handshake time, median of {timing.get('handshakes') or 10}",
         "cells": [_cell(_ms(classical_time), MEASURED) if isinstance(classical_time, (int, float)) else (none if not classical else _cell("not measured")),
                   _cell(_time_words(hybrid["time"][0], hybrid["time"][2]), hybrid["time"][1] if hybrid["time"][0] is not None else None),
                   _cell("not measured")]},
        {"label": "A classical-only client still connects",
         "cells": [_cell("Yes", MEASURED) if detail.get("classical_client") == "connects" else
                   _cell("No", MEASURED) if detail.get("classical_client") == "cannot" else _cell("Not clear"),
                   _cell("Yes", hybrid["client"][1]) if hybrid["client"][0] == "connects" else _cell("Not measured"),
                   _cell("No", MEASURED) if status == "pq_only" else _cell("No: there is no classical fallback")]},
    ]
    columns = ["", "Classical", "Hybrid", "Full post-quantum"]
    columns[{"classical": 1, "hybrid": 2, "pq_only": 3}[status]] = today(columns[{"classical": 1, "hybrid": 2, "pq_only": 3}[status]])
    note = {"classical": "This server doesn't offer hybrid yet, so the hybrid column can't be measured on it. “Our test server” is the hybrid test "
                         "server this app runs on this computer.",
            "hybrid": "The classical and hybrid columns were both measured on this server. Handshake times are the median of handshakes taken in turn.",
            "pq_only": "This server accepts only post-quantum key exchange, so the classical column can't be measured on it."}[status]
    return {"title": "Cost of going post-quantum",
            "intro": "Sizes and times for this server today, and what each step would change. Every number says where it came from.",
            "columns": columns, "rows": rows,
            "note": f"{note} Published sizes: ML-KEM-768 (FIPS 203) and ML-DSA-65 (FIPS 204)."}


def _program_numbers(state: dict) -> dict | None:
    cost = state["detail"].get("cost") or {}
    c, m = cost.get("component"), cost.get("mldsa65")
    return {"c": c, "m": m} if c and m else None


def _program_cost(state: dict) -> dict | None:
    numbers = _program_numbers(state)
    if not state["status"] or numbers is None:
        return None
    c, m, algorithm = numbers["c"], numbers["m"], state["detail"].get("algorithm")
    both = "this program plus the reference library"

    def row(label: str, key: str) -> dict:
        return {"label": label, "cells": [_cell(_bytes(c[key]), MEASURED), _cell(_bytes(c[key] + m[key]), both), _cell(_bytes(m[key]), REFERENCE)]}

    def time_row(label: str, op: str) -> dict:
        return {"label": label, "cells": [_cell(_ms(c[op]["median_ms"]), MEASURED), _cell(_ms(c[op]["median_ms"] + m[op]["median_ms"]), both),
                                          _cell(_ms(m[op]["median_ms"]), REFERENCE)]}
    return {"title": "Cost of going post-quantum",
            "intro": "Sizes and times for this program today, and what each step would change. Every number says where it came from.",
            "columns": ["", f"{algorithm} (today)", "Hybrid: both signatures", "ML-DSA-65 only"],
            "rows": [row("Signature size", "signature_bytes"), row("Public key size", "public_key_bytes"),
                     time_row("Signing, median", "sign"), time_row("Checking, median", "verify")],
            "note": ("The ML-DSA-65 column is the reference library on this computer, not software of yours, so the times are for scale only. "
                     "The hybrid column is the two added together. Published sizes for ML-DSA-65 (FIPS 204): signature 3,309 bytes, public key 1,952 bytes.")}


# ------------------------------------------------------------------ recommendation

def _nist() -> list:
    return [f"NIST dates: today's public-key algorithms are deprecated after {PQ_DATES['deprecated_after']} and disallowed after "
            f"{PQ_DATES['disallowed_after']} ", _tag(PQ_DATES["tag"]), "."]


def _reasons(state: dict) -> list[list[dict]]:
    rec, detail = state["recommendation"], state["detail"]
    rule = rec["rule"]
    life, life_tag = _setting(state, "lifespan")
    expo, expo_tag = _setting(state, "exposure")
    change, change_tag = _setting(state, "can_change")
    hybrid = _hybrid_cost(detail) if state["kind"] == "server" else {}
    out: list[list] = []
    compat = (["With hybrid on, a classical-only client still connects ", _tag(OUR_SERVER), ". It can't be measured on this server until hybrid is on."]
              if hybrid and hybrid["client"][0] == "connects" else
              ["Whether a classical-only client still connects with hybrid on could not be measured ", _tag(NOT_MEASURED), "."])
    review = state.get("default_review_date")
    keep_date = [f"Keeping classical is a decision with a date, never “forever”: review by {day(review)} ", _tag("assumed: 12 months"),
                 f". The latest allowed is {day(rules.LATEST_REVIEW)}, NIST's date."]
    if rule == "long_lived":
        out.append([f"{life} data ", life_tag, ": traffic recorded today could be decrypted later, if a large quantum computer is built."])
        if state["settings"]["exposure"]["value"] == "internet":
            out.append([f"{expo} ", expo_tag, ": anyone on the path can record it."])
        out += [compat, _nist()]
    elif rule == "internet_facing":
        out += [[f"{expo} ", expo_tag, ": anyone on the path can record its traffic."],
                [f"{life} data ", life_tag, ", so there is less to protect for long. The cost table shows what hybrid adds."], compat, _nist()]
    elif rule == "short_internal":
        out += [[f"{life} data ", life_tag, " and ", expo.lower(), " ", expo_tag, ": a connection recorded today has little to give away later."], keep_date]
    elif rule == "cant_change_exposed":
        out.append([f"{change} ", change_tag, ", so the post-quantum part has to be done in front of it, by a gateway."])
        if state["settings"]["lifespan"]["value"] == "long":
            out.append([f"{life} data ", life_tag, ": traffic recorded today could be decrypted later, if a large quantum computer is built."])
        if state["settings"]["exposure"]["value"] == "internet":
            out.append([f"{expo} ", expo_tag, ": anyone on the path can record it."])
        out.append(["Wrapping protects the connection only, not cryptography inside the application (for example signing)."])
    elif rule == "cant_change_low":
        out += [[f"{change} ", change_tag, ". ", f"{life} data ", life_tag, " and ", expo.lower(), " ", expo_tag,
                 ": a connection recorded today has little to give away later."], keep_date]
    elif rule == "already_hybrid":
        group = (detail.get("hybrid_groups") or ["a hybrid group"])[0] if state["kind"] == "server" else None
        out.append([f"It already offers hybrid key exchange ({group}) ", _tag(MEASURED), "."] if group else ["It already signs with both ", _tag(MEASURED), "."])
        if detail.get("classical_client") == "connects":
            out.append(["A classical-only client still connects ", _tag(MEASURED), "."])
        out.append(["Full post-quantum is not recommended yet: every client would have to support it, and this app can't see your clients."])
    elif rule == "already_pq_only":
        if state["kind"] == "server":
            cert = detail.get("certificate") or {}
            with_cert = f", with an {cert.get('name')} certificate" if cert.get("post_quantum") else ""
            out += [[f"It already accepts only post-quantum key exchange ({present_pq.group_words(detail.get('pure_group'))}){with_cert} ", _tag(MEASURED), "."],
                    ["A classical-only client can't connect ", _tag(MEASURED), ". Check that every client that needs this server supports it."]]
        else:
            out.append([f"It already signs with a post-quantum algorithm ({detail.get('algorithm')}) ", _tag(MEASURED), "."])
    elif rule == "long_lived_signatures":
        algorithm = detail.get("algorithm")
        out += [[f"{life} signatures ", life_tag, f": a signature made today has to be trusted after {PQ_DATES['deprecated_after']}, when NIST deprecates "
                 f"{algorithm} ", _tag(PQ_DATES["tag"]), "."],
                ["Signing with both today's algorithm and a post-quantum one keeps today's verifiers working."]]
        numbers = _program_numbers(state)
        if numbers:
            out.append([f"An ML-DSA-65 signature is {_bytes(numbers['m']['signature_bytes'])} ", _tag(REFERENCE),
                        f" against {_bytes(numbers['c']['signature_bytes'])} today ", _tag(MEASURED), "."])
    elif rule == "short_lived_signatures":
        out += [[f"{life} signatures ", life_tag, ": they stop mattering before NIST's dates."], keep_date]
    return [[(_t(p) if isinstance(p, str) else p) for p in line] for line in out]


def reasons_plain(state: dict) -> list[str]:
    """The same reasons as plain strings (tags in square brackets), for the evidence download."""
    if not state["recommendation"]:
        return []
    return ["".join(f"[{p['v']}]" if p["t"] == "tag" else p["v"] for p in line) for line in _reasons(state)]


def _plain(parts: list[dict]) -> str:
    return "".join(f"[{p['v']}]" if p["t"] == "tag" else p["v"] for p in parts)


def _recommendation(state: dict) -> dict:
    rec = state["recommendation"]
    if rec is None:
        return {"title": "No recommendation yet", "tag": None, "reasons": [], "evidence": None, "evidence_link": None,
                "none_text": ("There is no recommendation, because the status couldn't be measured. Nothing is recommended from a guess."
                              if state["code"] is not None else "Measure the status first: a recommendation starts from what was measured.")}
    title = option_title(state["kind"], rec["option"])
    what = "this server" if state["kind"] == "server" else "this program"
    evidence = [_t(f"Evidence: {what} measured {STATUS_LABELS[state['status']]} "), _tag(MEASURED)]
    return {"title": f"Recommended: {title}" + (" (in place today)" if rec["in_place"] else ""), "tag": RULES_TAG,
            "reasons": _reasons(state), "evidence": evidence, "evidence_link": "See the evidence", "none_text": None}


# ------------------------------------------------------------------ the four options

def _blocker_line(state: dict, code: str, fix_id: str | None) -> dict:
    detail = state["detail"]
    if code == "no_tls13":
        versions = join_and(list(detail.get("tls_versions") or [])) or "no TLS 1.3"
        return _line(f"It doesn't accept TLS 1.3, which post-quantum key exchange needs (it accepts {versions}) ", _tag(MEASURED), ".", fix_id=fix_id)
    if code == "weak_certificate":
        cert = detail.get("certificate") or {}
        return _line(f"Its certificate ({cert.get('name')}) is below NIST's minimum of {cert.get('minimum_bits')} bits ", _tag(MEASURED), ".", fix_id=fix_id)
    return _line(f"It signs with {detail.get('algorithm')} only: it can't make post-quantum signatures ", _tag(MEASURED), ".", fix_id=fix_id)


def _check_first(kind: str) -> dict:
    """Full post-quantum has no fallback, so there is something to check that this app cannot measure. It is said as a
    thing to do, not as a blocker: a blocker is only something measured that must be fixed before the change."""
    if kind == "server":
        return _line("Check that every client supports it. This app can't see your clients ", _tag(NOT_MEASURED), ".")
    return _line("Check that everyone who checks its signatures supports ML-DSA. This app can't see them ", _tag(NOT_MEASURED), ".")


def _review_line(state: dict) -> dict:
    choice = state["choice"]
    if choice and choice["option"] == "keep" and choice.get("review_date"):
        return _line(f"Review date: {day(choice['review_date'])} ", _tag("chosen by you"), f". Latest allowed: {day(rules.LATEST_REVIEW)}, NIST's date.")
    return _line(f"Review date: {day(state.get('default_review_date'))} ", _tag("assumed: 12 months"),
                 f". Latest allowed: {day(rules.LATEST_REVIEW)}, NIST's date.")


def _server_option(state: dict, option: str) -> tuple[str, list[dict]]:
    """(what it is, the sections) of one option card for a server."""
    detail, status = state["detail"], state["status"]
    sizes, cert = detail.get("sizes") or {}, detail.get("certificate") or {}
    classical, hybrid = sizes.get("classical") or {}, _hybrid_cost(detail)
    own_hybrid = bool(sizes.get("hybrid"))   # the hybrid numbers were measured on this server itself
    kem, dsa = PQ_PUBLISHED["ml_kem_768"], PQ_PUBLISHED["ml_dsa_65"]
    blocking = [_blocker_line(state, code, state["fix_ids"].get(code) if state["plan_option"] == option else None) for code in state["blockers"][option]]
    none = [_line("None measured.")]
    if rules.in_place(status, option):
        blocking, none = [], [_line("None: it is in place today.")]
    if option == "keep":
        cost = ([_line(f"Nothing changes. Key shares stay {_bytes(classical.get('client_share_bytes'))} ", _tag(MEASURED), ".")]
                if classical.get("client_share_bytes") is not None else [_line("Nothing changes.")])
        return ("No change now. It always has a review date, never “forever”.",
                [{"title": "Cost", "lines": cost}, {"title": "Blockers", "lines": none},
                 {"title": "To manage", "lines": [_line("Algorithms 2 (key exchange, certificate) · Key sets 1 · Libraries 1"), _review_line(state)]}])
    if option == "hybrid":
        cs, ss, hello, time = hybrid["client_share"], hybrid["server_share"], hybrid["hello"], hybrid["time"]
        before = classical.get("client_share_bytes")
        cost = []
        if before is not None and not own_hybrid:
            cost.append(_line(f"Key shares today: {_n(before)} bytes (client) and {_n(classical.get('server_share_bytes'))} bytes (server) ", _tag(MEASURED), "."))
        cost.append(_line(f"Key shares with hybrid: {_n(cs[0])} bytes (client) and {_n(ss[0])} bytes (server) ", _tag(cs[1]), "."))
        if hello[0] is not None:
            was = hybrid["classical_hello"][0]
            cost.append(_line((f"First message {_n(was)} → {_n(hello[0])} bytes " if was is not None else f"First message {_n(hello[0])} bytes "),
                              _tag(hello[1]), ". A client that sends more options, as a browser does, sends a bigger one."))
        if time[0] is not None:
            cost.append(_line(("About " + _time_words(time[0], time[2]) + " per handshake " if time[2] else "No time difference beyond noise "), _tag(time[1]), "."))
        cost.append(_line("Plainly: two algorithms in every key exchange, two key shares, bigger messages, more to keep up to date."))
        sections = [{"title": "Cost", "lines": cost}]
        if not rules.in_place(status, option):
            howto = state["fix_ids"].get("howto") if state["plan_option"] == option else None
            sections.append({"title": "To do", "lines": [_line("Turn on hybrid key exchange. This is the change itself, not a blocker." if howto else
                                                               "Turn on hybrid key exchange. Choose this option to get the how-to in Fixes.", fix_id=howto)]})
        sections += [{"title": "Blockers", "lines": blocking or none},
                     {"title": "To manage", "lines": [_line("Algorithms 3 · Key sets 1, plus 2 key shares per connection · Libraries 1 (a version with ML-KEM)")]}]
        return "Post-quantum key exchange added to the classical one. Clients that can't do it keep working.", sections
    if option == "full_pq":
        cost = [_line(f"Key shares {_n(kem['encapsulation_key_bytes'])} and {_n(kem['ciphertext_bytes'])} bytes; certificate key {_n(dsa['public_key_bytes'])} bytes; "
                      f"handshake signature {_n(dsa['signature_bytes'])} bytes ", _tag("published: FIPS 203, FIPS 204"), ".")]
        todo = []
        if status != "pq_only":
            todo.append(_check_first("server"))
            todo.append(_line("Accept ML-KEM by itself, and switch the classical and hybrid key exchanges off."))
            if not cert.get("post_quantum"):
                todo.append(_line(f"Replace the {cert.get('name') or 'classical'} certificate with an ML-DSA one."))
        sections = [{"title": "Cost", "lines": cost}] + ([{"title": "To do", "lines": todo}] if todo else [])
        sections += [{"title": "Blockers", "lines": blocking or none},
                     {"title": "To manage", "lines": [_line("Algorithms 2 · Key sets 1 (new) · Libraries: this server's and every client's")]}]
        return "Post-quantum algorithms only. Every connected system must support them, and there is no classical fallback.", sections
    return ("A gateway or network encryptor in front does the post-quantum part. For systems that can't be changed. It protects the connection only, "
            "not cryptography inside the application (for example signing).",
            [{"title": "Cost", "lines": [_line("It depends on the gateway ", _tag(NOT_MEASURED), ".")]},
             {"title": "Blockers", "lines": [_line("None measured. A gateway has to be bought or built, and run.")]},
             {"title": "To manage", "lines": [_line("Algorithms: this server's 2, plus the gateway's · Key sets +1 · Libraries +1")]}])


def _program_option(state: dict, option: str) -> tuple[str, list[dict]]:
    detail, numbers = state["detail"], _program_numbers(state)
    algorithm = detail.get("algorithm")
    blocking = [_blocker_line(state, code, state["fix_ids"].get(code) if state["plan_option"] == option else None) for code in state["blockers"][option]]
    none = [_line("None measured.")]
    if rules.in_place(state["status"], option):
        blocking, none = [], [_line("None: it is in place today.")]
    c, m = (numbers["c"], numbers["m"]) if numbers else (None, None)
    if option == "keep":
        cost = [_line(f"Nothing changes. Signatures stay {_bytes(c['signature_bytes'])} ", _tag(MEASURED), ".")] if c else [_line("Nothing changes.")]
        return ("No change now. It always has a review date, never “forever”.",
                [{"title": "Cost", "lines": cost}, {"title": "Blockers", "lines": none},
                 {"title": "To manage", "lines": [_line("Algorithms 1 · Key sets 1 · Libraries 1"), _review_line(state)]}])
    if option == "hybrid":
        cost = ([_line(f"Signature {_n(c['signature_bytes'])} + {_n(m['signature_bytes'])} = {_n(c['signature_bytes'] + m['signature_bytes'])} bytes; public key "
                       f"{_n(c['public_key_bytes'])} + {_n(m['public_key_bytes'])} = {_n(c['public_key_bytes'] + m['public_key_bytes'])} bytes ",
                       _tag("this program plus the reference library"), "."),
                 _line(f"Signing takes about {_ms(m['sign']['median_ms'])} more ", _tag(REFERENCE), ".")] if c and m else
                [_line(f"An ML-DSA-65 signature adds {_n(PQ_PUBLISHED['ml_dsa_65']['signature_bytes'])} bytes ", _tag(PQ_PUBLISHED["ml_dsa_65"]["tag"]), ".")])
        cost.append(_line("Plainly: two signatures on everything, two key sets to look after, bigger files or messages."))
        return (f"Every signature is made twice: with {algorithm} and with ML-DSA. Verifiers that only know {algorithm} keep working.",
                [{"title": "Cost", "lines": cost}, {"title": "Blockers", "lines": blocking or none},
                 {"title": "To manage", "lines": [_line("Algorithms 2 · Key sets 2 · Libraries 1 or 2")]}])
    cost = ([_line(f"Signature {_n(c['signature_bytes'])} → {_n(m['signature_bytes'])} bytes; public key {_n(c['public_key_bytes'])} → {_n(m['public_key_bytes'])} bytes ",
                   _tag(REFERENCE), ".")] if c and m else
            [_line(f"Signature {_n(PQ_PUBLISHED['ml_dsa_65']['signature_bytes'])} bytes ", _tag(PQ_PUBLISHED["ml_dsa_65"]["tag"]), ".")])
    todo = [] if rules.in_place(state["status"], option) else [{"title": "To do", "lines": [_check_first("software")]}]
    return ("ML-DSA signatures only. Everyone who checks them must support ML-DSA, and there is no classical fallback.",
            [{"title": "Cost", "lines": cost}, *todo, {"title": "Blockers", "lines": blocking or none},
             {"title": "To manage", "lines": [_line("Algorithms 1 · Key sets 1 (new) · Libraries: this program's and every verifier's")]}])


def _not_offered(state: dict, option: str) -> str | None:
    kind, status = state["kind"], state["status"]
    if option == "wrap" and kind != "server":
        return "Doesn't apply: wrapping protects a connection, not signatures made inside a program."
    if option in state["offered"]:
        return None
    what = "server" if kind == "server" else "program"
    already = {"hybrid": f"this {what} is already Hybrid", "pq_only": f"this {what} is already Post-quantum only"}.get(status, "")
    return f"Doesn't apply: {already}." if already else "Doesn't apply."


def _options(state: dict, today: date) -> list[dict]:
    if not state["status"]:
        return []
    rec, choice = state["recommendation"], state["choice"]
    out = []
    for option in rules.OPTIONS:
        title = option_title(state["kind"], option)
        not_offered = _not_offered(state, option)
        if not_offered and option == "wrap" and state["kind"] != "server":
            what, sections = ("A gateway or network encryptor in front does the post-quantum part. It protects the connection only.", [])
        else:
            what, sections = (_server_option if state["kind"] == "server" else _program_option)(state, option)
        recommended, chosen = bool(rec and rec["option"] == option), bool(choice and choice["option"] == option)
        tags = (["Recommended"] if recommended else []) + (["Your choice"] if chosen else []) + \
               (["In place today"] if rules.in_place(state["status"], option) else [])
        choose = None
        if not not_offered:
            review = None
            if option == "keep":
                start = (choice or {}).get("review_date") if chosen else None
                review = {"label": "Review date", "value": str(start or state["default_review_date"]),
                          "min": date.fromordinal(today.toordinal() + 1).isoformat(), "max": rules.LATEST_REVIEW.isoformat(),
                          "help": f"Never “forever”. Latest allowed: {day(rules.LATEST_REVIEW)}, NIST's date."}
            choose = {"title": f"Choose “{title}”", "needs_reason": not recommended,
                      "reason_label": ("Your reason (needed, because this differs from the recommendation)" if not recommended
                                       else "Your reason (optional)"),
                      "review_date": review, "save": "Save choice", "cancel": "Cancel",
                      "note": "Your choice is recorded with the time and is never overwritten. The roadmap follows it."}
        out.append({"key": option, "title": title, "tags": tags, "highlighted": chosen if choice else recommended, "what": what,
                    "sections": sections, "not_offered": not_offered, "choose_label": "Choose this option", "choose": choose})
    return out


def choice_line(kind: str, choice: dict) -> str:
    line = f"Your choice: {option_title(kind, choice['option'])}, saved {day(choice['at'])} (UTC)."
    if choice.get("review_date"):
        line += f" Review date: {day(choice['review_date'])}."
    return line + (f" Your reason: {choice['reason']}" if choice.get("reason") else " No reason given.")


def plan_line(state: dict) -> str:
    view = state.get("change_view")
    change_line = None
    if view and view["badge"]["label"] not in ("Ready to try", "Text only", "Ready to download"):
        short = {"keep": "Keep classical", "hybrid": "Hybrid", "full_pq": "Full post-quantum", "wrap": "Wrap the connection"}.get(state["plan_option"], "")
        change_line = f"{'Your choice' if state['plan_source'] == 'choice' else 'Recommended'}: {short} · {view['badge']['label'][0].lower() + view['badge']['label'][1:]}"
    return present_tracks.plan_line(state, change_line)


# ------------------------------------------------------------------ the roadmap

def roadmap_note(state: dict, track: str | None = None, band: str | None = None) -> dict:
    detail, option = state["detail"], state["plan_option"]
    band = band or next(iter(state["track_bands"].values()))
    if band == "not_placed":
        return _line(today_sentence(state))
    if band == "target":
        if track == "signatures":
            return _line(f"Signs with {detail.get('algorithm')} ", _tag(MEASURED), ".")
        if track == "auth":
            auth = detail.get("auth") or {}
            return _line(f"{auth.get('certificate')} certificate and {auth.get('signature')} handshake signature ", _tag(MEASURED), ".")
        return _line(f"Accepts only {present_pq.group_words(detail.get('pure_group'))} ", _tag(MEASURED), ".")
    if band == "done_for_now":
        still = " Classical-only clients still connect " if detail.get("classical_client") == "connects" else " "
        return _line(f"Offers {(detail.get('hybrid_groups') or ['hybrid'])[0]}. Next: post-quantum only, once every client supports it.{still}",
                     _tag(MEASURED), ".")
    if track == "auth" and band == "phase2":
        if option == "full_pq":
            return _line("Part of the Full post-quantum change (an ML-DSA certificate).", fix_id=state["fix_ids"].get("howto"))
        return _line("An ML-DSA certificate, once your clients can check one. After key exchange; in this version it comes with Full post-quantum.")
    if band in ("phase1", "phase2"):
        fixable = [c for c in state["blockers"][option] if c in rules.FIXABLE_BLOCKERS]
        if fixable:
            first = _blocker_line(state, fixable[0], state["fix_ids"].get(fixable[0]) or state["fix_ids"].get("howto"))
            return {"text": [_t("Blocker: " + first["text"][0]["v"][0].lower() + first["text"][0]["v"][1:])] + first["text"][1:], "fix_id": first["fix_id"]}
        todo = {("server", "hybrid"): "turn on hybrid key exchange", ("server", "full_pq"): "move to post-quantum key exchange and certificate only",
                ("software", "hybrid"): "sign with both algorithms", ("software", "full_pq"): "sign with ML-DSA only"}[(state["kind"], option)]
        tail = {("server", "full_pq"): " First check that every client supports it: this app can't see them.",
                ("software", "full_pq"): " First check that everyone who checks its signatures supports ML-DSA."}.get((state["kind"], option), "")
        return _line(f"To do: {todo}.{tail}", fix_id=state["fix_ids"].get("howto"))
    if band == "later":
        review = state.get("review_date") or {}
        life, _ = _setting(state, "lifespan")
        expo, _ = _setting(state, "exposure")
        return _line(f"Review by {day(review.get('value'))} ", _tag("chosen by you" if review.get("source") == "chosen" else "assumed: 12 months"),
                     f" · {life.lower()} data, {expo.lower()}.")
    source = state["settings"]["can_change"]
    why = {"file": "The file marks it as one that can't be changed.", "user": "You marked it as one that can't be changed.",
           "assumed": ""}[source["source"]] if source["value"] == "no" else ""
    return _line(f"{why} Protects the connection only, not cryptography inside the application.".strip())


def roadmap_rows(state: dict) -> list[tuple[str, dict]]:
    """(band, row) for each track of one system (phase 4b). A system kept classical, wrapped, or not measured has one row
    for both tracks; otherwise each track has its own row and its own place."""
    tag = None if not state["status"] else "chosen by you" if state["plan_source"] == "choice" else "recommended, not yet chosen by you"
    base = {"system_key": state["key"], "kind_label": kind_label(state), "name": state["name"], "plan_tag": tag}
    bands, statuses, option = state["track_bands"], state["tracks"], state["plan_option"]
    both = state["kind"] == "server" and (len(set(bands.values())) == 1 and next(iter(bands.values())) in ("later", "wrapped", "not_placed"))
    if both or state["kind"] == "software" and next(iter(bands.values())) == "not_placed":
        band = next(iter(bands.values()))
        option_words = option_title(state["kind"], option) if state["status"] and option else "No option yet"
        return [(band, {**base, "track": "Both tracks" if state["kind"] == "server" else "Signatures", "option": option_words,
                        "plan_tag": tag if band != "not_placed" else None, "note": roadmap_note(state, None, band)})]
    out = []
    for track, band in bands.items():
        status = statuses[track]
        out.append((band, {**base, "track": present_tracks.TRACK_TITLES[track][1], "option": _track_option(state, track, status, band),
                           "plan_tag": tag if band not in ("target",) else None, "note": roadmap_note(state, track, band)}))
    return out


def _track_option(state: dict, track: str, status: str | None, band: str) -> str:
    label = present_tracks.TRACK_LABELS.get(status or "", "")
    option = state["plan_option"]
    if band in ("target", "done_for_now"):
        return label
    if track == "kex":
        goal = {"hybrid": "Hybrid", "full_pq": "Post-quantum only"}.get(option, option_title("server", option))
        return f"{label} → {goal}"
    if track == "auth":
        return f"{label} → ML-DSA certificate"
    return f"{label} → {option_title('software', option)}"


def _roadmap(states: list[dict], download: dict) -> dict:
    chosen = sum(1 for s in states if s["choice"])
    placed = [s for s in states if s["status"]]
    rows = [(band, row) for s in states for band, row in roadmap_rows(s)]
    n_tracks = sum(len(s["tracks"]) for s in states)
    at_target = sum(1 for s in states for b in s["track_bands"].values() if b == "target")
    intro = (f"Every track of every system has a place: {n_tracks} tracks, {at_target} at the target. "
             f"Built from your choices: {chosen} of {len(states)} chosen" + (", so the rest use the recommendation" if chosen < len(placed) else "")
             + ". It updates when a choice, a setting or a measurement changes.")
    bands = []
    for key, (title, sub, look) in present_tracks.BANDS.items():
        in_band = [row for band, row in rows if band == key]
        if in_band:
            bands.append({"key": key, "title": title, "sub": sub, "look": look, "rows": in_band})
    return {"intro": intro, "download": {"label": "Download evidence", **download}, "bands": bands}


# ------------------------------------------------------------------ the whole step

def kind_label(state: dict) -> str:
    return "Server" if state["kind"] == "server" else "Signing program"


def _settings_view(state: dict, enabled: bool) -> dict:
    helps = {"lifespan": "How long must what it carries stay private?" if state["kind"] == "server" else "How long must its signatures stay trusted?",
             "exposure": "Who can reach it or record its traffic?", "can_change": "Can its software or settings be updated?"}
    fields = [{"field": f, "label": FIELD_LABELS[f], "help": helps[f], "value": state["settings"][f]["value"],
               "options": [{"value": v, "label": VALUE_LABELS[f][v]} for v in rules.FIELDS[f]],
               "source": SOURCE_LABELS[state["settings"][f]["source"]], "enabled": enabled} for f in rules.FIELDS]
    return {"title": "About this system", "intro": "The recommendation uses these three settings. Change any that is wrong.", "fields": fields}


def system_view(state: dict, today: date, busy: bool) -> dict:
    result = state["result"]
    if result is not None and not state["status"]:
        # In this step a measurement that gave no status reads "Couldn't check", as in Verify.
        result = {**result, "label": result["label"].replace("Couldn't run", "Couldn't check")}
    choice = state["choice"]
    return {
        "key": state["key"], "kind_label": kind_label(state), "name": state["name"], "status": status_of(state), "plan_line": plan_line(state),
        "measuring": state["job"],
        "today": {"title": "Today, on two tracks" if state["kind"] == "server" else "Today", "sentence": today_sentence(state),
                  "file_note": _file_note(state), "facts": _general_facts(state),
                  "control_line": (result or {}).get("control", {}).get("line") if state["status"] else None,
                  "details_label": "Details and evidence", "result": result},
        "settings": _settings_view(state, enabled=not busy),
        "cost": (_server_cost(state) if state["kind"] == "server" else _program_cost(state)),
        "recommendation": _recommendation(state),
        "options_title": "The four options", "options": _options(state, today),
        # phase 4b: two tracks and a target, the Also noticed notes, and the change ready to apply
        "tracks": present_tracks.track_views(state), "tracks_brief": present_tracks.tracks_brief(state) if (state["status"] or state["code"] is not None) else [],
        "target_line": present_tracks.target_line(state), "also_noticed_title": "Also noticed",
        "also_noticed": present_tracks.also_noticed(state), "change": state.get("change_view"),
        "choice": {"line": choice_line(state["kind"], choice), "history": [choice_line(state["kind"], c) for c in state["history"]]} if choice else None,
        "choices_note": (("The roadmap uses your choice. A new measurement or recommendation never changes it." if state["choice_applies"] else
                          f"Your choice no longer applies, because this system now measures {status_of(state)['label']}. It stays in the "
                          "record, and the roadmap uses the recommendation until you choose again.") if choice else
                         "Until you choose, the roadmap uses the recommendation and says so." if state["status"] else ""),
    }


def view(*, plan_id: int, import_id: int, is_demo: bool, filename: str, states: list[dict], busy: bool, finished: int,
         measured_at: str | None, today: date, download: dict) -> dict:
    n = len(states)
    subline = [_t("Where each system in "), _m(filename), _t(" stands on the move to post-quantum cryptography, what each option costs, and a plan.")]
    if measured_at:
        subline += [_t(" Measured "), {"t": "time", "v": measured_at}, _t(".")]
    elif n:
        subline.append(_t(" Not measured yet."))
    any_measured = any(s["code"] is not None for s in states)
    return {
        "plan_id": plan_id, "import_id": import_id, "is_demo": is_demo, "title": TITLE, "subline": subline, "disclaimer": DISCLAIMER, "busy": busy,
        "measure": {"label": "Measure again" if any_measured else "Measure status", "enabled": bool(n) and not busy,
                    "blocked_reason": "A measurement is running." if busy else None if n else "The file names nothing that can be measured.",
                    "progress_text": f"Measuring: {finished} of {n} systems finished." if busy else None},
        "tabs": {"systems": f"Systems · {n}", "roadmap": "Roadmap"}, "list_title": f"Systems in the file ({n})",
        "empty_text": None if n else "This file names no server and no signing program, so there is nothing to plan a migration for.",
        "systems": [system_view(s, today, busy) for s in states],
        "roadmap": _roadmap(states, download),
    }


# ------------------------------------------------------------------ Fixes entries (text only)

def _where_hybrid() -> dict:
    apache = APACHE_CHECKED or NOT_CHECKED
    return {"title": "Where the setting lives", "note": "Use the row that matches how TLS is handled for this server.",
            "columns": ["Where TLS is set up", "The setting", "To add hybrid key exchange"],
            "rows": [
                {"place": "nginx", "setting": "the `ssl_ecdh_curve` line (in the `http` block, or in the site's own `server` block)",
                 "lead": NGINX_CHECKED, "code": NGINX_HYBRID_LINE},
                {"place": "Apache", "setting": "an `SSLOpenSSLConfCmd Groups` line (in the main server config, or in the virtual host)",
                 "lead": apache, "code": APACHE_HYBRID_LINE},
                {"place": "Your own application", "setting": "the list of key-exchange groups in your application's TLS settings",
                 "lead": f"{NOT_CHECKED[:-1]}. With OpenSSL 3.5 or newer, for example:", "code": 'SSL_CTX_set1_groups_list(ctx, "X25519MLKEM768:X25519:P-256");'},
            ],
            "after": ["With nginx 1.31.8 or Apache 2.4.71 on OpenSSL 3.5.9, a site with no such line already offers hybrid, and a line that leaves "
                      "`X25519MLKEM768` out switches it off (both checked). So if the server has such a line, change it rather than adding another.",
                      "On a TLS library older than OpenSSL 3.5 this line stops nginx from starting (checked on nginx 1.24.0 with OpenSSL 3.0.13: "
                      "the config test fails). Check the library version first.",
                      "Reload the server, then press Measure again in the Migration step. This entry closes when the measurement reads Hybrid."]}


def _fix_words(state: dict, what: str) -> dict:
    """The words of one migration entry in Fixes. `what`: "howto" (the change itself) or a blocker code."""
    detail, name, option = state["detail"], state["name"], state["plan_option"]
    hybrid = _hybrid_cost(detail) if state["kind"] == "server" else {}
    if what == "howto" and option == "hybrid":
        hello, was = hybrid["hello"], hybrid["classical_hello"]
        grows = (f"the first handshake message grows from about {_n(was[0])} to about {_n(hello[0])} bytes ({hello[1]}), and a client that sends "
                 "more options, as a browser does, sends a bigger one. A few old network devices drop a first message that no longer fits in one "
                 "network packet, so test from where your clients connect."
                 if hello[0] is not None and was[0] is not None else
                 "the first handshake message grows a lot. A few old network devices drop a first message that no longer fits in one network "
                 "packet, so test from where your clients connect.")
        return {"title": f"Turn on hybrid key exchange on {name}", "line": "A warning first, then where the setting lives",
                "what": ("A server setting, not a code change: add the hybrid key exchange X25519MLKEM768 next to the classical ones. "
                         "The suggestion below says where the setting lives. The app has not made this change."),
                "suggestion": {"intro": ["This is the change itself, not a blocker: nothing that was measured stands in its way.",
                                         "It needs a TLS library that knows ML-KEM, such as OpenSSL 3.5 or newer. Clients that can't do hybrid keep "
                                         "connecting with the classical key exchange, which stays in the list."],
                               "warning": {"title": "Before you change it:", "text": grows}, "where": _where_hybrid(), "options": None, "exact": None}}
    if what == "howto":   # full post-quantum on a server
        return {"title": f"Move {name} to post-quantum only", "line": "What to change, in plain words",
                "what": "A server setting and a new certificate, not a code change. The app has not made this change.",
                "suggestion": {"intro": ["Accept ML-KEM by itself and switch the classical and hybrid key exchanges off, and replace the certificate with an ML-DSA one.",
                                         f"{NOT_CHECKED[:-1]}: this version has no checked config line for a post-quantum-only server. Your TLS library's "
                                         "documentation names the groups (for example `MLKEM768`) and the certificate types it supports.",
                                         "Press Measure again in the Migration step afterwards. This entry closes when the measurement reads Post-quantum only."],
                               "warning": {"title": "Before you change it:",
                                           "text": "every client that can't do post-quantum key exchange will no longer be able to connect. This app can't see your clients."},
                               "where": None, "options": None, "exact": None}}
    if what == "no_tls13":
        versions = join_and(list(detail.get("tls_versions") or [])) or "older versions only"
        return {"title": f"Turn on TLS 1.3 on {name} first", "line": "A blocker: fix this before the change",
                "what": "A server setting, not a code change: post-quantum key exchange exists in TLS 1.3 only. The app has not made this change.",
                "suggestion": {"intro": [f"This server accepts {versions} (measured). Hybrid and post-quantum key exchange exist in TLS 1.3 only, so TLS 1.3 "
                                         "has to be on before either can be."],
                               "warning": {"title": "Before you change it:",
                                           "text": "it needs a TLS library with TLS 1.3 (OpenSSL 1.1.1 or newer). Clients that only know older versions keep "
                                                   "connecting as long as those versions stay on."},
                               "where": {"title": "Where the setting lives", "note": "Use the row that matches how TLS is handled for this server.",
                                         "columns": ["Where TLS is set up", "The setting", "To add TLS 1.3"],
                                         "rows": [{"place": "nginx", "setting": "the `ssl_protocols` line", "lead": NOT_CHECKED, "code": "ssl_protocols TLSv1.2 TLSv1.3;"},
                                                  {"place": "Apache", "setting": "the `SSLProtocol` line", "lead": NOT_CHECKED, "code": "SSLProtocol -all +TLSv1.2 +TLSv1.3"}],
                                         "after": ["Reload the server, then press Measure again in the Migration step. This entry closes when the measurement shows TLS 1.3."]},
                               "options": None, "exact": None}}
    if what == "weak_certificate":
        cert = detail.get("certificate") or {}
        return {"title": f"Replace the certificate on {name} first", "line": "A blocker: fix this before the change",
                "what": "A new certificate, not a code change. The app has not made this change.",
                "suggestion": {"intro": [f"Its certificate is {cert.get('name')}, below NIST's minimum of {cert.get('minimum_bits')} bits (measured). Replace it "
                                         "before changing the key exchange, so the change isn't built on a key that already falls short.",
                                         "Press Measure again in the Migration step afterwards."],
                               "warning": None, "where": None, "options": None, "exact": None}}
    algorithm, numbers = detail.get("algorithm"), _program_numbers(state)
    size = (f"Plan for the size: a signature grows from {_n(numbers['c']['signature_bytes'])} to about "
            f"{_n(numbers['c']['signature_bytes'] + numbers['m']['signature_bytes'])} bytes (this program plus the reference library, measured)."
            if numbers else "Plan for the size: an ML-DSA-65 signature is 3,309 bytes (published: FIPS 204).")
    both = option == "hybrid"
    return {"title": f"{name} can't make post-quantum signatures", "line": "A blocker: fix this before the change",
            "what": ("A change to the program and its signing library, made by whoever looks after it. The app has not made a change for this."),
            "suggestion": {"intro": [f"{name} signs with {algorithm} only (measured). " + ("Signing with both" if both else "Signing with ML-DSA")
                                     + " needs a version of the program built on a library that has ML-DSA.",
                                     "ML-DSA is in OpenSSL 3.5 or newer, and in the reference library this app measured it with."],
                           "warning": None, "where": None,
                           "options": {"title": "What to do", "items": [{
                               "title": "Add ML-DSA signing" + (" next to today's" if both else ""), "when": "Steps for whoever looks after this program.",
                               "steps": ["Update the signing library to one with ML-DSA (for example OpenSSL 3.5 or newer).",
                                         (f"Sign each message with both {algorithm} and ML-DSA-65, and ship both signatures. Verifiers that don't know ML-DSA keep "
                                          f"checking the {algorithm} one." if both else "Sign each message with ML-DSA-65, once every verifier supports it."),
                                         size,
                                         "Import a file that names the new version and press Measure status. This entry closes when the measurement no longer reads Classical."],
                               "note": "In this version only our own demo components can be measured."}]},
                           "exact": None}}


def fix_view(fix: dict, state: dict, is_demo: bool) -> dict:
    """One migration entry as the Fixes step shows it: text only, in the same shape as every other text-only fix."""
    what = fix["migration"]["what"]
    words = _fix_words(state, what)
    on_server = state["kind"] == "server"
    plan = option_title(state["kind"], state["plan_option"])
    lead = "From the Migration step: " if what == "howto" else "From the Migration step, a blocker: "
    source = [_t(lead), _m(state["name"]), _t(f" measured {STATUS_LABELS[state['status']]}, and its plan is {plan}"
                                               + (" (your choice)." if state["plan_source"] == "choice" else " (recommended, not yet chosen by you)."))]
    return {
        "id": fix["id"], "kind": "text", "title": words["title"], "list_source": f"Migration plan: {state['name']}", "source": source,
        "status": {"key": "text_only", "word": "Text only", "busy": False}, "labels": [], "is_demo": is_demo,
        "what": {"label": "What it suggests", "paragraphs": [[_t(words["what"])]], "server_line": None},
        "proof": {"state": "none", "badge": None, "muted": None,
                  "text": "None. This suggestion is text only: the app has not applied it or tested it on your system."},
        "pull_request": None,
        "approvers": {"text": ("Your own server team, outside this app. The app never changes your server." if on_server
                               else "Whoever looks after this software, outside this app."), "options": None, "rows": None, "footnote": None},
        "actions": {"buttons": [], "note": None}, "patch": None, "merge_dialog": None,
        "sections": [{"key": "suggestion", "title": "The suggestion", "line": words["line"], "open": True, "suggestion": words["suggestion"]}],
        "sections_note": None, "change_box": None, "advisories": None,
    }


def change_fix_view(fix: dict, state: dict, is_demo: bool) -> dict:
    """A system's change as its entry in Fixes (phase 4b): the change box carries everything, the same as in Migration."""
    view = state["change_view"]
    change = state["change"]
    on_server = state["kind"] == "server"
    titles = {"hybrid": f"Turn on hybrid key exchange on {state['name']}", "full_pq": f"Move {state['name']} to post-quantum only",
              "keep": f"Keep {state['name']} classical for now: review by {day(change.get('review_date'))}",
              "wrap": f"Wrap the connection to {state['name']}", "sign_both": f"{state['name']} can't make post-quantum signatures",
              "mldsa_only": f"{state['name']} can't make post-quantum signatures"}
    plan = option_title(state["kind"], state["plan_option"])
    source = [_t("From the Migration step: "), _m(state["name"]), _t(f" measured {STATUS_LABELS[state['status']]}, and its plan is {plan}"
                                                                   + (" (your choice)." if state["plan_source"] == "choice" else " (recommended, not yet chosen by you)."))]
    target = change.get("target")
    what = ("A change ready to try on a test copy and, after approval, to apply here: " + change["target_words"] + "." if target else
            "A change to download and apply yourself. " + (change.get("no_target") or ""))
    return {
        "id": fix["id"], "kind": "text", "title": titles.get(change["option"], view["title"]), "list_source": f"Migration plan: {state['name']}",
        "source": source, "status": {"key": "text_only", "word": view["badge"]["label"], "busy": view["busy"]}, "labels": [], "is_demo": is_demo,
        "what": {"label": "What it suggests", "paragraphs": [[_t(what)]], "server_line": None},
        "proof": {"state": "none", "badge": None, "muted": None,
                  "text": ("The change box below shows its try on a test copy, its approvals, and Apply." if target
                           else "None in the lab: this server can't be copied or changed from here. The app has not applied it to your system.")},
        "pull_request": None,
        "approvers": {"text": ("Pick them in the change box below. The app applies a change only when a person presses Apply." if target else
                               "Your own server team, outside this app." if on_server else "Whoever looks after this software, outside this app."),
                      "options": None, "rows": None, "footnote": None},
        "actions": {"buttons": [], "note": None}, "patch": None, "merge_dialog": None, "sections": [], "sections_note": None, "advisories": None,
        "change_box": view,
    }


# ------------------------------------------------------------------ the evidence download

def export(states: list[dict]) -> dict:
    """The migration plan as it goes into the evidence file and the report: plain data, the same words as the screen."""
    systems = []
    for s in states:
        rec, choice = s["recommendation"], s["choice"]
        cost = _server_cost(s) if s["kind"] == "server" else _program_cost(s)
        systems.append({
            "system": s["name"], "kind": s["kind"], "status": status_of(s)["label"], "status_sentence": today_sentence(s),
            "measured_at": s["measured_at"], "run_id": s["run_id"],
            "facts": [{"label": f["label"], "value": _plain(f["value"])} for f in _facts(s)],
            "settings": {FIELD_LABELS[f]: {"value": VALUE_LABELS[f][s["settings"][f]["value"]], "source": SOURCE_LABELS[s["settings"][f]["source"]]}
                         for f in rules.FIELDS},
            "cost": {"columns": cost["columns"], "rows": [{"label": r["label"], "cells": [_plain(c) for c in r["cells"]]} for r in cost["rows"]],
                     "note": cost["note"]} if cost else None,
            "recommendation": {"option": option_title(s["kind"], rec["option"]), "rule": rec["rule"], "in_place_today": rec["in_place"],
                               "reasons": reasons_plain(s), "made_by": RULES_TAG} if rec else None,
            "your_choice": {"option": option_title(s["kind"], choice["option"]), "reason": choice["reason"], "review_date": choice.get("review_date"),
                            "saved_at": choice["at"]} if choice else None,
            "earlier_choices": [{"option": option_title(s["kind"], c["option"]), "reason": c["reason"], "review_date": c.get("review_date"),
                                 "saved_at": c["at"]} for c in s["history"]],
            "tracks": [{"track": t["short_title"], "status": t["status"]["label"], "sentence": t["sentence"],
                        "facts": [{"label": f["label"], "value": _plain(f["value"])} for f in t["facts"]],
                        "next": _plain(t["next"]), "why": _plain(t["why"]),
                        "roadmap": present_tracks.BANDS[s["track_bands"][t["key"]]][0]} for t in present_tracks.track_views(s)],
            "also_noticed": present_tracks.also_noticed(s),
            "plan": {"option": option_title(s["kind"], s["plan_option"]), "from": "your choice" if s["plan_source"] == "choice" else "the recommendation",
                     "roadmap": "; ".join(f"{row['track']}: {present_tracks.BANDS[band][0]}" for band, row in roadmap_rows(s)),
                     "note": "; ".join(_plain(row["note"]["text"]) for _, row in roadmap_rows(s)),
                     "review_date": (s.get("review_date") or {}).get("value"),
                     "blockers": [_plain(_blocker_line(s, code, None)["text"]) for code in s["blockers"].get(s["plan_option"], [])]}
            if s["status"] and s["plan_option"] else None,
        })
    placed = [(band, row) for s in states for band, row in roadmap_rows(s)]
    roadmap = [{"phase": title, "what": sub, "systems": [f"{row['name']} ({row['track']})" for band, row in placed if band == key]}
               for key, (title, sub, _) in present_tracks.BANDS.items() if any(band == key for band, _ in placed)]
    return {"title": TITLE, "note": ("Statuses are measured. Recommendations come from fixed rules, with no AI model. A choice is the user's own, recorded "
                                     "with the time, and never overwritten by the app."),
            "systems": systems, "roadmap": roadmap}


__all__ = ["view", "system_view", "fix_view", "export", "file_settings", "status_of", "today_sentence", "option_title", "plan_line",
           "roadmap_note", "choice_line", "kind_label", "day", "FILE_SETTINGS_TITLE", "TITLE", "BANDS", "STATUS_LABELS"]
