"""Where it came from (22 November 2026, Kevin's plan and decisions A, B and C): the one rule that picks the tag of every
result, system status and fix, case by case. Live = observe; lab = test. The rule reads what the app already recorded
and decides nothing."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.engine.research import SERVER_KINDS, SOFTWARE_TEST_KINDS
from app.present import source as S

BANNED = re.compile(r"\bsecure\b|\bscore\b|\bseverity\b|\bsevere\b|time to hack", re.I)


def key(tag: dict | None) -> str | None:
    return tag["key"] if tag else None


def test_the_four_tags_have_kevins_words_and_say_what_they_mean():
    assert S.LABELS == {"live": "Observed live", "lab": "Proven in the lab", "file": "From your file", "published": "Published"}
    for k in S.KEYS:
        tag = S.tag(k)
        assert tag["label"] == S.LABELS[k] and tag["meaning"] and tag["note"] is None
        assert not BANNED.search(tag["meaning"])
    # live = observe: a reading is handshakes only; lab = test: on a copy, never the live system
    assert "handshakes only" in S.MEANINGS["live"] and "copy" in S.MEANINGS["lab"] and "live system" in S.MEANINGS["lab"]


@pytest.mark.parametrize("kind", SERVER_KINDS)
def test_a_server_test_is_a_reading_of_the_server(kind):
    tag = S.of_test(kind, {"code": "failed"}, "localhost:8443")
    assert key(tag) == "live" and "localhost:8443" in tag["note"] and "handshakes only" in tag["note"]


@pytest.mark.parametrize("kind", SOFTWARE_TEST_KINDS)
def test_every_other_test_runs_a_copy_on_this_computer(kind):
    tag = S.of_test(kind, {"code": "passed", "component": "acme-sign 1.4.2", "mode": "isolated"})
    assert key(tag) == "lab"
    assert tag["note"] == ("Run on a copy of acme-sign 1.4.2 on this computer, in isolated mode (a locked-down container with no network). "
                           "Your live system was not touched.")
    assert "not isolated" in S.of_test(kind, {"code": "passed", "component": "acme-sign 1.4.2", "mode": "demo"})["note"]
    assert "public copy of openjdk 17.0.2" in S.of_test(kind, {"code": "failed", "component": "openjdk 17.0.2", "real": True})["note"]


@pytest.mark.parametrize("code", ["couldnt_run", "couldnt_trust", "couldnt_check", None])
def test_a_test_that_observed_or_proved_nothing_has_no_tag(code):
    assert S.of_test("tls_versions", {"code": code}, "localhost:8443") is None
    assert S.of_test("official_vectors", {"code": code}) is None
    assert S.of_test("official_vectors", None) is None


def test_verify_server_claims_are_live_program_claims_are_lab_and_what_couldnt_be_checked_rests_on_the_file():
    server = {"claim": {"location_kind": "server", "location": "localhost:8443"}}
    program = {"claim": {"location_kind": "software", "location": "acme-sign 1.4.2"}}
    assert key(S.of_verify({**server, "result": "False"})) == "live"
    assert key(S.of_verify({**server, "result": "True"})) == "live"
    assert key(S.of_verify({**program, "result": "True"})) == "lab"
    assert "running a copy of acme-sign 1.4.2" in S.of_verify({**program, "result": "True"})["note"]
    for claim in (server, program):
        assert key(S.of_verify({**claim, "result": "Couldn't check"})) == "file"
    assert S.of_verify(None) is None


def test_a_systems_status_is_live_on_a_server_lab_on_a_program_and_the_file_before_a_measurement():
    assert key(S.of_system("server", "classical", "localhost:8451")) == "live"
    assert key(S.of_system("software", "classical", "acme-sign 1.4.2")) == "lab"
    for status in ("not_measured", "couldnt_check", None):
        for kind in ("server", "software"):
            assert key(S.of_system(kind, status, "x")) == "file"


def test_a_librarys_answer_keeps_the_label_it_has_and_gets_its_tag_from_it():
    assert key(S.of_answer("release_notes", "no")) == "published"          # decision B: the maker's release notes
    assert key(S.of_answer("public_copy", "yes")) == "lab"
    assert key(S.of_answer(None, "doesnt_apply")) == "published"             # the knowledge base, from what the maker publishes
    for answer in ("not_in_knowledge_base", "couldnt_tell_version", "needs_your_environment"):
        assert key(S.of_answer(None, answer)) == "file"
    assert key(S.of_library()) == "file"
    assert key(S.of_answers([{"label": "release_notes"}, {"label": "public_copy"}])) == "lab"
    assert key(S.of_answers([{"label": "release_notes"}, {"label": None}])) == "published"
    assert key(S.of_answers([{"label": None}])) == "file"
    assert key(S.of_claim("acme-pay-cbom.json")) == "file" and "acme-pay-cbom.json" in S.of_claim("acme-pay-cbom.json")["note"]


def _row(kind, origin, code="passed", **more):
    return {"kind": kind, "came_from": {"key": origin}, "result": {"code": code} if code else None, "ran_on": "localhost:8443", "name": "x", **more}


def test_a_row_of_checks_follows_what_it_ran_on_whatever_started_it():
    # a retest and a proof rerun a server test against the server as it is: still a reading of the server
    for origin in ("plan", "retest", "proof", "watch"):
        assert key(S.of_check_row(_row("tls_versions", origin))) == "live", origin
        assert key(S.of_check_row(_row("official_vectors", origin))) == "lab", origin
    assert key(S.of_check_row(_row("pq_status", "try"))) == "lab"                       # a test copy
    assert "also connected to the server as it is today" in S.of_check_row(_row("client_reach", "try"))["note"]
    assert key(S.of_check_row(_row("pq_status", "after_apply"))) == "live"              # measured again on the server itself
    assert "earlier settings were put back" in S.of_check_row(_row("tls_versions", "after_rollback"))["note"]
    assert key(S.of_check_row(_row("pq_status", "measure", "classical"))) == "live"
    assert key(S.of_check_row(_row("signing_status", "measure", "classical"))) == "lab"
    assert key(S.of_check_row(_row("capability", "public_copy", "measured"))) == "lab"
    # nothing to rest on yet: a check of ours has no tag; a system that couldn't be measured stands on the file
    assert S.of_check_row(_row("official_vectors", "plan", None)) is None
    assert S.of_check_row(_row("official_vectors", "plan", "couldnt_run")) is None
    assert key(S.of_check_row(_row("pq_status", "measure", "couldnt_trust"))) == "file"
    verify = {"claim": {"location_kind": "server", "location": "localhost:8443"}, "result": "False"}
    assert key(S.of_check_row({**_row("verify", "verify", "false"), "verify": verify})) == "live"


def test_a_fix_carries_the_tag_of_the_finding_it_came_from():
    assert key(S.of_fix({"source_kind": "failed_tests", "kind": "text"}, "localhost:8443")) == "live"       # a server test failed
    assert key(S.of_fix({"source_kind": "failed_tests", "kind": "text"}, None)) == "lab"                    # a program or a library
    code = S.of_fix({"source_kind": "failed_tests", "kind": "code", "component": {"name": "acme-sign", "version": "1.4.2"}})
    assert key(code) == "lab" and "acme-sign 1.4.2" in code["note"]
    assert key(S.of_fix({"source_kind": "dependency"})) == "file"
    assert key(S.of_fix({"source_kind": "developer_change"})) == "lab"
    assert key(S.of_fix({"source_kind": "applied_change"}, "localhost:8443")) == "live"
    assert key(S.of_fix({"source_kind": "migration", "test_kind": "pq_status", "migration": {"system": "server:localhost:8451"}})) == "live"
    assert "localhost:8451" in S.of_fix({"source_kind": "migration", "test_kind": "pq_status", "migration": {"system": "server:localhost:8451"}})["note"]
    assert key(S.of_fix({"source_kind": "migration", "test_kind": "signing_status", "migration": {"system": "software:c3"}})) == "lab"
    assert key(S.lab_proof()) == "lab" and key(S.lab_try()) == "lab" and key(S.after_change("localhost:8443")) == "live"


def test_the_small_tags_already_on_a_page_keep_their_words_and_get_their_sources_look():
    parts = [{"t": "text", "v": "1,184 bytes "}, {"t": "tag", "v": "measured"}, {"t": "tag", "v": "measured on our test server"},
             {"t": "tag", "v": "measured on the reference library"}, {"t": "tag", "v": "published: FIPS 203"},
             {"t": "tag", "v": "measured on the copy"}, {"t": "tag", "v": "not measured"}, {"t": "tag", "v": "set by you"}]
    words = [p["v"] for p in parts]
    S.colour_tags({"cells": [parts]}, S.LIVE)
    assert [p["v"] for p in parts] == words                                   # not one word changes
    assert [p.get("s") for p in parts] == [None, "live", "lab", "lab", "published", "lab", None, None]
    assert S.colour_tags([{"t": "tag", "v": "measured"}], S.LAB)[0]["s"] == "lab"     # a bare "measured" on a signing program
    assert S.colour_tags({"tag": "measured"}, S.LIVE) == {"tag": "measured"}         # only a sentence's tag part is touched


def test_the_overview_counts_in_the_fixed_order_and_leaves_out_the_sources_with_none():
    tags = [S.live("a"), S.live("b"), S.tag("lab"), None]
    assert S.counted(tags, extra_file=2) == [{"key": "live", "label": "Observed live", "count": 2},
                                             {"key": "lab", "label": "Proven in the lab", "count": 1},
                                             {"key": "file", "label": "From your file", "count": 2}]
    assert S.counted([]) == []


def test_every_sentence_the_rule_can_say_is_plain_and_says_no_score_and_no_severity():
    notes = [S.live("localhost:8443"), S.after_change("x"), S.after_change("x", True), S.lab_copy("p", "demo"), S.lab_copy("p", "isolated"),
             S.lab_copy(None), S.lab_copy("l", real=True), S.lab_try(), S.lab_try(True), S.lab_proof(), S.lab_public_copy("l"), S.from_file(),
             S.published(), S.of_library(), S.of_claim("f"), S.of_answer(None, "doesnt_apply"), S.of_answer(None, "not_in_knowledge_base"),
             S.of_system("software", "classical", "p"), S.of_system("server", None, "s"), S.of_fix({"source_kind": "dependency"}),
             S.of_fix({"source_kind": "developer_change"}), S.of_verify({"claim": {"location_kind": "software"}, "result": "True"}),
             S.of_verify({"claim": {}, "result": "Couldn't check"})]
    for tag in notes:
        for words in (tag["label"], tag["meaning"], tag["note"]):
            assert words and not BANNED.search(words), words


def test_the_rule_imports_nothing_that_measures_decides_runs_or_changes():
    """It reads one fixed list (which tests are server tests) and nothing else: no reviewer, no runner, no store."""
    tree = ast.parse(Path(S.__file__).read_text())
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported == {"__future__", "typing", "app.engine.research"}
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "app.engine.research" for a in n.names}
    assert names == {"SERVER_KINDS"}
