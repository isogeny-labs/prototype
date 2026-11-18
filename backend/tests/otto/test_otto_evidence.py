"""Phase 5c, step 7: Otto's part of the signed evidence file, and the verify command's checks of it: the pack
signature, each advisory check's design in its pack, the ledger's chain, every bound run, --previous, and what the
command says when Otto is not installed where it runs."""
import copy
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest

import otto_fuzz
import otto_helpers as helpers
from app.canonical import canonical_bytes
from app.evidence.export import PUBLIC_KEY_FILE
from app.otto import harness
from conftest import demo_plan, play_back_speed
from evidence import otto as evidence_otto

pytestmark: list = []   # marks are on the tests that need the harness
BACKEND = Path(__file__).resolve().parents[2]


def _download(lab, plan_id: int) -> tuple[bytes, dict]:
    made = lab.export_evidence(plan_id)
    _, raw, _ = lab.evidence_file(made["id"], "json")
    return raw, json.loads(raw)["evidence"]


def _cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "evidence", *args], cwd=BACKEND, capture_output=True, text=True, timeout=120)


def _ran(tmp_path, patch):
    """A demo-mode Lab with the migration status measured, a pack installed, its check added and run once (it fails on
    acme-sign 1.4.2). With a status measured the failed check also brings a plan change that nobody has decided: a
    change to a system's plan is proposed only once the system has a place on it."""
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, patch, {"2026.11.1.json": first}, [public])
    lab.pack_key = public
    lab.plan = demo_plan(lab)
    lab.measure_migration(lab.plan.id)              # Measure status, as a person presses it
    lab.wait_until_measured(lab.plan.id, 300)
    lab.check_pack_updates()
    lab.install_pack("2026.11.1")
    helpers.accept_checks(lab, lab.plan.id)
    lab.check_item = next(t for t in lab.plan_view(lab.plan.id)["tests"] if t["kind"] == "advisory_cases")["id"]
    lab.run_test(lab.plan.id, lab.check_item)
    lab.wait_until_idle(lab.plan.id, 240)
    return lab


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    """Built once for this file. The tests that use it only download evidence and read it; a test that runs anything
    more builds its own (ran_alone)."""
    patch = pytest.MonkeyPatch()
    lab = _ran(tmp_path_factory.mktemp("ran"), patch)
    yield lab
    lab.stop()
    patch.undo()


@pytest.fixture(scope="module")
def ran_download(ran):
    """One evidence download of `ran`, as text: each test that only changes a copy of the file reads it from here
    (a download a case costs a third of a second, and there are some 25 cases)."""
    raw, _ = _download(ran, ran.plan.id)
    return raw


@pytest.fixture
def ran_alone(tmp_path, monkeypatch):
    lab = _ran(tmp_path, monkeypatch)
    yield lab
    lab.stop()


def test_an_assessment_with_nothing_of_ottos_has_no_otto_part(lab):
    plan = demo_plan(lab)
    lab.run_test(plan.id, plan.item["bad_signatures"])
    lab.wait_until_idle(plan.id, 240)
    _, evidence = _download(lab, plan.id)
    assert "otto" not in evidence
    assert evidence["app"]["note"] == "Both engines are rule-based code from the same build. No AI model is connected."


