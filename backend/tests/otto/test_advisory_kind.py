"""Phase 5c, step 3: the advisory check. A test built from a design (data, never code), run by the existing
runner, decided by the existing reviewer, worded plainly."""
import copy
import json

import pytest

from app.canonical import sha256_hex
from app.db import ReviewRow, TestRunRow, TestSpecRow
from app.engine import research, vectors
from app.engine.reviewer import PROOF_PASS_CODES, ReviewNotAllowed, RuleReviewer
from app.otto import designs
from app.run.execute import signing
from conftest import demo_plan, play_back_speed

import otto_helpers as helpers

BANNED = ("secure", "score", "severity", "critical", "time to hack", "time-to-hack")


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


# ---------------------------------------------------------------- the design: data, checked every time it is used

def test_a_design_picks_published_cases_and_counts_them():
    made = helpers.design()
    cases = {c.id: c for c in vectors.load_wycheproof("ecdsa_p256").cases}
    ids = made["cases"]["ids"]
    assert ids and all("InvalidSignature" in cases[i].flags for i in ids)
    assert {"168", "171"} <= set(ids) and made["cases"]["must_reject"] == len(ids) and made["cases"]["must_accept"] == 0
    assert made["cases"]["sha256"] == vectors.WYCHEPROOF["ecdsa_p256"]["sha256"]
    assert designs.check_design(made) is made
    # ids and flags together, in file order, each once
    both = helpers.design(flags=("MissingZero",), ids=("168", "6"))
    assert both["cases"]["ids"] == ["6", "168"]


@pytest.mark.parametrize("flags, ids, words", [
    (("ValidSignature",), (), "no case that must be rejected"),      # the control could never fail
    (("NoSuchKindOfCase",), (), "no cases of the kind"),
    ((), ("99999",), "no case 99999"),
    ((), (), "at least one flag or case id"),
])
def test_a_selection_that_cannot_work_is_refused(flags, ids, words):
    with pytest.raises(designs.DesignError) as refused:
        helpers.design(flags=flags, ids=ids)
    assert words in str(refused.value)


def test_a_design_note_cannot_ask_for_anything_else():
    for change in ({"block": "run_this_script"}, {"control": "none"}, {"command": "rm -rf /"}, {"decision": "maybe"}):
        with pytest.raises(designs.DesignError):
            designs.compile_note({**helpers.note(), **change}, "CVE-2022-21449", "Blank signature accepted", helpers.STEP)
    with pytest.raises(designs.DesignError):   # the question must name the program, once
        designs.compile_note({**helpers.note(), "question": "Is it fine?"}, "CVE-2022-21449", "Blank signature accepted", helpers.STEP)
    assert designs.no_test_reason({"decision": "no_test", "reason": "The runner covers ECDSA P-256 only."}) == "The runner covers ECDSA P-256 only."
    assert designs.no_test_reason(helpers.note()) is None


def test_a_changed_design_is_refused():
    made = helpers.design()
    for change in (lambda d: d["cases"]["ids"].append("1"),                      # a case its selection does not pick
                   lambda d: d["cases"]["ids"].pop(),                           # a case dropped
                   lambda d: d["cases"].__setitem__("sha256", "0" * 64),        # another file
                   lambda d: d["cases"].__setitem__("must_reject", 1),          # a count that is not the file's
                   lambda d: d.__setitem__("control", "none"),
                   lambda d: d.__setitem__("rule", "most_cases_match"),
                   lambda d: d.__setitem__("code", "print(1)"),
                   lambda d: d.__setitem__("advisory", "not an id"),
                   lambda d: d["model_step"].__setitem__("prompt_sha256", "short")):
        broken = copy.deepcopy(made)
        change(broken)
        with pytest.raises(designs.DesignError):
            designs.check_design(broken)
    for not_a_design in (None, [], "x", {"schema": "other"}):
        with pytest.raises(designs.DesignError):
            designs.check_design(not_a_design)


