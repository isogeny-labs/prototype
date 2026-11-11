"""The slowdown rule: synthetic timings, the slowed control, the exclusive gate, and repeated real retests."""
import random
import threading
import time

from app.canonical import sha256_hex
from app.jobs import ExclusiveGate
from app.research import RuleEngine
from app.reviewer import RuleReviewer, paired_comparison
from conftest import demo_plan, result_of
from test_records import DEMO_CLAIMS

ROUNDS, REPEATS = 4, 25
SPEC = RuleEngine(ROUNDS, REPEATS).propose_tests(DEMO_CLAIMS)["tests"][4]
RULE = SPEC["rule"]


def timings(seed, base, extra=0.0, factor=1.0):
    rng = random.Random(seed)
    return [round((base + abs(rng.gauss(0, base * 0.04)) + (base * 3 if rng.random() < 0.02 else 0)) * factor + extra, 4)
            for _ in range(ROUNDS * REPEATS)]


def benches(role, key, sign, verify):
    return [{"round": r, "subject": key, "role": role, "rc": 0, "sign_ms": sign[r * REPEATS:(r + 1) * REPEATS],
             "verify_ms": verify[r * REPEATS:(r + 1) * REPEATS], "signature_bytes": 71, "public_key_bytes": 65,
             "all_verified": True} for r in range(ROUNDS)]


def retest_review(new_factor=1.0, new_extra=0.0, control_extra=3.0, seed=1):
    old = benches("old", "acme-sign-1.4.2", timings(seed, 7.0), timings(seed + 1, 13.0))
    new = benches("new", "acme-sign-1.4.3", timings(seed + 2, 7.0, new_extra, new_factor), timings(seed + 3, 13.0, new_extra, new_factor))
    control = benches("control", "control-slow:acme-sign-1.4.3", timings(seed + 4, 7.0, new_extra + control_extra, new_factor),
                      timings(seed + 5, 13.0, new_extra + control_extra, new_factor))
    raw = {"benches": old + new + control, "reference": None, "exclusive": True}
    run = {"spec_hash": sha256_hex(SPEC), "phase": "retest", "raw": raw}
    out = RuleReviewer().review({"spec": SPEC, "spec_hash": sha256_hex(SPEC), "proposed_by": "isogeny.rule-engine/1", "run": run})
    return out["verdict"]["code"], out["control"]["outcome"], out["detail"]


def test_the_rule_is_written_into_the_locked_test():
    assert RULE == {"type": "paired_slowdown", "first_run": "report_only", "ops": ["sign", "verify"],
                    "noise_factor_milli": 1858, "sigma": 4, "floor_percent": 3}
    assert SPEC["inputs"]["exclusive"] is True and SPEC["inputs"]["pairs"] == ROUNDS * REPEATS


def test_the_formula():
    old = [10.0, 10.0, 10.0, 10.0]
    c = paired_comparison(old, [11.0, 11.2, 10.8, 11.0], RULE)
    # d = 1.0, 1.2, 0.8, 1.0 -> D = 1.0, MAD = 0.1, noise = 1.858 * 0.1 / 2 = 0.0929; 1.0 - 4 * 0.0929 > 0.3
    assert c["D_ms"] == 1.0 and c["noise_ms"] == 0.0929 and c["floor_ms"] == 0.3 and c["flagged"] is True
    assert c["change_percent"] == 10.0 and abs(c["band_percent"] - 3.716) < 1e-9
    assert paired_comparison(old, [10.2, 10.2, 10.2, 10.2], RULE)["flagged"] is False   # +2%: real, but under the 3% floor
    assert paired_comparison(old, [9.0, 9.0, 9.0, 9.0], RULE)["flagged"] is False       # faster is never a slowdown
    assert paired_comparison(old, [10.0, 30.0, 10.0, 10.0], RULE)["flagged"] is False   # one slow outlier is not a slowdown


