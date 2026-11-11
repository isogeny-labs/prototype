"""Records: locked tests, append-only runs and reviews, and the exact canonical form their fingerprints use."""
import hashlib
import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.canonical import canonical_bytes, loads_strict, sha256_hex
from app.db import APPEND_ONLY_TABLES, TestRunRow, TestSpecRow
from app.research import RuleEngine
from app.testlab import read_spec
from conftest import demo_plan, run_kind

DEMO_CLAIMS = [
    {"location": "localhost:8443", "location_kind": "server", "kind": "protocol_versions", "claimed_value": "TLS 1.3",
     "detail": {"host": "localhost", "port": 8443, "versions": ["TLS 1.3"]}},
    {"location": "localhost:8443", "location_kind": "server", "kind": "certificate", "claimed_value": "ECDSA P-256",
     "detail": {"host": "localhost", "port": 8443, "algorithm": "ECDSA P-256"}},
    {"location": "acme-sign 1.4.2", "location_kind": "software", "kind": "signature_algorithm", "claimed_value": "ECDSA P-256",
     "detail": {"component": "acme-sign", "version": "1.4.2", "algorithm": "ECDSA P-256"}},
]


def test_canonical_form_is_exact():
    assert canonical_bytes({"b": 1, "a": [True, None, "é"]}) == '{"a":[true,null,"é"],"b":1}'.encode()
    assert sha256_hex({"a": 1}) == hashlib.sha256(b'{"a":1}').hexdigest()
    with pytest.raises(ValueError):
        canonical_bytes({"x": float("nan")})
    for bad in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1} x', b"\xff"):
        with pytest.raises(ValueError):
            loads_strict(bad)
    assert loads_strict(b'{"a":1}') == {"a": 1}


def _all_specs():
    engine = RuleEngine(3, 20)
    specs = engine.propose_tests(DEMO_CLAIMS)["tests"]
    return specs + [engine.design_test({"catalog_id": k, "claims": DEMO_CLAIMS}) for k in ("pq_readiness", "mldsa_compare")]


def test_a_locked_test_names_no_version_mode_or_time():
    def keys(value):
        if isinstance(value, dict):
            for k, v in value.items():
                yield k
                yield from keys(v)
        elif isinstance(value, list):
            for v in value:
                yield from keys(v)

    def floats(value):
        if isinstance(value, float):
            yield value
        elif isinstance(value, dict):
            for v in value.values():
                yield from floats(v)
        elif isinstance(value, list):
            for v in value:
                yield from floats(v)

    for spec in _all_specs():
        text_form = canonical_bytes(spec).decode()
        assert "1.4.2" not in text_form and "1.4.3" not in text_form, spec["kind"]
        assert not {"version", "mode", "started_at", "finished_at", "locked_at", "baseline_version", "time"} & set(keys(spec))
        assert not list(floats(spec)), "thresholds are whole numbers, so the fingerprint is exact"
        for part in ("question", "method", "inputs", "control", "rule", "target"):
            assert spec[part], part
        assert spec["control"]["must"], "every test says what its control must do"


def test_the_same_test_always_gets_the_same_fingerprint():
    assert [sha256_hex(s) for s in _all_specs()] == [sha256_hex(s) for s in _all_specs()]
    assert len({sha256_hex(s) for s in _all_specs()}) == 7


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_raw_sql_cannot_change_or_delete_specs_runs_or_reviews(demo_flow, table):
    with demo_flow.lab.db() as db:
        before = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert before > 0
        column = {"test_specs": "kind", "test_runs": "mode", "reviews": "code"}[table]
        for statement in (f"UPDATE {table} SET {column} = 'passed'", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == before


def test_stored_specs_match_their_fingerprints(demo_flow):
    with demo_flow.lab.db() as db:
        rows = db.query(TestSpecRow).all()
        assert len(rows) == 7
        for row in rows:
            spec, ok = read_spec(row)
            assert ok and sha256_hex(spec) == row.hash and row.proposed_by == "isogeny.rule-engine/1"


def test_a_run_refuses_to_start_when_the_stored_test_was_changed(lab):
    plan = demo_plan(lab)
    with lab.db() as db:  # only possible by removing the guard first: this is someone tampering with the database file
        db.execute(text("DROP TRIGGER test_specs_no_update"))
        db.execute(text("UPDATE test_specs SET canonical = replace(canonical, 'Any wrong answer means Failed', 'Up to five wrong answers still pass') "
                        "WHERE kind = 'bad_signatures'"))
        db.commit()
    result = run_kind(lab, plan, "bad_signatures")
    assert result["label"] == "Couldn't trust this run"
    with lab.db() as db:
        run = db.get(TestRunRow, result["run_id"])
        assert run.raw["problem"]["code"] == "spec_changed" and "subject" not in run.raw  # the component was never run
    # the untouched tests still run normally
    assert run_kind(lab, plan, "certificate")["label"] == "Passed"


def test_every_stored_output_is_redacted(demo_flow):
    with demo_flow.lab.db() as db:
        for run in db.query(TestRunRow).all():
            dumped = json.dumps(run.raw) + run.logs
            assert "PRIVATE KEY" not in dumped and '"private_key"' not in dumped