def test_the_locked_test_is_complete_and_names_no_version(lab):
    plan = demo_plan(lab)
    made = helpers.design()
    spec = helpers.spec_for(lab, plan.id, made)
    assert spec["schema"] == research.SPEC_SCHEMA and spec["kind"] == "advisory_cases"
    assert spec["title"] == "Advisory check: Blank signature accepted (CVE-2022-21449)" == research.title_of("advisory_cases", spec)
    assert spec["target"] == {"kind": "software", "component": "acme-sign", "algorithm": "ECDSA P-256", "claim": spec["target"]["claim"]}
    assert spec["inputs"]["cases"] == made["cases"]["ids"] and spec["inputs"]["advisory"]["design_sha256"] == designs.design_sha256(made)
    assert spec["control"]["kind"] == "accept_all_verifier" and spec["rule"]["type"] == "all_cases_match"
    assert "acme-sign" in spec["question"] and "{program}" not in spec["question"]
    text = json.dumps(spec)
    assert "1.4.2" not in text and "demo mode" not in text.lower()
    assert sha256_hex(spec) == sha256_hex(helpers.spec_for(lab, plan.id, helpers.design()))   # the same design is the same test
    assert not any(word in t.lower() for t in _texts(spec) for word in BANNED)


def test_the_kind_is_known_wherever_a_test_kind_must_be():
    assert "advisory_cases" in research.SOFTWARE_TEST_KINDS and "advisory_cases" not in research.ALL_KINDS   # never in the + Add test catalog
    assert PROOF_PASS_CODES["advisory_cases"] == "passed"
    assert callable(RuleReviewer()._advisory_cases)
    assert designs.PROPOSED_BY != RuleReviewer.engine_id and designs.PROPOSED_BY != research.RuleEngine.engine_id


# ---------------------------------------------------------------- run by the runner, decided by the reviewer

def test_the_check_fails_on_the_affected_demo_version(lab):
    plan = demo_plan(lab)
    made = helpers.design()
    item_id = helpers.add_check(lab, plan.id, made)
    total = len(made["cases"]["ids"])
    card = next(t for t in lab.plan_view(plan.id)["tests"] if t["id"] == item_id)
    assert card["title"] == "Advisory check: Blank signature accepted (CVE-2022-21449)" and card["origin"] == "added"
    lab.run_test(plan.id, item_id)
    lab.wait_until_idle(plan.id, 240)
    first = helpers.result_for(lab, plan.id, item_id)
    assert first["label"] == "Failed" and first["control"]["outcome"] == "as_expected"
    assert first["component"] == "acme-sign 1.4.2" and f"2 of the {total} published cases" in first["plain"]
    wrong_rows = first["evidence"][0]["rows"]
    assert [r[0] for r in wrong_rows] == ["168", "171"] and all(r[2] == "reject" and r[3] == "accepted" for r in wrong_rows)
    assert first["shows"] and first["what_happened"] and first["plain"]
    # a failed result with a fix in Fixes shows that fix's one line in place of the "Suggested fix" text
    assert first["suggested_fix"] is None and first["fix_line"]["lead"]
    assert first["locked_test"]["fingerprint"] and "must get every invalid case wrong" in first["locked_test"]["fields"][3]["lines"][0]
    box = first["advisories"]
    assert box["items"][0]["id"] == "CVE-2022-21449" and box["tag"] == "quoted from the named source, not a result"
    assert box["items"][0]["href"] == "https://openjdk.org/groups/vulnerability/advisories/2022-04-19"
    assert not any(word in t.lower() for t in _texts(first) for word in BANNED)
    with lab.db() as db:
        run = db.query(TestRunRow).filter(TestRunRow.plan_item_id == item_id).one()
        review = db.query(ReviewRow).filter(ReviewRow.run_id == run.id).one()
        assert db.get(TestSpecRow, run.spec_hash).proposed_by == "isogeny.otto-pack/1" == review.proposed_by
        assert review.reviewer == "isogeny.rule-reviewer/1"


