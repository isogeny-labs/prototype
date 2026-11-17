"""The one plain sentence on top of every Verify row, and the "Also noticed" notes (phase 3a-fixes).

Words only. Nothing here decides a result: True / False / Couldn't check come from verify.py and compare.py, and
these sentences are written from that result and the facts the check recorded. Rules for every sentence: say
what was found and why that gives this result, in words a busy engineer who isn't a cryptographer reads at a
glance. Never "secure", never a score, never a judgement beyond what was measured.

An "Also noticed" note is something a check saw that the file didn't ask about. It is never a result and never
changes True / False."""
from __future__ import annotations

from app.engine.compare import COULDNT, FALSE, TRUE
from app.names import TLS_VERSIONS, join_and

RETIRED = ("TLS 1.0", "TLS 1.1")  # both retired in 2021 (RFC 8996)
ID_CARD = "the server's ID card (its certificate)"


def quoted(text: str) -> str:
    return f"‘{text}’"


def case_words(comment: str) -> str:
    """One official signature case, in plain words (the file's own comment, with the best-known ones spelled out)."""
    text = comment.replace("Signature with special case values ", "")
    if text == "Legacy: ASN encoding of s misses leading 0":
        return "a number written without its leading zero (a missing leading zero)"
    if text == "r=0 and s=0":
        return "r=0 and s=0 (a signature made of zeros)"
    if text == "r=0 and s=n":
        return "r=0 and s=n (zero, written a second way)"
    if text == "s is larger than n":
        return "s larger than n (a value outside the allowed range)"
    return text


def lower_first(text: str) -> str:
    """Lower the first letter, unless the first word is an abbreviation such as TLS or RSA."""
    text = (text or "").strip()
    return text if len(text) > 1 and text[1].isupper() else text[:1].lower() + text[1:]


def also_noticed_tls(states: dict) -> list[str]:
    """The note for a check whose handshakes show the server accepts TLS 1.0 or 1.1. `states` maps a TLS version to
    "accepted" / "refused" / "unknown" (or to {"state": ...})."""
    def state(v: str) -> object:
        s = states.get(v)
        return s.get("state") if isinstance(s, dict) else s
    old = [v for v in RETIRED if state(v) == "accepted"]
    if not old:
        return []
    both = "both retired" if len(old) == 2 else "retired"
    return [f"This server also accepts {join_and(old)}, {both} in 2021. The file didn't ask about this, so it doesn't change the result."]


def tls_claim(claimed: list[str]) -> str:
    return quoted(f"{join_and(claimed)} only")


def verify_tls(result: str, claimed: list[str], accepted: list[str], refused: list[str], unknown: list[str]) -> str:
    claim = tls_claim(claimed)
    outside = [v for v in accepted if v not in claimed]
    if result == FALSE and outside:
        return f"The server accepts {join_and(outside)}, so {claim} is not true."
    if result == FALSE:
        gone = [v for v in claimed if v in refused]
        return f"The server refuses {join_and(gone)}, which the file says it accepts, so {claim} is not true."
    if result == TRUE:
        return f"The server accepts {join_and([v for v in claimed if v in accepted])} and refused every other TLS version we tried, so {claim} is true."
    if unknown:
        return f"The server didn't confirm or refuse {join_and(unknown)}, so we can't say whether {claim} is true."
    return f"We couldn't tell which TLS versions the server accepts, so we can't say whether {claim} is true."


def verify_certificate(result: str, claimed: str, found: str | None) -> str:
    if result == TRUE:
        return f"{ID_CARD[0].upper() + ID_CARD[1:]} uses {found}, which matches the claim."
    if result == FALSE:
        return f"{ID_CARD[0].upper() + ID_CARD[1:]} uses {found}, not {claimed} as the file claims."
    return ""


def verify_software(result: str, label: str, algorithm: str, found: str, key_exchange: bool = False) -> str:
    if result == TRUE and key_exchange:
        return f"{label} says it uses {algorithm}, and a normal key exchange round trip worked, which matches the claim."
    if result == TRUE:
        return f"{label} says it uses {algorithm}, and a normal sign-and-check round trip worked, which matches the claim."
    if result == FALSE:
        return f"{label} doesn't match the claim: {lower_first(found)}"
    return ""


def couldnt(reason: str | None, what: str = "this") -> str:
    """A Couldn't check row: say there is no answer either way, and why."""
    why = (reason or "").strip()
    if not why:
        return f"We couldn't check {what}, so there is no answer either way."
    return f"We couldn't check {what}, so there is no answer either way: {lower_first(why).rstrip('.')}."


def verify_fallback(result: str, found: str) -> str:
    """For a row stored before phase 3a-fixes, which has no sentence of its own."""
    return {TRUE: "This matches the claim. ", FALSE: "This doesn't match the claim. "}.get(result, "") + (found or "")


__all__ = ["RETIRED", "also_noticed_tls", "verify_tls", "verify_certificate", "verify_software", "couldnt", "verify_fallback",
           "quoted", "tls_claim", "lower_first", "TLS_VERSIONS", "COULDNT"]
