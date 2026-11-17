"""What this repository ships for Otto: the two signed test packs (research/packs), the recorded Claude answers they
were built from (research/recorded) and the research ledger (research/lab). These tests pin how those fit together.

They decide no result and repeat none as an answer key: what each test and each fix did on public copies is in the
packs themselves, judged by Otto's harness, and the answer key for them is written separately."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import OTTO_PACKS_DIR, OTTO_RECORDED_DIR
from app.otto import fixes, harness, model, packs
from app.otto.engine import NOT_REGISTERED, OttoEngine
from app.run import components
from conftest import demo_plan, make_lab
from ottolab import build, prompts, snapshot

BACKEND = Path(__file__).resolve().parents[2]
RECORDED_HOW = "Recorded during the build, not through the API"
BANNED = ("score", "severity", "critical", "time to hack", "time-to-hack")


def _shipped() -> list[packs.Pack]:
    found, refused = packs.found_in(OTTO_PACKS_DIR, packs.trusted_keys(None))
    assert refused == []
    return found


def _recorded() -> dict[str, dict]:
    """{file name: the recorded answer}, every file in the folder."""
    out = {}
    for path in sorted(OTTO_RECORDED_DIR.iterdir()):
        answer = model.read_recorded(path)
        assert answer is not None, f"{path.name} is not a whole recorded answer"
        assert path == model.recorded_path(OTTO_RECORDED_DIR, answer["step"], answer["prompt_sha256"])
        out[path.name] = answer
    return out


# The publisher's own words (a page title such as "Oracle Critical Patch Update Advisory", a quoted line) are data, shown
# as quotes. The wording rules are about what this app says itself.
THEIR_WORDS = ("sources", "quote", "weakness_quote", "publisher", "steps", "ledger")


def _our_words(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for k, v in value.items() if k not in THEIR_WORDS for t in _our_words(v)]
    if isinstance(value, list):
        return [t for v in value for t in _our_words(v)]
    return []


def test_the_shipped_packs_read_with_the_shipped_key_and_follow_each_other():
    found = _shipped()
    assert [p.version for p in found] == [version for version, _ in build.SHIP_PLAN] == ["2026.11.1", "2026.11.2"]
    assert packs.follows(found[0], None) is None and packs.follows(found[1], found[0]) is None
    assert "Packs install in order" in packs.follows(found[1], None)
    lock = harness.read_lock()
    for pack, (_, ids) in zip(found, build.SHIP_PLAN, strict=True):
        assert [a["id"] for a in pack.pack["advisories"]] == list(ids)
        assert not pack.made_here and pack.signer == build.SHIP_SIGNER == pack.pack["signer"]
        assert pack.pack["otto"]["commit"] == lock.commit and pack.pack["otto"]["repository"] == lock.repository
        assert pack.pack["research"]["answers"] == "recorded" and "recorded during the build" in pack.pack["research"]["answers_note"]
    # the folder holds nothing else, and the app's default updates folder is this one
    assert sorted(p.name for p in OTTO_PACKS_DIR.iterdir()) == ["2026.11.1.json", "2026.11.2.json"]


def test_a_shipped_test_or_fix_is_only_what_its_trial_on_public_copies_supports():
    """The rule of a pack, read off the shipped ones: a test is "ready" only with a trial that held and was replayed by
    a second author; a fix is "proven" only if, on the fixed version, no pass-or-fail test was left failing."""
    states = {}
    for pack in _shipped():
        for advisory in pack.pack["advisories"]:
            test, fix = advisory["test"], advisory["fix"]
            states[advisory["id"]] = (test["state"], fix["state"])
            assert test["reason"] and fix["reason"]
            if test["state"] == "ready":
                arms = test["trial"]["arms"]
                assert test["trial"]["outcome"] == "supported" and test["trial"]["replayed"] is True
                assert arms["affected"]["wrong"] > 0 == arms["fixed"]["wrong"] and arms["accept-all"]["right"] < arms["accept-all"]["total"]
                assert pack.design(test["design_sha256"]) is not None
            else:
                assert fix["state"] == "none"          # no test, no fix to prove
            if fix["state"] == "proven":
                trial = fix["trial"]
                assert trial["outcome"] == "supported" and trial["replayed"] is True
                assert trial["arms"]["fixed"]["failing"] == 0 < trial["arms"]["affected"]["failing"]
            elif fix["state"] == "not_proven":
                assert fix["trial"]["outcome"] != "supported" or fix["trial"]["arms"]["fixed"]["failing"] > 0
            assert not any(word in text.lower() for text in _our_words(advisory) for word in BANNED + ("secure",)), advisory["id"]
    assert set(states) == {aid for _, ids in build.SHIP_PLAN for aid in ids} and len(states) == 6
    # no check is shipped twice under two names: every ready test selects cases of its own
    selections = [tuple(sorted(t["design"]["cases"]["ids"])) for pack in _shipped() for t in pack.pack["tests"]]
    assert len(selections) == len(set(selections)) == 3
    twin = next(a for pack in _shipped() for a in pack.pack["advisories"] if a["id"] == "CVE-2019-14853")
    assert twin["test"]["state"] == "none" and "the same check under a second name" in twin["test"]["reason"]
    # each source says both where a person would look and the address the quoted text was read from on that day
    for pack in _shipped():
        for advisory in pack.pack["advisories"]:
            assert all(s["url"].startswith("https://") and s["read_from"].startswith("https://") and s["fetched"] for s in advisory["sources"])


def test_every_recorded_answer_was_asked_by_the_build_or_by_the_app_and_says_how_it_was_made():
    recorded = _recorded()
    assert recorded and all(a["recorded"]["how"] == RECORDED_HOW for a in recorded.values())
    asked = {}                                              # prompt fingerprint -> the step of a shipped pack that used it
    for pack in _shipped():
        for advisory in pack.pack["advisories"]:
            for step in advisory["steps"]:
                assert step["source"] == "recorded" and step["model"] is None and step["cost_nano_usd"] == 0 and step["how"] == RECORDED_HOW
                asked[step["prompt_sha256"]] = step
    by_prompt = {a["prompt_sha256"]: a for a in recorded.values()}
    # every step of a pack has its recorded answer here, word for word ...
    for digest, step in asked.items():
        assert by_prompt[digest]["step"] == step["step"] and by_prompt[digest]["answer_sha256"] == step["answer_sha256"]
    # ... and nothing else is here but the one answer the app itself uses: Otto's change for the demo program
    others = [a for digest, a in by_prompt.items() if digest not in asked]
    assert [a["step"] for a in others] == ["write_fix"]


def test_the_recorded_answers_still_fit_the_prompts_the_research_asks():
    """A prompt is the key of its recorded answer. If the words of a prompt change, the research can no longer be
    repeated from the recorded answers: new answers must be recorded and the packs built again."""
    by_prompt = {a["prompt_sha256"]: a for a in _recorded().values()}
    snap = snapshot.read_snapshot(build.SNAPSHOT)
    ready = {a["id"]: a["test"]["state"] == "ready" for pack in _shipped() for a in pack.pack["advisories"]}
    assert [a["id"] for a in snap["advisories"]] and set(ready) == {a["id"] for a in snap["advisories"]}
    for advisory in snap["advisories"]:
        read = by_prompt[model.sha256_text(prompts.read_advisory_prompt(advisory))]
        reading = prompts.check_reading(read["answer"], advisory)
        assert model.sha256_text(prompts.design_test_prompt(advisory, reading)) in by_prompt, advisory["id"]
        # a fix is asked for only once a test held on public copies
        assert (model.sha256_text(prompts.propose_fix_prompt(advisory, reading)) in by_prompt) == ready[advisory["id"]], advisory["id"]


def test_the_newest_pack_was_built_with_the_research_scripts_as_they_are_now():
    """A pack names the scripts it was built with, by fingerprint. If one of them is changed, build the next pack with
    it (the shipped packs stay as they are) and point this test at that pack."""
    newest = _shipped()[-1].pack["otto"]
    here = {"check_model_step.py": "ottolab/pinned/check_model_step.py", "trial.py": "ottolab/pinned/trial.py",
            "ottolab/agent.py": "ottolab/agent.py", "ottolab/prompts.py": "ottolab/prompts.py", "ottolab/research.py": "ottolab/research.py"}
    assert set(newest["scripts"]) == set(here)
    for name, path in here.items():
        assert hashlib.sha256((BACKEND / path).read_bytes()).hexdigest() == newest["scripts"][name], f"{path} changed after the packs were built"
    # the two pinned scripts are in the research ledger's folder as they were registered
    for name in ("trial.py", "check_model_step.py"):
        assert (build.LAB / name).read_bytes() == (BACKEND / "ottolab" / "pinned" / name).read_bytes()
    # and the research ledger ends where the newest pack says it did
    lines = (build.LAB / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == newest["ledger"]["height"] and json.loads(lines[-1])["hash"] == newest["ledger"]["head"]


def test_the_recorded_change_for_acme_sign_gives_no_registered_program_so_the_app_does_not_offer_it():
    """What the build found, kept honest. The one recorded answer for Otto's own-code fix is a clean change that
    names all three failed tests, but the program it gives differs from our own acme-sign 1.4.3 (the same check,
    written another way). Only our registered demo programs may run, so the app can't prove this change and does
    not offer it: the fix template takes its place and the page says why. If a new answer is ever recorded, this
    test changes with it; an answer is never re-asked to get a different one."""
    answer = next(a for a in _recorded().values() if a["step"] == "write_fix")
    source = components.lookup("acme-sign", "1.4.2").read_text(encoding="utf-8")
    assert 'Program: acme-sign 1.4.2' in answer["prompt"] and source in answer["prompt"]
    change = fixes.check_change(answer["answer"], {"acme_sign.py": source}, 3)
    assert change["answers"] == [0, 1, 2] and 'VERSION = "1.4.3"' in change["files"]["acme_sign.py"]
    built = {"acme_sign.py": change["files"]["acme_sign.py"].encode("utf-8")}
    assert components.registered_version("acme-sign", built) is None
    with pytest.raises(fixes.Refused) as refused:
        OttoEngine._usable(answer["answer"], {"name": "acme-sign", "version": "1.4.2"}, {"acme_sign.py": source}, 3)
    assert str(refused.value) == NOT_REGISTERED


@pytest.mark.needs_otto
def test_the_shipped_packs_install_and_their_tests_fit_the_demo(tmp_path):
    """With nothing set, the app's updates folder is the shipped one: both packs install in order and every ready
    test fits the Acme Pay demo's signing program. Nothing runs."""
    lab = make_lab(tmp_path)
    try:
        plan = demo_plan(lab)
        assert lab.check_pack_updates()["packs"]["update"]["version"] == "2026.11.1"
        lab.install_pack("2026.11.1")
        done = lab.install_pack("2026.11.2")
        assert [p["version"] for p in done["packs"]["installed"]] == ["2026.11.1", "2026.11.2"] and done["packs"]["update"] is None
        assert "recorded during the build" in done["answers"]["line"] and done["answers"]["live"] is False
        view = lab.advisories_view(plan.id)
        assert [r["id"] for r in view["rows"]] == [aid for _, ids in build.SHIP_PLAN for aid in ids]
        ready = [r for r in view["rows"] if r["test"]["key"] == "ready"]
        assert len(ready) == view["add"]["count"] == 3 and all(r["fits"] == ["acme-sign 1.4.2"] for r in ready)
        assert all(r["test"]["label"] and r["test"]["reason"] and r["result"]["label"] for r in view["rows"])
        assert all(r["panel"]["publisher"]["text"] and r["panel"]["publisher"]["href"].startswith("https://") for r in view["rows"])
        text = " ".join(_our_words(view)).lower()
        assert not any(word in text for word in BANNED)
        assert text.count("secure") == 1 and "doesn't prove a system secure" in view["standing_line"]     # the standing line, nowhere else
        before = len(lab.plan_view(plan.id)["tests"])
        added = lab.add_new_checks(plan.id)
        tests = lab.plan_view(plan.id)["tests"]
        assert len(tests) == before + 3 and added["add"]["count"] == 0 and not lab.jobs.busy(plan.id)
        assert all(t["status"] != "done" for t in tests if t["kind"] == "advisory_cases")          # added, not run
        # each new card says which advisory it came from, with the way to it; no other card does
        for card in tests:
            came_from = card["title"].rsplit("(", 1)[-1].rstrip(")") if card["kind"] == "advisory_cases" else None
            assert card.get("advisory") == ({"label": f"From advisory {came_from}", "link": {"page": "advisories", "item": came_from}}
                                            if came_from else None)
            assert ("advisory" in card) == (came_from is not None)          # every other card is exactly as it was
    finally:
        lab.stop()