@pytest.mark.slow
def test_the_same_locked_check_is_rerun_on_the_fixed_version_and_passes(lab):
    plan = demo_plan(lab)
    made = helpers.design()
    item_id = helpers.add_check(lab, plan.id, made)
    total = len(made["cases"]["ids"])
    play_back_speed(lab)
    lab.run_all(plan.id)   # the check runs with the plan's other tests, like any test in it
    lab.wait_until_idle(plan.id, 240)
    first = helpers.result_for(lab, plan.id, item_id)
    assert first["label"] == "Failed" and first["component"] == "acme-sign 1.4.2"
    lab.start_retest(plan.id, "1.4.3")
    lab.wait_until_idle(plan.id, 300)
    after = helpers.result_for(lab, plan.id, item_id, "after")
    assert after["label"] == "Passed" and after["component"] == "acme-sign 1.4.3"
    assert after["locked_test"]["fingerprint"] == first["locked_test"]["fingerprint"]
    assert f"all {total} published cases" in after["plain"] and not any(word in t.lower() for t in _texts(after) for word in BANNED)
    assert after["suggested_fix"] == "None needed. Every case for this advisory got the right answer."


def test_a_control_that_does_not_fail_means_couldnt_trust(lab, monkeypatch):
    monkeypatch.setattr(signing, "CONTROL", "acme-sign-1.4.3")  # a "broken signer" that is not broken
    plan = demo_plan(lab)
    item_id = helpers.add_check(lab, plan.id, helpers.design())
    lab.run_test(plan.id, item_id)
    lab.wait_until_idle(plan.id, 240)
    result = helpers.result_for(lab, plan.id, item_id)
    assert result["label"] == "Couldn't trust this run" and result["control"]["outcome"] == "not_as_expected"
    assert result["advisories"]["items"][0]["id"] == "CVE-2022-21449"   # where the check came from still shows


def _reviewed(spec: dict, raw: dict, proposed_by: str = designs.PROPOSED_BY) -> dict:
    spec_hash = sha256_hex(spec)
    run = {"schema": "isogeny.run/1", "spec_hash": spec_hash, "phase": "first", "component": {"name": "acme-sign", "version": "1.4.2"},
           "baseline_version": None, "mode": "demo", "started_at": "t", "finished_at": "t", "duration_ms": 1, "raw": raw,
           "logs": "", "runner": "isogeny.runner/1"}
    return RuleReviewer().review({"spec": spec, "spec_hash": spec_hash, "proposed_by": proposed_by, "run": run})


def _raw(spec: dict, wrong: tuple = (), control_rejects: tuple = (), drop: tuple = ()) -> dict:
    """A raw outcome made by hand: the program right on every case except `wrong`, the control accepting everything
    except `control_rejects`, the reference library right on every case."""
    cases = [c for c in vectors.load_wycheproof("ecdsa_p256").cases if c.id in set(spec["inputs"]["cases"])]
    right = {c.id: "accept" if c.expected == "valid" else "reject" for c in cases}
    subject = {i: (("reject" if a == "accept" else "accept") if i in wrong else a) for i, a in right.items() if i not in drop}
    control = {c.id: "reject" if c.id in control_rejects else "accept" for c in cases}
    pin = spec["inputs"]["files"][0]
    return {"subject": {"key": "acme-sign-1.4.2", "answers": subject, "no_answer": {}},
            "control": {"key": "control-accept-all", "answers": control, "no_answer": {}},
            "reference": {"library": "cryptography", "ecdsa_p256": {"answers": dict(right)}},
            "files": {pin["file"]: pin["sha256"]}, "batch": {"command": "x", "duration_ms": 1, "mode": "demo", "started_at": "t", "stderr_tail": ""}}


