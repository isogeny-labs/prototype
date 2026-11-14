"""The migration plan's fixed rules (phase 4a): which option is recommended for a system, what blocks an option,
where a system sits on the roadmap, and which review dates are allowed. No AI model and no scores: every answer
here follows from the measured status, three settings and the tables below, and the same inputs always give the
same answer. No words for the screen are made here (present_migration.py has them).

A status comes only from a reviewed measurement: "classical", "hybrid", "pq_only", or None (couldn't check, or
not measured yet). With no status nothing is recommended and the system is not placed on the roadmap."""
from __future__ import annotations

from datetime import date

OPTIONS = ("keep", "hybrid", "full_pq", "wrap")      # the order the screens show them in
FIELDS = {"lifespan": ("long", "short"), "exposure": ("internet", "internal"), "can_change": ("yes", "no")}
LATEST_REVIEW = date(2030, 12, 31)                   # NIST IR 8547: today's public-key algorithms are deprecated after 2030
REVIEW_MONTHS = 12                                   # the default review date of "Keep classical for now"
# A blocker is only something that must be fixed BEFORE the change: TLS 1.3 off, a certificate below the minimum, a
# library too old to make post-quantum signatures. Making the change itself (turning hybrid on) is not one.
FIXABLE_BLOCKERS = ("no_tls13", "weak_certificate", "no_pq_signature")


def default_settings(kind: str, public_address: bool = False) -> dict:
    """What is assumed when neither the file nor the user says: the careful reading (long-lived data), exposure by
    where the address is, and that the system can be changed."""
    return {"lifespan": "long", "exposure": "internet" if kind == "server" and public_address else "internal", "can_change": "yes"}


def recommend(kind: str, status: str | None, settings: dict) -> dict | None:
    """{"option", "rule", "in_place"} or None. The first rule that fits wins. Full post-quantum is never recommended
    unless the system is already there, and wrapping never applies to a signing program."""
    if status not in ("classical", "hybrid", "pq_only"):
        return None
    if status == "pq_only":
        return {"option": "full_pq", "rule": "already_pq_only", "in_place": True}
    if status == "hybrid":
        return {"option": "hybrid", "rule": "already_hybrid", "in_place": True}
    long_lived, internet, fixed = settings["lifespan"] == "long", settings["exposure"] == "internet", settings["can_change"] == "no"
    if kind == "server":
        if fixed:
            option, rule = ("wrap", "cant_change_exposed") if long_lived or internet else ("keep", "cant_change_low")
        elif long_lived:
            option, rule = "hybrid", "long_lived"
        elif internet:
            option, rule = "hybrid", "internet_facing"
        else:
            option, rule = "keep", "short_internal"
    elif long_lived:
        option, rule = "hybrid", "long_lived_signatures"
    else:
        option, rule = "keep", "short_lived_signatures"
    return {"option": option, "rule": rule, "in_place": False}


def offered(kind: str, status: str | None) -> tuple[str, ...]:
    """The options a system can be given. None without a status; no wrapping for a signing program; and no going
    back: a system that is already Hybrid is not offered "keep classical" or a wrapper, and one that is already
    Post-quantum only is offered nothing else."""
    if status == "pq_only":
        return ("full_pq",)
    if status == "hybrid":
        return ("hybrid", "full_pq")
    if status != "classical":
        return ()
    return OPTIONS if kind == "server" else tuple(o for o in OPTIONS if o != "wrap")


def in_place(status: str | None, option: str) -> bool:
    """Is this post-quantum option what the system was measured doing today?"""
    return (status, option) in (("hybrid", "hybrid"), ("pq_only", "full_pq"))


def blockers(kind: str, option: str, facts: dict) -> list[str]:
    """What must be fixed before this option can be taken, as codes, from measured facts only.
    Server facts: {"tls13": "on"|"off"|"unknown", "weak_certificate": bool}. Program facts: {"post_quantum_signatures": bool}."""
    if option not in ("hybrid", "full_pq"):
        return []
    found = []
    if kind == "server":
        if facts.get("tls13") == "off":
            found.append("no_tls13")           # post-quantum key exchange exists in TLS 1.3 only
        if facts.get("weak_certificate"):
            found.append("weak_certificate")
    elif not facts.get("post_quantum_signatures"):
        found.append("no_pq_signature")
    return found   # (that every client must support full post-quantum is said as something to check, not as a blocker)


def band(kind: str, status: str | None, option: str | None, settings: dict, blocking: list[str]) -> str:
    """Where a system sits on the roadmap: already, phase1, phase2, later, wrapped or not_placed."""
    if status not in ("classical", "hybrid", "pq_only") or option is None:
        return "not_placed"
    if option == "wrap":
        return "wrapped"
    if option == "keep":
        return "later"
    if in_place(status, option):
        return "already"
    first = kind == "server" and settings["exposure"] == "internet" and settings["lifespan"] == "long" and not blocking
    return "phase1" if first else "phase2"


def default_review_date(measured_on: date) -> date:
    year, month = measured_on.year + (measured_on.month - 1 + REVIEW_MONTHS) // 12, (measured_on.month - 1 + REVIEW_MONTHS) % 12 + 1
    day = measured_on.day
    while True:
        try:
            wanted = date(year, month, day)
            break
        except ValueError:
            day -= 1                                   # 29 February -> 28 February
    return min(wanted, LATEST_REVIEW)


def review_date_problem(value: str | None, today: date) -> str | None:
    """Why this review date can't be used (a code), or None. A kept-classical system always has one: never "forever"."""
    try:
        wanted = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return "missing"
    if wanted <= today:
        return "past"
    return "too_late" if wanted > LATEST_REVIEW else None


__all__ = ["OPTIONS", "FIELDS", "LATEST_REVIEW", "FIXABLE_BLOCKERS", "default_settings", "recommend", "offered", "in_place",
           "blockers", "band", "default_review_date", "review_date_problem"]
