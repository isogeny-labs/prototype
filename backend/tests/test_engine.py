"""The research engine socket: proposing and designing tests, who may review, and Dig deeper."""
import ast
from pathlib import Path

import pytest

from app import research, reviewer
from app.canonical import sha256_hex
from app.db import ResearchRequestRow
from app.research import CATALOG, ReviewNotAllowed, RuleEngine
from app.reviewer import RuleReviewer
from conftest import result_of
from test_records import DEMO_CLAIMS


def test_the_five_tests_are_proposed_in_order_for_the_demo_claims():
    plan = RuleEngine().propose_tests(DEMO_CLAIMS)
    assert [t["kind"] for t in plan["tests"]] == ["tls_versions", "certificate", "official_vectors", "bad_signatures", "speed_size"]
    assert [t["title"] for t in plan["tests"]] == ["Old TLS versions", "Certificate strength", "Official test vectors",
                                                    "Bad signatures", "Speed and size"]
    assert plan["notes"] == []
    assert plan["tests"][0]["control"]["accepts"] == "TLS 1.2"  # just below the oldest claimed version


def test_fewer_tests_for_a_file_that_claims_less():
    only_server = RuleEngine().propose_tests(DEMO_CLAIMS[:2])
    assert [t["kind"] for t in only_server["tests"]] == ["tls_versions", "certificate"] and len(only_server["notes"]) == 3
    only_software = RuleEngine().propose_tests(DEMO_CLAIMS[2:])
    assert [t["kind"] for t in only_software["tests"]] == ["official_vectors", "bad_signatures", "speed_size"]
    assert RuleEngine().propose_tests([])["tests"] == []


def test_the_control_server_is_derived_from_the_claim():
    claims = [dict(DEMO_CLAIMS[0], detail={"host": "localhost", "port": 8443, "versions": ["TLS 1.2", "TLS 1.3"]})]
    spec = RuleEngine().propose_tests(claims)["tests"][0]
    assert spec["control"]["accepts"] == "TLS 1.1" and spec["control"]["must"] == {"verdict": "failed", "accepted": "TLS 1.1"}


def test_design_test_gives_a_complete_locked_test_for_both_catalog_ids():
    engine = RuleEngine()
    assert CATALOG == ("pq_readiness", "mldsa_compare")
    for kind in CATALOG:
        spec = engine.design_test({"catalog_id": kind, "claims": DEMO_CLAIMS})
        assert spec["kind"] == kind and spec["schema"] == "isogeny.test-spec/1" and len(sha256_hex(spec)) == 64
        assert spec["control"]["must"] and spec["rule"]["type"]
    with pytest.raises(research.CannotDesign):
        engine.design_test({"catalog_id": "pq_readiness", "claims": DEMO_CLAIMS[2:]})  # no server in the file
    with pytest.raises(research.CannotDesign):
        engine.design_test({"catalog_id": "upload_software", "claims": DEMO_CLAIMS})


def test_the_engine_that_proposes_never_reviews():
    with pytest.raises(ReviewNotAllowed):
        RuleEngine().review({"spec": {}, "spec_hash": "", "proposed_by": "x", "run": {}})


def test_the_reviewer_refuses_a_test_it_proposed_and_proposes_nothing():
    spec = RuleEngine().propose_tests(DEMO_CLAIMS)["tests"][0]
    with pytest.raises(ReviewNotAllowed):
        RuleReviewer().review({"spec": spec, "spec_hash": sha256_hex(spec), "proposed_by": RuleReviewer.engine_id, "run": {}})
    assert RuleReviewer.engine_id != RuleEngine.engine_id
    for call in (lambda r: r.propose_tests([]), lambda r: r.design_test({}), lambda r: r.dig_deeper({}), lambda r: r.propose_change({})):
        with pytest.raises(NotImplementedError):
            call(RuleReviewer())


def test_the_reviewer_imports_nothing_from_the_engine_or_the_runner():
    tree = ast.parse(Path(reviewer.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # from . import x / from .x import y
                imported |= {node.module.split(".")[0]} if node.module else {a.name for a in node.names}
            else:
                imported.add(node.module.split(".")[0])
    assert not imported & {"research", "execute", "present", "jobs", "lab", "testlab", "runner", "components", "reference", "main"}
    assert imported <= {"__future__", "math", "re", "statistics", "vectors", "canonical", "guidance"}, imported


def test_only_the_reviewer_holds_verdict_logic():
    """The modules that run tests and the engine that proposes them never name a result."""
    app = Path(reviewer.__file__).parent
    for path in [app / "research.py", *sorted((app / "execute").glob("*.py"))]:
        source = path.read_text()
        for word in ('"passed"', '"no_slowdown"', '"not_offered"', '"couldnt_trust"', '"measured"'):
            assert word not in source, f"{path.name} mentions {word}"


def test_every_reviewed_run_was_reviewed_by_the_separate_reviewer(demo_flow):
    from app.db import ReviewRow, TestRunRow
    with demo_flow.lab.db() as db:
        runs, reviews = db.query(TestRunRow).all(), db.query(ReviewRow).all()
        assert len(runs) == len(reviews) == 14
        for review in reviews:
            assert review.reviewer == "isogeny.rule-reviewer/1" and review.proposed_by == "isogeny.rule-engine/1"
            assert review.spec_hash_ok is True


def test_dig_deeper_saves_a_request_and_no_answer(demo_flow):
    lab = demo_flow.lab
    before = result_of(demo_flow.first, "official_vectors")
    view = lab.dig_deeper(before["run_id"])
    after = result_of(view, "official_vectors")
    research_box = after["research"]
    assert research_box["status"] == "waiting for research engine" and research_box["badge"] == "Queued"
    assert research_box["status_line"] == "Status: waiting for research engine"
    fields = {f["label"]: f["value"] for f in research_box["fields"]}
    assert fields["Finding"] == "Official test vectors: Failed, 3 of 484 cases wrong on acme-sign 1.4.2"
    assert "168, 171 and 364" in fields["Question"]
    assert "No answer yet" in research_box["note"] and "answer" not in fields
    assert (after["code"], after["summary"]) == (before["code"], before["summary"])  # the result itself is unchanged
    again = result_of(lab.dig_deeper(before["run_id"]), "official_vectors")["research"]
    assert again["id"] == research_box["id"]  # a second click changes nothing
    with lab.db() as db:
        rows = db.query(ResearchRequestRow).filter_by(run_id=before["run_id"]).all()
        assert len(rows) == 1 and rows[0].engine == "isogeny.rule-engine/1"
        assert set(rows[0].evidence) == {"run_id", "spec_hash", "review_id"}


def test_mark_reviewed_records_the_users_own_decision(demo_flow):
    lab = demo_flow.lab
    run_id = result_of(demo_flow.first, "bad_signatures")["run_id"]
    first = result_of(lab.mark_reviewed(run_id), "bad_signatures")
    assert first["reviewed"]["text"] == "You marked this result as reviewed." and first["code"] == "failed"
    assert result_of(lab.mark_reviewed(run_id), "bad_signatures")["reviewed"] == first["reviewed"]
