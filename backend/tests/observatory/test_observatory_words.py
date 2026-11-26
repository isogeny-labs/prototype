"""The Observatory's own words, rule by rule: the plain name of an algorithm, how a use and a line are worded, what was
seen on a connection, a box's summary from counts of the checks' own words, the one tag of a box, and that no sentence
rates anything. Words only: nothing here needs a running app."""

from __future__ import annotations

from app.names import ALGORITHM_NAMES
from app.observatory import build
from app.present import observatory as words
from app.present import source as present_source
from tests.observatory.observatory_walk import NEVER


def test_an_algorithm_gets_the_apps_own_plain_name_and_only_as_a_whole_word():
    for technical, plain in ALGORITHM_NAMES:
        assert words.plain_name(technical) == plain
    assert (
        words.plain_name("ECDSA P-256") == "Classical signatures"
        and words.plain_name("RSA 2048") == "Classical signatures"
    )
    assert words.plain_name("X25519MLKEM768") == "Hybrid connection"  # the longer name first, never "X25519"
    assert words.plain_name("X25519") == "Classical key exchange"
    # a name the app has no plain name for stays as the file writes it
    for unknown in ("SHA-256", "AES-128-GCM", "ECDSA P-384", "RSASSA", "XRSA 2048", "", "ML-KEM-1024"):
        assert words.plain_name(unknown) is None, unknown


def test_a_use_a_line_and_what_was_seen_are_worded_from_the_real_names():
    assert words.use_words("certificate", "localhost:8443", True) == "the certificate on localhost:8443"
    assert words.use_words("protocol", "localhost:8443", True) == "TLS on localhost:8443"
    assert words.use_words("signature", "acme-sign 1.4.2", False) == "the signatures of acme-sign 1.4.2"
    assert words.use_words("key_exchange", "openssl 3.5.9", False) == "the key exchange of openssl 3.5.9"
    assert words.use_words("direct", "gateway 3.2", False) == "gateway 3.2"
    assert words.used_in(["a", "b"]) == "Used in 2 places: a and b." and words.used_in(["a"]) == "Used in 1 place: a."
    assert words.used_in([]) == "Your scanner file names it, and no system that uses it."
    # the line from your own software to its one library says how the list reaches it; to a group, how many
    assert words.libraries_line(1, "through python 3.12.3") == "through python 3.12.3"
    assert words.libraries_line(1, "direct") == words.libraries_line(1, None) == "uses"
    assert words.libraries_line(8, None) == "uses 8 libraries" and words.more_libraries(5) == "5 more"
    assert words.libraries_title("acme-ledger 5.1.0", 8) == "acme-ledger 5.1.0's libraries · 8"
    # what the recorded handshakes show, newest version first; no record is not "nothing accepted"
    assert words.live_label(["TLS 1.3", "TLS 1.2"]) == "TLS · 1.3 and 1.2 accepted"
    assert words.live_label(["TLS 1.3"]) == "TLS · 1.3 accepted"
    assert words.live_label([]) == "TLS · no version accepted" and words.live_label(None) == "Handshakes only"


def test_an_untied_entry_names_what_it_is_not_tied_to():
    assert words.not_tied(["the endpoint", "acme-sign"]) == "Not tied to the endpoint or to acme-sign."
    assert words.not_tied(["localhost:8443"]) == "Not tied to localhost:8443."
    assert words.not_tied(["a", "b", "c"]) == "Not tied to a or to b or to c."
    assert words.not_tied(["a", "b", "c", "d"]) == "Not tied to any of the 4 systems in your scanner file."
    assert words.not_tied([]) == "Not tied to a system: your scanner file names none."
    assert words.tie_words("acme-sign 1.4.2", "name_version").endswith("is tied to it by name and version.")
    assert words.tie_words("acme-pay-server 1.0.0", "user").endswith("by you, with Part of on Dependencies.")