@pytest.mark.needs_otto
def test_the_otto_part_is_inside_what_is_signed(ran):
    raw, evidence = _download(ran, ran.plan.id)
    otto = evidence["otto"]
    assert otto["schema"] == "isogeny.otto-evidence/1" and otto["harness"]["commit"] == harness.read_lock().commit
    assert [p["pack"]["version"] for p in otto["packs"]] == ["2026.11.1"] and set(otto["packs"][0]) == {"pack", "fingerprint", "public_key", "signature"}
    check = otto["checks"][0]
    assert check["title"] == "Advisory check: Blank signature accepted (CVE-2022-21449)" and check["item_id"] == ran.check_item
    assert check["spec"]["kind"] == "advisory_cases" and check["pack_fingerprint"] == otto["packs"][0]["fingerprint"]
    # the lock entry, the three entries of the person's accept (the proposal named, the decision, its check), the run and its check
    assert otto["ledger"]["height"] == 6 == len(otto["ledger"]["lines"]) and otto["ledger"]["head"].startswith("sha256:")
    # Otto proposes, a person decides: every proposal as it stands, and the decision on it with who and when
    accepted = next(p for p in otto["proposals"] if p["kind"] == "check")
    assert accepted["label"] == "From Otto" and accepted["state"] == "accepted" and accepted["status"] == "Added" and accepted["why"]
    decision, = accepted["decisions"]
    assert (decision["decision"], decision["by"], decision["before"], decision["after"], decision["number"]) == ("accept", "You", "proposed", "accepted", 1)
    assert decision["at"].endswith("Z") and decision["ledger_entry"].startswith("sha256:") and decision["reason"] is None
    assert decision["proposal"]["id"] == accepted["id"] and decision["proposal_sha256"] == accepted["fingerprint"]
    assert "one login" in otto["decisions_note"] and "A decision is not a result" in otto["decisions_note"]
    # a proposal nobody has decided is in the file too, as that
    waiting = [p for p in otto["proposals"] if p["state"] == "proposed"]
    assert waiting and all(p["decisions"] == [] and p["status"] == "Proposed" for p in waiting)
    run = otto["runs"][0]
    assert run["phase"] == "first" and run["record"]["spec_hash"] == check["spec_hash"] and run["lock_entry"] == check["lock_entry"]
    assert "Advisory checks come from signed test packs made by Otto" in evidence["app"]["note"]
    # the same check is among the file's tests like any other, with its advisory box
    test = next(t for t in evidence["tests"] if t["item_id"] == ran.check_item)
    assert test["proposed_by"] == "isogeny.otto-pack/1" and test["runs"][0]["result"]["advisories"]["items"][0]["id"] == "CVE-2022-21449"
    # the ledger itself never says how a run came out (the run failed; the ledger holds only fingerprints and names)
    text = json.dumps(otto["ledger"]["lines"])
    assert run["review"]["verdict"]["code"] == "failed" and "ailed" not in text and "assed" not in text
    # the report lists it, and words no result there
    _, report, _ = ran.evidence_file(ran.export_evidence(ran.plan.id)["id"], "html")
    page = report.decode()
    assert "8. Otto: test packs, the ledger and Claude" in page and "Advisory checks added from a test pack" in page
    assert "proposals, and the decisions on them" in page and "Accepted by You" in page and "Nobody has decided this yet." in page
    assert "<script" not in page.lower()


@pytest.mark.needs_otto
def test_the_command_checks_the_file_the_pack_and_the_ledger_together(ran, tmp_path):
    raw, _ = _download(ran, ran.plan.id)
    path = tmp_path / "evidence.json"
    path.write_bytes(raw)
    data_dir = str(ran.settings.data_dir)
    ok = _cli("verify", str(path), "--data-dir", data_dir, "--pack-key", ran.pack_key)
    assert ok.returncode == 0 and ok.stdout.startswith("Evidence verified\n"), ok.stdout + ok.stderr
    for words in ("Otto: Test packs: 1 in the file, each whole and with a signature that holds from a pack key you trust.",
                  "Otto: Advisory checks: 1, each with its design in its pack and its lock entry in the ledger.",
                  "Otto: Ledger: 6 entries in one unbroken chain; 1 runs, each bound to a test locked before it.",
                  "Otto: Decisions: 1 on 1 of Otto's 2 proposals, each in the ledger with who and when, in an order the app allows.",
                  "Otto's own audit"):
        assert words in ok.stdout, ok.stdout
    # a pack signed by a key this computer does not trust: consistent, but not confirmed, and that is not a pass
    unknown = _cli("verify", str(path), "--data-dir", data_dir)
    assert unknown.returncode == 2 and "Evidence verified" not in unknown.stdout and "This is not a pass." in unknown.stdout
    assert "could not be confirmed: its key is not one you trust" in unknown.stdout
    # one byte changed anywhere fails
    changed = bytearray(raw)
    changed[raw.index(b'"otto"') + 40] ^= 0x01
    (tmp_path / "changed.json").write_bytes(bytes(changed))
    failed = _cli("verify", str(tmp_path / "changed.json"), "--data-dir", data_dir, "--pack-key", ran.pack_key)
    assert failed.returncode == 1 and failed.stdout.startswith("Evidence NOT verified: ")
    assert _cli("verify", str(path), "--data-dir", data_dir, "--pack-key", "zz").returncode == 1


