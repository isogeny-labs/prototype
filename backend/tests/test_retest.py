"""Retest on the corrected demo version: the same locked tests, before and after."""
import pytest

from app.db import ReviewRow, RetestRow, TestRunRow
from app.errors import BadRequest, Conflict
from conftest import demo_plan, result_of

KINDS = ("tls_versions", "certificate", "official_vectors", "bad_signatures", "speed_size")


def test_retest_answers_match_the_answer_key(demo_flow):
    labels = [result_of(demo_flow.after, k, "after")["label"] for k in KINDS]
    assert labels == ["Failed", "Passed", "Passed", "Passed", "No slowdown beyond measured noise"]
    # the first results are still there, next to the new ones
    assert [result_of(demo_flow.after, k)["label"] for k in KINDS] == ["Failed", "Passed", "Failed", "Failed", "Measured"]
    pq_before, pq_after = result_of(demo_flow.after, "pq_readiness"), result_of(demo_flow.after, "pq_readiness", "after")
    assert pq_before["label"] == pq_after["label"]


def test_the_same_locked_tests_were_rerun(demo_flow):
    with demo_flow.lab.db() as db:
        runs = db.query(TestRunRow).all()
        first = {r.plan_item_id: r for r in runs if r.phase == "first"}
        retest = {r.plan_item_id: r for r in runs if r.phase == "retest"}
        assert len(first) == len(retest) == 7 and set(first) == set(retest)
        for item_id, before in first.items():
            assert before.spec_hash == retest[item_id].spec_hash and len(before.spec_hash) == 64
        reviews = {r.run_id: r for r in db.query(ReviewRow).all()}
        assert all(reviews[r.id].spec_hash == r.spec_hash and reviews[r.id].spec_hash_ok for r in runs)
        assert db.query(RetestRow).count() == 1
    for row in demo_flow.after["rows"]:
        assert row["result"]["locked_test"]["fingerprint"] == row["after"]["locked_test"]["fingerprint"]
        assert row["result"]["locked_test"]["locked_at"] == row["after"]["locked_test"]["locked_at"]


def test_component_version_and_mode_are_recorded_in_every_run(demo_flow):
    with demo_flow.lab.db() as db:
        runs = db.query(TestRunRow).all()
        kinds = {i: k for k, i in demo_flow.plan.item.items()}
        for run in runs:
            assert run.mode == "demo" and run.runner == "isogeny.runner/1" and run.started_at <= run.finished_at
            software = kinds[run.plan_item_id] in ("official_vectors", "bad_signatures", "speed_size", "mldsa_compare")
            expected = ("acme-sign", "1.4.3" if run.phase == "retest" else "1.4.2") if software else (None, None)
            assert (run.component_name, run.component_version) == expected
            assert run.baseline_version == ("1.4.2" if software and run.phase == "retest" else None)
            assert (run.retest_id is not None) == (run.phase == "retest")


def test_before_and_after_view(demo_flow):
    view = demo_flow.after
    assert view["view"] == "before_after"
    # each side says which code it ran on: here both are our bundled demo versions (no code was connected)
    bundled = [{"t": "text", "v": "the bundled demo version"}]
    assert view["columns"] == {"test": "Test", "before": "Before: acme-sign 1.4.2", "after": "After: acme-sign 1.4.3",
                               "before_note": bundled, "after_note": bundled,
                               "before_heading": "Before: acme-sign 1.4.2, the bundled demo version",
                               "after_heading": "After: acme-sign 1.4.3, the bundled demo version"}
    assert view["code_line"] == [{"t": "text", "v": "Code they ran on: before, the bundled demo version of acme-sign 1.4.2; "
                                                    "after, the bundled demo version of acme-sign 1.4.3."}]
    text = "".join(p["v"] for p in view["subline"] if p["t"] != "time")
    assert text == "Before and after: the same seven locked tests, run on acme-sign 1.4.2 and then on acme-sign 1.4.3. Retest finished ."
    assert [p["t"] for p in view["subline"]].count("time") == 1
    lines = {r["kind"]: r["control_line"] for r in view["rows"]}
    assert lines["official_vectors"] == lines["tls_versions"] == "Control failed as expected in both runs."
    assert lines["speed_size"] == lines["pq_readiness"] == lines["mldsa_compare"] == "Control behaved as expected in both runs."
    assert all(r["result_status"] is None and r["after_status"] is None for r in view["rows"])
    assert view["retest"]["running"] is False and view["retest"]["can_start"] is True
    assert [v["version"] for v in view["retest"]["versions"]] == ["1.4.3", "1.4.2"]
    assert {v["tag"] for v in view["retest"]["versions"]} == {"demo"}
    assert "Only our two demo versions can be chosen here." in view["retest"]["menu_note"]
    assert result_of(view, "tls_versions", "after")["short"].startswith("Server still accepts TLS 1.2.")
    assert result_of(view, "official_vectors", "after")["summary"] == "484 of 484 official cases right."
    assert result_of(view, "bad_signatures", "after")["summary"] == "Rejects r=0, s=0 and every other bad signature tried."
    assert result_of(view, "bad_signatures", "after")["component"] == "acme-sign 1.4.3"