def test_what_a_claim_says_is_the_files_own_terms():
    assert words.claim_says("protocol_versions", "TLS 1.2, TLS 1.3", {"versions": ["TLS 1.2", "TLS 1.3"]}) == (
        "TLS 1.2 and TLS 1.3 only"
    )
    assert words.claim_says("protocol_versions", "TLS (version not stated)", {}) == "TLS (version not stated)"
    assert words.claim_says("certificate", "ECDSA P-256", {"algorithm": "ECDSA P-256"}) == "ECDSA P-256"
    assert words.claim_says("key_exchange", "X25519, P-256", {"groups": ["X25519", "P-256"]}) == "only X25519, P-256"
    assert words.claim_says("post_quantum", "Hybrid", {"status": "Hybrid"}) == "Hybrid"
    assert (
        words.file_says(["TLS 1.3 only"]) == "The file says TLS 1.3 only" and words.file_says([]) == "Not in your file"
    )
    assert (
        words.claim_name("ECDSA P-256", True) == "The claim"
        and words.claim_name("Hybrid", False) == "The claim: Hybrid"
    )
    assert words.retest_label("acme-sign 1.4.3", "acme-sign 1.4.2") == "Retest on acme-sign 1.4.3"
    for same in (("acme-sign 1.4.2", "acme-sign 1.4.2"), (None, None), (None, "acme-sign 1.4.2")):
        assert words.retest_label(*same) == "Retest, tested again as it is"


def test_a_boxs_summary_is_built_only_from_counts_of_the_checks_own_words():
    assert (
        words.summary(
            ["False", "True"],
            ["Failed", "Passed"],
            [("key exchange", "Classical"), ("authentication", "Classical")],
            {},
            True,
        )
        == "2 claims: 1 False, 1 True. 2 server tests: 1 Failed, 1 Passed. Post-quantum status: Classical."
    )
    # two tracks that stand differently are each named
    assert words.summary([], [], [("key exchange", "Hybrid (interim)"), ("authentication", "Classical")], {}, True) == (
        "Post-quantum status: key exchange Hybrid (interim), authentication Classical."
    )
    assert (
        words.summary(
            ["True"],
            ["Failed", "Failed", "Measured"],
            [("signatures", "Classical")],
            {"Retest on x 2": ["Passed"]},
            False,
        )
        == "1 claim: 1 True. 3 tests: 2 Failed, 1 Measured. Retest on x 2: 1 Passed. Post-quantum status: Classical."
    )
    assert words.summary(["Couldn't check"], ["Not checked yet"], [], {}, True) == (
        "1 claim: 1 Couldn't check. 1 server test: 1 Not checked yet."
    )
    assert words.summary([], [], [], {}, False) == "Nothing observed or run here."


def test_a_box_carries_one_tag_only_where_every_result_rests_on_the_same_thing():
    live, lab, file = (present_source.live("a:1"), present_source.lab_copy("x 1"), present_source.from_file())
    assert build._one_tag([]) is None and build._one_tag([None, None]) is None
    assert build._one_tag([live, None, present_source.live("a:1")]) == live  # the same sentence too: it is kept
    other = build._one_tag([live, present_source.after_change("a:1")])
    assert other == present_source.tag("live") and other["note"] is None  # the same tag, two sentences: the tag alone
    assert build._one_tag([live, lab]) is None and build._one_tag([lab, file, None]) is None


def test_no_sentence_of_the_observatory_rates_anything():
    # every sentence the module holds (its own description, which says what it never says, is no sentence of the map)
    own = {name: value for name, value in vars(words).items() if not name.startswith("__")}
    said = [v for v in own.values() if isinstance(v, str)]
    said += [t for v in own.values() if isinstance(v, dict) for t in v.values() if isinstance(t, str)]
    said += [entry["text"] for entry in words.LEGEND]
    said += [
        words.gap_software(["a:1"], ["x 1", "y 2"], True),
        words.gap_software(["a:1", "b:2"], [], True),
        words.gap_software(["a:1"], [], False),
        words.gap_clients(["a:1", "b:2"]),
        words.gap_clients_of("a:1"),
        words.gap_unplaced(["RSA 2048"]),
        words.gap_part_of(["a", "b"]),
        words.gap_part_of([]),
        words.gap_libraries(True),
        words.gap_libraries(False),
        words.not_drawn(1),
        words.not_drawn(3),
        words.unreadable_note("This file is not valid JSON."),
    ]
    assert len(said) > 60
    for text in said:
        assert not NEVER.search(text), text
    # the gap for several servers names each, and a long list is counted
    assert words.gap_software(["a:1", "b:2"], [], True).startswith("Which software answers on a:1 and b:2.")
    assert "5 server addresses" in words.gap_clients([f"h{n}:1" for n in range(5)])
    assert "x 1 and y 2" in words.gap_software(["a:1"], ["x 1", "y 2"], True)
