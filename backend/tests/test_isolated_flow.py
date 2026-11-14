"""The same tests in isolated mode (containers), and what happens when isolated mode is asked for but missing."""
import json
import re

import pytest

from app import components, runner
from app.db import TestRunRow
from conftest import demo_plan, make_lab, result_of


def test_tests_run_in_containers_and_the_mode_is_recorded(docker_ready, tmp_path, monkeypatch):
    lab = make_lab(tmp_path, force_mode=None, speed_rounds=40, speed_repeats=5)  # the real default: 200 pairs
    try:
        assert lab.mode.name == "isolated" and lab.session_json(None)["mode"] == "isolated"
        assert lab.session_json(None)["mode_line"] == "Isolated mode: our demo software runs in a locked-down container with no network."
        plan = demo_plan(lab)
        # The Verify step's software check also runs in the container, never as a local process.
        monkeypatch.setattr(components, "run_component", lambda *a, **k: pytest.fail("Verify ran the component locally"))
        software = next(r for r in lab.verify(plan.imp["id"])["results"] if r["claim"]["location_kind"] == "software")
        assert software["result"] == "True" and len(software["evidence"]) == 5
        for item in software["evidence"][:4]:
            assert item["tool"] == components.ISOLATED_TOOL and item["command"].startswith("docker run ") and "--network none" in item["command"]
            assert item["tool_version"] == f"image {lab.mode.components_image}"
        assert components.WITHHELD in json.dumps(software) and not re.search(r"\b[0-9a-f]{64}\b", software["evidence"][1]["output"])
        monkeypatch.undo()
        lab.remove_test(plan.id, plan.item["official_vectors"])  # the 484-case run in a container is covered by test_isolation.py
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 300)
        first = lab.lab_view(plan.id)
        assert [r["result"]["label"] for r in first["rows"]] == ["Failed", "Passed", "Failed", "Measured"]
        lab.start_retest(plan.id, "1.4.3")
        lab.wait_until_idle(plan.id, 300)
        after = lab.lab_view(plan.id)
        assert [r["after"]["label"] for r in after["rows"]] == ["Failed", "Passed", "Passed", "No slowdown beyond measured noise"]
        assert all(r[w]["control"]["outcome"] == "as_expected" for r in after["rows"] for w in ("result", "after"))
        bad = result_of(after, "bad_signatures")
        assert bad["mode"] == "isolated" and "docker run" in bad["run_record"]["outputs"][0]["text"] and "--network none" in bad["run_record"]["outputs"][0]["text"]
        assert {"label": "Mode", "value": "Isolated mode: locked-down container, no network", "tag": None} in bad["run_record"]["meta"]
        with lab.db() as db:
            runs = db.query(TestRunRow).all()
            assert len(runs) == 8 and {r.mode for r in runs} == {"isolated"}
            for run in runs:  # old and new were measured in the same container run: numbers from two modes are never compared
                if run.phase == "retest" and "benches" in run.raw:
                    assert run.raw["batch"]["mode"] == "isolated" and {b["role"] for b in run.raw["benches"]} == {"old", "new", "control"}
    finally:
        lab.stop()