def test_speed_after_the_retest_compares_side_by_side(demo_flow):
    after = result_of(demo_flow.after, "speed_size", "after")
    table = after["evidence"][0]
    assert table["title"] == "Timings and sizes, before and after"
    assert [c["label"] for c in table["columns"]] == ["What was measured", "acme-sign 1.4.2\nbefore", "acme-sign 1.4.3\nafter",
                                                      "Change", "Reference library\n(cryptography)"]
    assert [r[0] for r in table["rows"]] == ["Sign, median", "Sign, slowest 1 in 100", "Verify, median", "Verify, slowest 1 in 100",
                                             "Signature size, this run", "Public key size"]
    assert table["rows"][4][3] == "none"   # same key, same message, deterministic signing: old and new sign identically
    assert "70 to 72 bytes" in table["note"] and "not a real difference" in table["note"]
    assert all("Summary written by the app from the stored run." in o["text"] and '"command"' not in o["text"]
               for o in after["run_record"]["outputs"])
    assert table["rows"][5][1:4] == ["65 bytes", "65 bytes", "none"]
    meta = {m["label"]: m["value"] for m in table["meta"] if m["label"]}
    assert meta["Repeats"] == "100 sign and 100 verify per version, in 25 alternating rounds" and meta["Measured noise"].startswith("±")
    assert "for scale only" in table["note"] and "side by side in this run, in the same mode" in table["note"]
    assert [o["title"] for o in after["run_record"]["outputs"]] == ["Output summary, acme-sign 1.4.2", "Output summary, acme-sign 1.4.3"]
    assert after["suggested_fix"] == "None needed. No slowdown beyond measured noise was found."
    assert "Noise: ±" in after["short"]
    with demo_flow.lab.db() as db:
        raw = db.get(TestRunRow, after["run_id"]).raw
    assert raw["subjects"] == {"old": "acme-sign-1.4.2", "new": "acme-sign-1.4.3", "control": "control-slow:acme-sign-1.4.3"}


def test_only_our_demo_versions_can_be_chosen(lab):
    plan = demo_plan(lab)
    for version in ("1.4.4", "../1.4.3", "", "latest", "acme-sign-1.4.3"):
        with pytest.raises(BadRequest):
            lab.start_retest(plan.id, version)
    with pytest.raises(Conflict):  # nothing has been run yet, so there is nothing to compare with
        lab.start_retest(plan.id, "1.4.3")
    view = lab.lab_view(plan.id)
    assert view["view"] == "results" and view["retest"]["can_start"] is False and view["retest"]["blocked_reason"]
    assert view["download"]["can_start"] is False
    with lab.db() as db:
        assert db.query(RetestRow).count() == 0 and db.query(TestRunRow).count() == 0


def test_retest_runs_in_the_background_and_shows_progress(lab):
    plan = demo_plan(lab)
    for kind in ("official_vectors", "speed_size"):
        lab.remove_test(plan.id, plan.item[kind])
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 60)
    view = lab.start_retest(plan.id, "1.4.3")
    assert view["view"] == "before_after" and view["retest"]["running"] is True and view["retest"]["can_start"] is False
    assert view["retest"]["progress_text"].startswith("Retest running: ") and view["retest"]["progress_text"].endswith("of 3 tests finished.")
    assert "".join(p["v"] for p in view["subline"]).endswith("Retest running.")
    pending = [r for r in view["rows"] if r["after"] is None]
    assert pending and all(r["after_status"]["status"] in ("waiting", "running") for r in pending)
    with pytest.raises(Conflict):
        lab.start_retest(plan.id, "1.4.3")
    with pytest.raises(Conflict):
        lab.run_all(plan.id)
    assert lab.plan_view(plan.id)["can_run_all"] is False
    lab.wait_until_idle(plan.id, 60)
    done = lab.lab_view(plan.id)
    assert [r["after"]["label"] for r in done["rows"]] == ["Failed", "Passed", "Passed"]
    assert "the same three locked tests" in done["subline"][0]["v"]
