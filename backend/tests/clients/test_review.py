"""Phase 4e: the reviewer's rule for "Who can still connect", over every combination of what a stand-in did today and on
the test copy, and the four demo stand-ins as Kevin named them. The rule is information: its code is "measured", and
silence is never read as Breaks."""
from __future__ import annotations

import itertools

import pytest

from app.canonical import sha256_hex
from app.clients import design, profiles
from app.engine.reviewer import CLIENT_WORDS, RuleReviewer, client_kind, client_word
from app.present import clients as words

KINDS = ("hybrid", "post_quantum", "classical", "refused", "unclear")


def _expected(today: str, on_copy: str, brings: bool) -> tuple[str, bool]:
    """The rule as the plan approved on 20 November 2026 writes it, written out a second time."""
    if "unclear" in (today, on_copy):
        return "couldnt_check", False
    if on_copy in ("hybrid", "post_quantum"):
        return "connects", today == "refused"
    if on_copy == "classical":
        return ("falls_back" if brings else "connects"), today == "refused"
    return ("not_before" if today == "refused" else "breaks"), False


@pytest.mark.parametrize("today,on_copy,brings", list(itertools.product(KINDS, KINDS, (True, False))))
def test_every_combination_gets_the_word_of_the_rule(today, on_copy, brings):
    assert client_word(today, on_copy, brings) == _expected(today, on_copy, brings)


def test_silence_is_never_breaks_and_only_a_clear_refusal_is_one():
    assert client_kind({"outcome": "unknown", "detail": "no answer before the time limit"}) == "unclear"
    assert client_kind(None) == "unclear" and client_kind("refused") == "unclear"
    assert client_kind({"outcome": "refused", "alert": 70}) == "refused"
    assert client_kind({"outcome": "completed", "group": "X25519MLKEM768"}) == "hybrid"
    assert client_kind({"outcome": "completed", "group": "MLKEM768"}) == "post_quantum"
    assert client_kind({"outcome": "completed", "group": "P-256"}) == "classical"
    for today in KINDS:
        word, _ = client_word(today, "unclear", True)
        assert word == "couldnt_check"
    assert set(CLIENT_WORDS) == set(words.WORDS) == set(words.TONES)


def test_the_four_stand_ins_are_demo_data_with_the_names_kevin_approved():
    names = [p["name"] for p in profiles.stand_ins()]
    assert names == ["Payment terminal, old firmware", "Partner system, classical only", "Payment terminal, new firmware",
                     "Post-quantum-only client"]
    assert profiles.DEMO_LABEL == "Demo data" and "not your devices" in profiles.STAND_IN_NOTE
    assert set(design.CONTROL_MUST) == {p["id"] for p in profiles.stand_ins()}
    # the locked test is the same for the same change on the same server, and another for another change
    change = {"key": "migration:server:localhost:8452", "fingerprint": "f" * 64, "option": "hybrid", "kind": "migration"}
    a, b = design.design(address="localhost:8452", change=change), design.design(address="localhost:8452", change=change)
    assert sha256_hex(a) == sha256_hex(b) and a["inputs"]["brings_post_quantum"] is True
    tls = design.design(address="localhost:8443", change={**change, "option": "tls13", "kind": "tls"})
    assert sha256_hex(tls) != sha256_hex(a) and tls["inputs"]["brings_post_quantum"] is False
    assert a["inputs"]["stand_ins_sha256"] == profiles.fingerprint()


def _hs(outcome: str, group: str | None = None, version: str | None = None, alert: int | None = None) -> dict:
    return {"outcome": outcome, "group": group, "tls_version": version, "alert": alert, "detail": ""}


def _control() -> dict:
    out: dict = {}
    for server in ("hybrid", "classical"):
        out[server] = {}
        for sid, must in design.CONTROL_MUST.items():
            want = must[server]
            out[server][sid] = (_hs("refused", alert=40) if want["kind"] == "refused" else
                                _hs("completed", "X25519MLKEM768" if want["kind"] == "hybrid" else "X25519", want["version"]))
    return out