def test_same_speed_is_never_flagged_and_the_control_always_is():
    for seed in range(0, 200, 10):
        code, control, detail = retest_review(seed=seed)
        assert (code, control) == ("no_slowdown", "as_expected"), seed
        assert 0 < detail["noise_band_percent"] < 5
        assert detail["control"]["sign"]["flagged"] and detail["control"]["verify"]["flagged"]


def test_a_clear_slowdown_is_flagged():
    for seed in range(0, 100, 10):
        code, control, detail = retest_review(new_factor=1.3, seed=seed)
        assert (code, control) == ("slowdown", "as_expected")
        assert 25 < detail["comparison"]["sign"]["change_percent"] < 35


def test_a_tiny_real_change_under_the_floor_is_not_flagged():
    for seed in range(0, 100, 10):
        assert retest_review(new_factor=1.01, seed=seed)[0] == "no_slowdown"


def retest_words(old_sign, new_sign, old_verify, new_verify):
    """The on-screen words for a retest with these exact timings (through the real reviewer and present)."""
    from app import present
    n = ROUNDS * REPEATS
    old = benches("old", "acme-sign-1.4.2", old_sign, old_verify)
    new = benches("new", "acme-sign-1.4.3", new_sign, new_verify)
    control = benches("control", "control-slow:acme-sign-1.4.3", [x + 3 for x in new_sign], [x + 3 for x in new_verify])
    run = {"spec_hash": sha256_hex(SPEC), "phase": "retest", "component": {"name": "acme-sign", "version": "1.4.3"}, "baseline_version": "1.4.2",
           "mode": "demo", "started_at": "2026-11-11T00:00:00.000Z", "finished_at": "2026-11-11T00:00:20.000Z", "duration_ms": 20000,
           "raw": {"benches": old + new + control, "reference": None, "exclusive": True, "batch": {"command": "x"}}}
    assert len(old_sign) == n
    out = RuleReviewer().review({"spec": SPEC, "spec_hash": sha256_hex(SPEC), "proposed_by": "isogeny.rule-engine/1", "run": run})
    review = {"code": out["verdict"]["code"], "reason_code": None, "reason": None, "control": out["control"], "detail": out["detail"]}
    return present.lab_result(spec=SPEC, spec_hash=sha256_hex(SPEC), locked_at="", run_id=1, run=run, review=review, trusted=True,
                              mark=None, research=None, fix_version=None), out["detail"]


def test_a_difference_above_the_noise_but_under_the_rule_is_never_called_noise():
    """Between the noise band and the band plus 3% the rule does not flag. The words must then say what was
    measured, and must not say it is noise or that nothing got slower."""
    n = ROUNDS * REPEATS
    wobble = [0.01 * ((i % 5) - 2) for i in range(n)]                      # tiny, so the noise band is well under 1%
    old_sign, old_verify = [10.0] * n, [20.0] * n
    result, detail = retest_words(old_sign, [10.2 + w for w in wobble], old_verify, [20.4 + w for w in wobble])   # +2%
    band = detail["noise_band_percent"]
    assert result["label"] == "No slowdown beyond measured noise" and band < 1 < detail["comparison"]["sign"]["change_percent"]
    text = " ".join(result["what_happened"] + result["shows"])
    assert "is noise" not in text and "did not make signing or checking noticeably slower" not in text
    assert "is larger than that" in text and "so this is not called a slowdown" in text
    assert "above the measured noise but below the level this test calls a slowdown" in result["shows"][0]
    assert result["suggested_fix"].startswith("None needed under this test's rule.")
    # inside the band: the sentence quotes the band, not whatever was measured; a speed-up is never "noise" either way
    result, detail = retest_words(old_sign, [10.0 + w for w in wobble], old_verify, [20.0 + w for w in wobble])
    band = detail["noise_band_percent"]
    assert f"so a difference of {band}% or less is noise, not a slowdown." in result["what_happened"][1]
    assert result["suggested_fix"] == "None needed. No slowdown beyond measured noise was found."
    result, _ = retest_words(old_sign, [9.0 + w for w in wobble], old_verify, [18.0 + w for w in wobble])        # 10% faster
    assert "10.0% or less is noise" not in result["what_happened"][1] and result["label"] == "No slowdown beyond measured noise"