def test_the_review_rule_case_by_case(lab):
    spec = helpers.spec_for(lab, demo_plan(lab).id, helpers.design(flags=("MissingZero", "ValidSignature")))
    total = len(spec["inputs"]["cases"])
    out = _reviewed(spec, _raw(spec))
    assert out["verdict"]["code"] == "passed" and out["control"]["outcome"] == "as_expected"
    assert out["detail"]["total"] == total == out["detail"]["right"] and out["detail"]["invalid_total"] == 1
    out = _reviewed(spec, _raw(spec, wrong=("6",)))
    assert out["verdict"]["code"] == "failed" and [w["id"] for w in out["detail"]["wrong"]] == ["6"]
    genuine = next(i for i in spec["inputs"]["cases"] if i != "6")
    assert _reviewed(spec, _raw(spec, wrong=(genuine,)))["verdict"]["code"] == "failed"          # rejecting a genuine one fails too
    out = _reviewed(spec, _raw(spec, control_rejects=("6",)))                                   # the control did not fail
    assert out["verdict"]["code"] == "couldnt_trust" and out["control"]["outcome"] == "not_as_expected"
    out = _reviewed(spec, _raw(spec, drop=("6",)))                                              # the program did not answer one case
    assert (out["verdict"]["code"], out["verdict"]["reason_code"]) == ("couldnt_run", "component_no_answer")
    raw = _raw(spec)
    raw["reference"]["ecdsa_p256"]["answers"]["6"] = "accept"                                   # the reference library got one wrong
    assert _reviewed(spec, raw)["verdict"]["code"] == "couldnt_trust"
    raw = _raw(spec)
    raw["files"] = {spec["inputs"]["files"][0]["file"]: "0" * 64}                               # not the pinned file
    assert _reviewed(spec, raw)["verdict"]["reason_code"] == "vector_file_changed"
    with pytest.raises(ReviewNotAllowed):                                                       # the reviewer never reviews its own
        _reviewed(spec, _raw(spec), proposed_by=RuleReviewer.engine_id)


def test_a_locked_test_that_names_cases_outside_the_file_gives_no_result(lab):
    spec = helpers.spec_for(lab, demo_plan(lab).id, helpers.design())
    for cases in (["168", "99999"], ["168", "168"], [], "168"):
        broken = {**spec, "inputs": {**spec["inputs"], "cases": cases}}
        raw = _raw(spec)
        out = _reviewed(broken, raw)
        assert out["verdict"]["code"] == "couldnt_trust", cases


def test_the_runner_refuses_cases_outside_the_pinned_file(lab):
    plan = demo_plan(lab)
    spec = helpers.spec_for(lab, plan.id, helpers.design())
    broken = {**spec, "inputs": {**spec["inputs"], "cases": ["168", "99999"]}}
    with lab._plan_lock, lab.db() as db:
        from app.db import PlanItemRow
        item = PlanItemRow(plan_id=plan.id, spec_hash=lab._lock_spec(db, broken, proposed_by=designs.PROPOSED_BY), position=99,
                           origin="added", removed=False)
        db.add(item)
        db.commit()
        item_id = item.id
    lab.run_test(plan.id, item_id)
    lab.wait_until_idle(plan.id, 240)
    result = helpers.result_for(lab, plan.id, item_id)
    assert result["label"].startswith("Couldn't run") and result["code"] == "couldnt_run"


def test_a_link_from_a_pack_is_sent_only_for_a_known_publisher():
    from app.present import advisory
    assert advisory.safe_href("https://openjdk.org/groups/vulnerability/advisories/2022-04-19")
    for bad in ("http://openjdk.org/x", "https://evil.example/x", "javascript:alert(1)", "https://user@github.com/x",
                "https://github.com:8443/x", "https://github.com.evil.example/x", None, 7, "https://" + "a" * 400):
        assert advisory.safe_href(bad) == ""