def _review(raw: dict, option: str = "tls13") -> dict:
    spec = design.design(address="localhost:8443", change={"key": "k", "fingerprint": "f", "option": option, "kind": "tls"})
    run = {"spec_hash": sha256_hex(spec), "raw": raw}
    return RuleReviewer().review({"spec": spec, "spec_hash": sha256_hex(spec), "proposed_by": design.PROPOSED_BY, "run": run})


def _raw(today: dict, on_copy: dict, control: dict | None = None, reached: bool = True) -> dict:
    return {"engine": {"available": True, "text": "OpenSSL"}, "control": control if control is not None else _control(),
            "subject": {"address": "localhost:8443", "today": {"reached": reached, "problem": None if reached else "The server did not answer.",
                                                              "handshakes": today if reached else {}},
                        "copy": {"port": 1, "handshakes": on_copy}, "evidence": []}}


TODAY = {"old-terminal": _hs("completed", "P-256", "TLS 1.2"), "partner-classical": _hs("completed", "P-256", "TLS 1.3"),
         "new-terminal": _hs("completed", "P-256", "TLS 1.3"), "pq-only": _hs("refused", alert=40)}
COPY = {"old-terminal": _hs("refused", alert=70), "partner-classical": _hs("completed", "P-256", "TLS 1.3"),
        "new-terminal": _hs("completed", "P-256", "TLS 1.3"), "pq-only": _hs("refused", alert=40)}


def test_a_review_is_measured_with_each_stand_ins_word_and_the_words_follow_it():
    review = _review(_raw(TODAY, COPY))
    assert review["verdict"]["code"] == "measured" and review["control"]["outcome"] == "as_expected"
    rows = {r["id"]: r["word"] for r in review["detail"]["stand_ins"]}
    assert rows == {"old-terminal": "breaks", "partner-classical": "connects", "new-terminal": "connects", "pq-only": "not_before"}
    assert review["detail"]["counts"] == {"connects": 2, "falls_back": 0, "breaks": 1, "not_before": 1, "couldnt_check": 0}
    assert words.summary(review["detail"]["counts"], False) == "1 breaks, 2 connect, 1 didn't connect before either."
    assert words.warning(review["detail"]["counts"]) == "Sort out the 1 that breaks before you apply this change."
    assert words.summary({"connects": 1, "falls_back": 2, "not_before": 1}, True) == (
        "None break. 1 connects with hybrid or post-quantum key exchange; 2 fall back to classical key exchange; 1 didn't connect before either.")
    assert words.warning({"breaks": 3}) == "Sort out the 3 that break before you apply this change."
    assert words.warning({"connects": 4}) is None


def test_a_control_misread_is_not_trusted_and_a_server_not_reached_today_is_couldnt_check():
    control = _control()
    control["hybrid"]["new-terminal"] = _hs("completed", "X25519", "TLS 1.3")     # it did not take hybrid on the hybrid control
    review = _review(_raw(TODAY, COPY, control))
    assert review["verdict"]["code"] == "couldnt_trust" and review["control"]["outcome"] == "not_as_expected"
    assert "new-terminal on the hybrid control" in review["control"]["reason"]
    gone = _review(_raw(TODAY, COPY, {"error": "the control servers could not be started (OSError)"}))
    assert gone["verdict"]["code"] == "couldnt_trust" and gone["control"]["outcome"] == "errored"
    unreached = _review(_raw({}, COPY, reached=False))
    assert unreached["verdict"]["code"] == "measured"
    assert {r["word"] for r in unreached["detail"]["stand_ins"]} == {"couldnt_check"}
    assert unreached["detail"]["today_problem"] == "The server did not answer."
    # (separate review, 20 November 2026) a stand-in that couldn't be checked is never counted as one that doesn't break
    assert words.summary(unreached["detail"]["counts"], False) == "4 couldn't be checked."
    assert words.summary({"connects": 2, "couldnt_check": 2}, True) == (
        "2 connect with hybrid or post-quantum key exchange; 2 couldn't be checked.")
    assert words.summary({"breaks": 1, "couldnt_check": 3}, False) == "1 breaks, 3 couldn't be checked."
    assert words.warning(unreached["detail"]["counts"]) is None
    problem = _review({"problem": {"code": "copy_unavailable", "text": "the copy could not be started"}})
    assert problem["verdict"]["code"] == "couldnt_run"