def _resigned(lab, evidence: dict) -> bytes:
    """The file as someone holding the app's own signing key could write it after changing the Otto part: the outer
    signature is valid again, so only the checks of the Otto part itself can catch the change."""
    from app.evidence.export import sign_envelope
    return sign_envelope(evidence, lab.settings.data_dir)


@pytest.mark.needs_otto
@pytest.mark.parametrize("name", ["a ledger line changed", "a ledger line removed", "the last ledger lines cut off", "the pack swapped",
                                  "the pack edited", "a run record changed", "a review changed", "the design swapped", "a lock entry for another test",
                                  "a run listed that the ledger does not bind",
                                  "a decision under another name", "a decision at another time", "a decision with a reason added",
                                  "a decision taken out", "a decision made up", "an accept turned into a reject",
                                  "a proposal that stands elsewhere", "the proposal a decision was made on changed",
                                  "the list of proposals taken out", "a proposal reworded",
                                  "an undecided proposal passed off as added before decisions were recorded",
                                  "a second proposal for a check that a recorded accept put in the plan",
                                  "the word for where a proposal stands changed", "a proposal marked as withdrawn and reworded"])
def test_a_change_inside_the_otto_part_is_caught_even_when_the_file_is_signed_again(ran, ran_download, tmp_path, name):
    evidence = json.loads(ran_download)["evidence"]            # this case's own copy
    otto = evidence["otto"]
    lines = otto["ledger"]["lines"]
    decided = next(p for p in otto["proposals"] if p["decisions"])
    if name == "a ledger line changed":
        place = next(n for n, line in enumerate(lines) if '"phase":"first"' in line)
        lines[place] = lines[place].replace('"phase":"first"', '"phase":"retest"')
    elif name == "a decision under another name":
        decided["decisions"][0]["by"] = "Someone else"
    elif name == "a decision at another time":
        decided["decisions"][0]["at"] = "2020-01-01T00:00:00Z"
    elif name == "a decision with a reason added":
        decided["decisions"][0]["reason"] = "It was never wanted"
    elif name == "a decision taken out":
        decided["decisions"], decided["state"], decided["status"] = [], "proposed", "Proposed"
    elif name == "a decision made up":
        waiting = next(p for p in otto["proposals"] if not p["decisions"])
        made_up = {**copy.deepcopy(decided["decisions"][0]), "decision": "reject", "after": "rejected", "reason": "Not wanted",
                   "proposal": {k: waiting[k] for k in ("id", "kind", "title", "why", "lines", "about")}, "proposal_sha256": waiting["fingerprint"]}
        waiting["decisions"], waiting["state"], waiting["status"] = [made_up], "rejected", "Not added (Not wanted)"
    elif name == "an accept turned into a reject":
        decided["decisions"][0].update(decision="reject", after="rejected")
        decided["state"] = "rejected"
    elif name == "a proposal that stands elsewhere":
        decided["state"], decided["status"] = "rejected", "Not added (no reason given)"
    elif name == "the proposal a decision was made on changed":
        decided["decisions"][0]["proposal"]["title"] = "Something else was proposed"
    elif name == "the list of proposals taken out":
        del otto["proposals"]
    elif name == "a proposal reworded":
        decided["why"] = "Because it is required by law."
    elif name == "an undecided proposal passed off as added before decisions were recorded":
        waiting = next(p for p in otto["proposals"] if not p["decisions"])
        waiting["legacy"], waiting["state"], waiting["status"] = True, "accepted", "Accepted"
    elif name == "a second proposal for a check that a recorded accept put in the plan":
        twin = {**copy.deepcopy(decided), "id": decided["id"][:-1] + ("0" if decided["id"][-1] != "0" else "1"), "decisions": [],
                "legacy": True, "state": "accepted", "status": "Added", "ledger_entry": None}
        twin["fingerprint"] = evidence_otto._sha({k: twin[k] for k in ("id", "kind", "title", "why", "lines", "about")})
        otto["proposals"].append(twin)
    elif name == "the word for where a proposal stands changed":
        decided["status"] = "Not added (no reason given)"
    elif name == "a proposal marked as withdrawn and reworded":
        decided["current"], decided["title"] = False, "Something else was proposed"
    elif name == "a ledger line removed":
        del lines[1]
        otto["ledger"]["height"] -= 1
    elif name == "the last ledger lines cut off":
        del lines[1:]
        otto["ledger"]["height"] = 1
        otto["ledger"]["head"] = json.loads(lines[0])["hash"]
    elif name == "the pack swapped":
        other, _ = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory("CVE-2024-42460", "Missing leading zero accepted", flags=("MissingZero",))])
        otto["packs"] = [json.loads(other)]
    elif name == "the pack edited":
        otto["packs"][0]["pack"]["advisories"][0]["reading"]["plain_name"] = "Something else"
    elif name == "a run record changed":
        otto["runs"][0]["record"]["raw"]["subject"]["answers"]["168"] = "reject"
    elif name == "a review changed":
        otto["runs"][0]["review"]["verdict"]["code"] = "passed"
    elif name == "the design swapped":
        otto["packs"][0]["pack"]["tests"][0]["design"]["cases"]["ids"] = ["168"]
    elif name == "a lock entry for another test":
        otto["checks"][0]["spec"]["inputs"]["cases"] = ["168"]
    else:
        otto["runs"].append({**copy.deepcopy(otto["runs"][0]), "ledger_entry": "sha256:" + "0" * 64})
    outcome = evidence_otto.check_otto(evidence, {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and outcome.problem, name
    path = tmp_path / "resigned.json"
    path.write_bytes(_resigned(ran, evidence))
    done = _cli("verify", str(path), "--data-dir", str(ran.settings.data_dir), "--pack-key", ran.pack_key)
    assert done.returncode == 1 and done.stdout.startswith("Evidence NOT verified: the Otto part: "), done.stdout


@pytest.mark.needs_otto
def test_damaged_lists_of_proposals_are_refused_or_read_and_never_take_long(ran, monkeypatch):
    """Seeded fuzz of the reader the verify command gained on 18 November 2026: the list of Otto's proposals in an
    evidence file, with the decisions on them. A damaged copy is refused with one plain sentence, or read (when the
    damage left everything the ledger and the fingerprints bind as it was). It never raises and never takes long.
    (Otto's own audit, the last step, is checked elsewhere and is stood in for here: this test is about the reader.)"""
    from app.otto import assurance
    _, evidence = _download(ran, ran.plan.id)
    whole = evidence_otto.check_otto(copy.deepcopy(evidence), {ran.pack_key})
    assert whole.code == evidence_otto.OK and any(line.startswith("Decisions: ") for line in whole.lines)
    monkeypatch.setattr(assurance, "verify_lines", lambda lines, folder: [])
    rng = random.Random(20261118)
    refused = read = 0
    started = time.monotonic()
    for _ in range(400):
        damaged = copy.deepcopy(evidence)
        proposals = damaged["otto"]["proposals"]
        for _ in range(rng.randint(1, 3)):
            proposals = otto_fuzz.damage_json(rng, proposals)
        damaged["otto"]["proposals"] = proposals
        outcome = evidence_otto.check_otto(damaged, {ran.pack_key})
        if outcome.code == evidence_otto.OK:
            read += 1
            continue
        refused += 1
        assert outcome.code == evidence_otto.FAILED and outcome.problem and outcome.problem.isprintable() and len(outcome.problem) <= 900
    assert refused > read and refused + read == 400       # most damage is caught; what is not left the bound parts as they were
    assert time.monotonic() - started < 60


@pytest.mark.needs_otto
@pytest.mark.slow
def test_previous_shows_that_nothing_was_dropped_between_two_downloads(ran_alone, tmp_path):
    ran = ran_alone
    older_raw, older = _download(ran, ran.plan.id)
    play_back_speed(ran)
    ran.run_all(ran.plan.id)
    ran.wait_until_idle(ran.plan.id, 300)
    ran.start_retest(ran.plan.id, "1.4.3")
    ran.wait_until_idle(ran.plan.id, 300)
    newer_raw, newer = _download(ran, ran.plan.id)
    assert newer["otto"]["ledger"]["height"] > older["otto"]["ledger"]["height"]
    old_path, new_path = tmp_path / "older.json", tmp_path / "newer.json"
    old_path.write_bytes(older_raw)
    new_path.write_bytes(newer_raw)
    data_dir = str(ran.settings.data_dir)
    ok = _cli("verify", str(new_path), "--previous", str(old_path), "--data-dir", data_dir, "--pack-key", ran.pack_key)
    assert ok.returncode == 0 and "Compared with the older file: its 6 ledger entries are still here, unchanged" in ok.stdout, ok.stdout
    # the other way round: the "newer" file is the shorter one, so entries are missing
    back = _cli("verify", str(old_path), "--previous", str(new_path), "--data-dir", data_dir, "--pack-key", ran.pack_key)
    assert back.returncode == 1 and "history was cut or rewritten" in back.stdout
    # a ledger rewritten from the start (a valid chain of its own, signed again) is caught by --previous
    rewritten = copy.deepcopy(newer)
    rewritten["otto"] = copy.deepcopy(older["otto"])
    assert evidence_otto.check_otto(rewritten, {ran.pack_key}, newer).code == evidence_otto.FAILED
    assert evidence_otto.check_otto(newer, {ran.pack_key}, older).code == evidence_otto.OK
    # an older file with no Otto part can't be compared
    assert evidence_otto.check_otto(newer, {ran.pack_key}, {"schema": "isogeny.evidence/1"}).code == evidence_otto.FAILED


@pytest.mark.needs_otto
def test_without_otto_the_command_says_the_audit_was_not_run_and_that_is_not_a_pass(ran, monkeypatch):
    _, evidence = _download(ran, ran.plan.id)
    missing = harness.OttoStatus(False, harness.NOT_FETCHED, "isogeny-labs/otto", "a" * 40, "0.1.0", None)
    monkeypatch.setattr(harness, "status", lambda *a, **k: missing)
    outcome = evidence_otto.check_otto(evidence, {ran.pack_key})
    assert outcome.code == evidence_otto.NOT_CONFIRMED and "Otto's own audit of the ledger was not run" in outcome.problem
    assert "Otto is not installed on this computer" in outcome.problem and len(outcome.lines) == 4      # the other checks were still made
    assert any(line.startswith("Decisions: 1 on 1 of Otto's") for line in outcome.lines)


def test_the_checker_reads_the_same_signing_context_as_the_pack_builder():
    from app.otto import packs
    shipped = Path(packs.__file__).with_name("trusted-pack-keys.json")       # the key list the app ships (a test may have swapped the app's)
    assert evidence_otto.PACK_CONTEXT == packs.SIGNING_CONTEXT and evidence_otto.SHIPPED_KEYS_FILE == shipped and shipped.is_file()
    assert evidence_otto.LOCAL_KEY_FILE == packs.LOCAL_KEY_FILE and PUBLIC_KEY_FILE
    assert canonical_bytes({"b": 1, "a": "é"}) == '{"a":"é","b":1}'.encode()