def test_a_control_that_the_same_rule_does_not_flag_means_no_trust():
    assert retest_review(control_extra=0.0)[:2] == ("couldnt_trust", "not_as_expected")
    assert retest_review(new_factor=1.3, control_extra=0.0)[:2] == ("couldnt_trust", "not_as_expected")


def test_missing_or_failed_timings_are_never_a_result():
    old = benches("old", "a", timings(1, 7.0), timings(2, 13.0))
    new = benches("new", "b", timings(3, 7.0), timings(4, 13.0))
    control = benches("control", "c", timings(5, 10.0), timings(6, 16.0))

    def code(items):
        run = {"spec_hash": sha256_hex(SPEC), "phase": "retest", "raw": {"benches": items, "reference": None}}
        out = RuleReviewer().review({"spec": SPEC, "spec_hash": sha256_hex(SPEC), "proposed_by": "x", "run": run})
        return out["verdict"]["code"], out["verdict"]["reason_code"]
    assert code(old + new + control)[0] == "no_slowdown"
    assert code(old + new[:-1] + control) == ("couldnt_run", "component_no_answer")            # a round is missing
    assert code(old[1:] + new + control) == ("couldnt_run", "component_no_answer")
    assert code(old + new + control[:-1])[0] == "couldnt_trust"                                # the control broke down
    bad = [dict(new[0], all_verified=False)] + new[1:]
    assert code(old + bad + control) == ("couldnt_run", "component_no_answer")


def test_the_gate_gives_a_measurement_the_computer_to_itself():
    gate, events, stop = ExclusiveGate(), [], threading.Event()

    def worker():
        while not stop.is_set():
            with gate.shared():
                assert not gate.exclusive_now
                time.sleep(0.002)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for _ in range(5):
        time.sleep(0.01)
        with gate.exclusive():  # gets in although shared work never stops arriving
            events.append(gate.shared_now)
            time.sleep(0.01)
            events.append(gate.shared_now)
    stop.set()
    for t in threads:
        t.join()
    assert events == [0] * 10 and gate.shared_seen_during_exclusive == 0


def test_real_retests_never_flag_the_fix_while_other_jobs_run(lab):
    """1.4.2 -> 1.4.3, three times over, each time with the other tests running in the same Run: never a
    slowdown, the slowed control flagged every time, and the measurement always alone on the gate."""
    plan = demo_plan(lab)
    lab.remove_test(plan.id, plan.item["official_vectors"])  # keeps the repeats quick; three other tests still run alongside
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 240)
    assert result_of(lab.lab_view(plan.id), "speed_size")["label"] == "Measured"
    for attempt in range(3):
        lab.start_retest(plan.id, "1.4.3")
        lab.wait_until_idle(plan.id, 240)
        after = result_of(lab.lab_view(plan.id), "speed_size", "after")
        assert after["label"] == "No slowdown beyond measured noise", (attempt, after["summary"])
        assert after["control"]["outcome"] == "as_expected"
        assert result_of(lab.lab_view(plan.id), "bad_signatures", "after")["label"] == "Passed"
    assert lab.jobs.gate.shared_seen_during_exclusive == 0
    with lab.db() as db:
        from app.db import TestRunRow
        speed = [r for r in db.query(TestRunRow).all() if r.plan_item_id == plan.item["speed_size"] and r.phase == "retest"]
        assert len(speed) == 3
        for run in speed:  # old and new were measured in the same job, in the same mode, in alternating rounds
            assert run.mode == "demo" and run.baseline_version == "1.4.2" and run.component_version == "1.4.3"
            order = [b["role"] for b in run.raw["benches"]]
            assert order[:6] == ["old", "new", "control", "control", "new", "old"]