@pytest.mark.needs_otto
def test_the_evidence_report_links_a_shipped_advisory_to_its_publisher_and_the_file_verifies(tmp_path):
    """A shipped advisory names its source at a known publisher (here: the fixed JDK source). The readable report
    draws that link, and only such a link: the address in a pack is checked again where the report is made."""
    lab = make_lab(tmp_path)
    try:
        plan = demo_plan(lab)
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        lab.add_new_checks(plan.id)
        item = next(t["id"] for t in lab.plan_view(plan.id)["tests"] if "CVE-2022-21449" in t["title"])
        lab.run_test(plan.id, item)
        lab.wait_until_idle(plan.id, 240)
        result = next(r for r in lab.lab_view(plan.id)["rows"] if r["item_id"] == item)["result"]
        source = result["advisories"]["items"][0]["href"]
        # the link is the address the quoted line was read from: the file at its pinned commit
        assert result["label"] == "Failed" and source.startswith("https://raw.githubusercontent.com/openjdk/jdk17u/")
        made = lab.export_evidence(plan.id)
        report = lab.evidence_file(made["id"], "html")[1].decode("utf-8")
        assert f'<a href="{source.replace("&", "&amp;")}" rel="noreferrer noopener">' in report
        raw = lab.evidence_file(made["id"], "json")[1]
        path = tmp_path / "evidence.json"
        path.write_bytes(raw)
        done = subprocess.run([sys.executable, "-m", "evidence", "verify", str(path), "--data-dir", str(lab.settings.data_dir)], cwd=BACKEND,
                              capture_output=True, text=True, timeout=300)
        assert done.returncode == 0 and done.stdout.startswith("Evidence verified"), done.stdout + done.stderr
    finally:
        lab.stop()