def test_the_proof_of_a_change_runs_in_containers_and_says_so(docker_ready, tmp_path):
    """Phase 3a, isolated mode: Connect demo code, and the proof that starts by itself reruns the plan's tests on the
    changed code through the same container runner. It passes, and every proof run says isolated mode."""
    lab = make_lab(tmp_path, force_mode=None, speed_rounds=40, speed_repeats=5)  # the real default: 200 pairs
    try:
        assert lab.mode.name == "isolated"
        plan = demo_plan(lab)
        lab.remove_test(plan.id, plan.item["official_vectors"])  # the 484-case run in a container is covered by test_isolation.py
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 300)
        connected = next(f for f in lab.connect_code(plan.id) if f["kind"] == "code")
        assert connected["status"] == "proving" and connected["proof"]["total"] == 4
        lab.wait_until_idle(plan.id, 300)
        code = next(f for f in lab.fix_states(plan.id) if f["kind"] == "code")
        review = code["proof"]["review"]
        assert code["status"] == "ready" and code["proof"]["state"] == "passed" and review["believed"] is True and review["offered"] is True
        assert all(review["checks"].values()) and review["speed"] == {"ok": True, "reason": "no_slowdown"}
        assert {t["kind"]: (t["first"]["code"], t["proof"]["code"]) for t in code["proof"]["tests"]} == {
            "tls_versions": ("failed", "failed"), "certificate": ("passed", "passed"), "bad_signatures": ("failed", "passed"),
            "speed_size": ("measured", "no_slowdown")}
        with lab.db() as db:
            runs = db.query(TestRunRow).filter_by(phase="proof").all()
            assert len(runs) == 4 and {r.mode for r in runs} == {"isolated"}
            for run in runs:
                if run.component_name is None:
                    continue  # a server test: handshakes from the app itself, no component of ours runs
                assert (run.component_version, run.baseline_version) == ("1.4.3", "1.4.2")
                batch = run.raw["batch"]  # how the harness job was started, as the run recorded it
                assert batch["mode"] == "isolated" and batch["command"].startswith("docker run ") and "--network none" in batch["command"]
                shown = lab._result(db, run)
                assert shown["mode"] == "isolated" and shown["control"]["outcome"] == "as_expected"
                meta = shown["run_record"]["meta"]
                assert {"label": "Mode", "value": "Isolated mode: locked-down container, no network", "tag": None} in meta
                assert {"label": "Code", "tag": "demo", "value": f"the change on branch fix/ecdsa-range-check, commit {code['change']['head_commit'][:7]}, "
                                                                 "the same byte for byte as our bundled acme-sign 1.4.3"} in meta
                if "benches" in run.raw:  # the old and the changed code were timed side by side in the same container run
                    assert {b["role"] for b in run.raw["benches"]} == {"old", "new", "control"}
        # the Fixes step says which mode the proof ran in
        detail = next(f for f in lab.fixes_view(plan.id)["fixes"] if f["kind"] == "code")
        facts = {fact["label"]: "".join(part["v"] for part in fact["value"]) for fact in next(s for s in detail["sections"] if s["key"] == "details")["facts"]}
        assert detail["status"]["word"] == "Ready for review" and facts["Mode"] == "Isolated mode: locked-down container, no network"
    finally:
        lab.stop()


def test_isolated_mode_asked_for_but_missing_never_runs_software_unisolated(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_probe", lambda: (False, None, None))
    lab = make_lab(tmp_path, force_mode="isolated")
    try:
        assert lab.mode.name == "isolated" and lab.session_json(None)["mode_line"] == runner.ISOLATED_UNAVAILABLE_LINE
        plan = demo_plan(lab)
        # Verify does not run the signing component as a local process instead: it says it couldn't check.
        monkeypatch.setattr(components, "run_component", lambda *a, **k: pytest.fail("Verify ran the component locally"))
        software = next(r for r in lab.verify(plan.imp["id"])["results"] if r["claim"]["location_kind"] == "software")
        assert software["result"] == "Couldn't check" and software["evidence"] == []
        assert software["reason"] == "Isolated mode is not available on this computer, so the component was not run."
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 120)
        labels = {r["kind"]: r["result"]["label"] for r in lab.lab_view(plan.id)["rows"]}
        unavailable = "Couldn't run (isolated mode is not available)"
        assert labels == {"tls_versions": "Failed", "certificate": "Passed", "official_vectors": unavailable,
                          "bad_signatures": unavailable, "speed_size": unavailable}
        with lab.db() as db:
            assert {r.mode for r in db.query(TestRunRow).all()} == {"isolated"}
    finally:
        lab.stop()


def test_docker_without_images_stays_in_demo_mode_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_probe", lambda: (True, None, None))
    lab = make_lab(tmp_path, force_mode=None)
    try:
        line = lab.session_json(None)["mode_line"]
        assert lab.mode.name == "demo" and line.startswith("Demo mode: running our own demo software, not isolated.")
        assert "the test images are not prepared yet" in line
    finally:
        lab.stop()