def test_the_report_never_draws_a_link_that_is_not_ours_or_a_known_publishers():
    from app.evidence import export
    drawn = export.el("a", export.t("the source"), href="https://github.com/openjdk/jdk17u", publisher=True)
    assert drawn == '<a href="https://github.com/openjdk/jdk17u" rel="noreferrer noopener">the source</a>'
    for href in ("https://example.com/x", "http://github.com/openjdk/jdk17u", "https://user@github.com/x", "https://github.com:8443/x",
                 "javascript:alert(1)", "", None):
        with pytest.raises(ValueError):
            export.el("a", export.t("a link"), href=href, publisher=True)
    with pytest.raises(ValueError):                    # a publisher's address is drawn only where an advisory's source is
        export.el("a", export.t("the source"), href="https://github.com/openjdk/jdk17u")


@pytest.mark.needs_otto
def test_the_research_ledger_passes_ottos_own_audit(tmp_path):
    """Otto's harness checks its own ledger: the chain, every decision derived again from its runs, every pinned
    checker run again. On a copy, so the shipped folder is never written to."""
    copy = tmp_path / "lab"
    shutil.copytree(build.LAB, copy)
    done = subprocess.run([sys.executable, "-m", "ottolab.build", "audit", "--lab", str(copy)], cwd=BACKEND, capture_output=True, text=True,
                          timeout=900)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "chain intact, every decision re-derived, every pinned checker run again" in done.stdout and "PROBLEM" not in done.stdout
