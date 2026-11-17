"""Phase 5c, step 4: the research side on Adam's harness, end to end in demo mode on a made-up snapshot about our
own demo program: read, design, try on "public copies" (acme-sign 1.4.2 and 1.4.3), propose the fix, try that,
replay under a second author, and sign a pack. A design that can't catch the affected version must come out refuted
and stay out of the pack."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import otto_research_fixtures as fixtures
from app.otto import harness, packs
from ottolab import build, research, snapshot

pytestmark: list = []   # marks are on the tests that need the harness


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One run of the whole loop (about a minute and a half), shared by the tests of this file."""
    import os
    folder = tmp_path_factory.mktemp("research")
    snapshot_path = fixtures.write(folder)
    old = {k: os.environ.get(k) for k in ("EVIDENCE_LAB_MODE", "ANTHROPIC_API_KEY")}
    os.environ["EVIDENCE_LAB_MODE"] = "demo"            # the made-up advisories are about our own demo program
    os.environ.pop("ANTHROPIC_API_KEY", None)
    lines = []
    real_say, build.say = build.say, lines.append
    try:
        lab = research.open_lab(folder / "lab")
        key = Ed25519PrivateKey.generate()
        ids = tuple(a["id"] for a in fixtures.SNAPSHOT["advisories"])
        pack = build.build_pack(lab, snapshot.read_snapshot(snapshot_path), snapshot_path, "2026.11.1", ids, None, key, "A key made for a test",
                                folder / "packs", folder / "recorded", live=False, limit_nano=2_000_000_000, spent_file=folder / "spent.json")
        yield {"folder": folder, "lab": lab, "pack": pack, "lines": lines, "key": build._public_hex(key)}
    finally:
        build.say = real_say
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _advisory(built, number: int) -> dict:
    return built["pack"].advisory(f"TEST-2026-000{number}")


@pytest.mark.needs_otto
@pytest.mark.slow
def test_a_design_that_catches_the_affected_version_ships_with_its_trial(built):
    entry = _advisory(built, 1)
    assert entry["test"]["state"] == "ready" and entry["test"]["reason"].startswith("Test ready")
    trial = entry["test"]["trial"]
    assert trial["outcome"] == "supported" and trial["replayed"] is True
    arms = trial["arms"]
    assert arms["affected"] == {"library": "acme-sign", "version": "1.4.2", "right": 62, "wrong": 2, "total": 64}
    assert arms["fixed"]["wrong"] == 0 and arms["reference"]["wrong"] == 0 and arms["accept-all"]["wrong"] == 64
    design = built["pack"].design(entry["test"]["design_sha256"])
    assert design["advisory"] == "TEST-2026-0001" and "168" in design["cases"]["ids"]
    assert [t["design_sha256"] for t in built["pack"].pack["tests"]] == [entry["test"]["design_sha256"]]   # the only test in the pack


@pytest.mark.needs_otto
@pytest.mark.slow
def test_a_useless_design_comes_out_refuted_and_stays_out_of_the_pack(built):
    entry = _advisory(built, 2)
    assert entry["test"]["state"] == "not_offered" and "failed its own trial" in entry["test"]["reason"]
    assert entry["test"]["trial"]["outcome"] == "refuted" and entry["test"]["trial"]["arms"]["affected"]["wrong"] == 0
    assert built["pack"].design(entry["test"]["design_sha256"]) is None
    assert entry["fix"]["state"] == "none" and "no test" in entry["fix"]["reason"]
    st = built["lab"].state()
    dead = [f for _, f in st.of("fact") if "advisory:TEST-2026-0002" in f["tags"]]
    assert len(dead) == 1 and dead[0]["kind"] == "dead_end" and "not-offered" in dead[0]["tags"]


@pytest.mark.needs_otto
@pytest.mark.slow
def test_no_test_and_a_refused_reading_are_said_plainly(built):
    none = _advisory(built, 3)
    assert none["test"]["state"] == "none" and none["test"]["reason"].startswith("No test yet: The weakness is in a part")
    assert none["test"]["trial"] is None and none["reading"]["plain_name"] == "Out-of-range signature accepted"
    refused = _advisory(built, 4)
    assert refused["reading"] is None and "not in the publisher's text" in refused["reading_refused"]
    assert refused["test"]["state"] == "none" and [s["outcome"] for s in refused["steps"]] == ["refused"]
    assert [s["step"] for s in refused["steps"]] == ["read_advisory"]     # nothing more was asked after a refused reading


@pytest.mark.needs_otto
@pytest.mark.slow
def test_the_fix_is_proven_only_by_its_own_trial(built):
    fix = _advisory(built, 1)["fix"]
    assert fix["state"] == "proven" and fix["kind"] == "update" and (fix["library"], fix["version"]) == ("acme-sign", "1.4.3")
    assert fix["quote"]["text"] == "The check was added in acme-sign 1.4.3."
    arms = fix["trial"]["arms"]
    # the Independent exam, Attacker tricks and the advisory check: all three fail on 1.4.2 and none on 1.4.3
    assert arms["affected"] == {"version": "1.4.2", "failing": 3, "tests": 3} == {**arms["affected-again"]}
    assert arms["fixed"] == {"version": "1.4.3", "failing": 0, "tests": 3}
    assert fix["trial"]["outcome"] == "supported" and fix["trial"]["replayed"] is True and "Speed was not part" in fix["reason"]


@pytest.mark.needs_otto
@pytest.mark.slow
def test_every_claude_step_is_in_the_ledger_whole_and_checked(built):
    st = built["lab"].state()
    steps = research.step_claims(st, "TEST-2026-0001")
    assert [c["artifact"]["step"]["step"] for _, c in steps] == ["read_advisory", "design_test", "propose_fix"]
    for cid, claim in steps:
        step = claim["artifact"]["step"]
        assert step["prompt"] and step["answer"] and step["source"] == "recorded" and step["model"] is None
        assert step["how"] == fixtures.HOW and len(step["prompt_sha256"]) == 64 == len(step["answer_sha256"])
        verdict = st.settled(cid)[1]
        assert verdict["status"] == "accept" and verdict["tier"] == "V0-certificate"
    in_pack = _advisory(built, 1)["steps"]
    assert [s["claim"] for s in in_pack] == [cid for cid, _ in steps] and all("prompt" not in s for s in in_pack)
    # the design in the pack names the recorded answer it was made from
    design = built["pack"].pack["tests"][0]["design"]
    assert design["model_step"] == {"prompt_sha256": in_pack[1]["prompt_sha256"], "answer_sha256": in_pack[1]["answer_sha256"]}


@pytest.mark.needs_otto
@pytest.mark.slow
def test_the_harness_judged_and_a_second_author_replayed(built):
    st = built["lab"].state()
    decisions = {d["outcome"] for _, d in st.of("decision")}
    assert decisions == {"supported", "refuted"} and all(d["author"] == "otto-judge" for _, d in st.of("decision"))
    assert {r["author"] for _, r in st.of("run")} == {research.EXECUTOR}
    audits = [a for _, a in st.of("audit")]
    assert audits and all(a["author"] == research.VALIDATOR and not a["mismatches"] and a["code_ok"] for a in audits)
    assert not any(r for _, r in st.of("review"))                 # the model judge of Adam's loop was never used
    assert built["lab"].audit(reverify=True) == []
    head = built["lab"].ledger.head()
    assert built["pack"].pack["otto"]["ledger"]["height"] <= head["height"]
    assert built["pack"].pack["otto"]["commit"] == harness.read_lock().commit


@pytest.mark.needs_otto
@pytest.mark.slow
def test_the_pack_file_is_signed_and_reads_back(built):
    path = built["folder"] / "packs" / "2026.11.1.json"
    keys = {built["key"]: ("A key made for a test", False)}
    pack = packs.read_file(path, keys)
    assert pack.fingerprint == built["pack"].fingerprint and pack.pack["research"]["answers"] == "recorded"
    assert pack.pack["research"]["answers_note"] == "Answers recorded during the build, 17 November 2026"
    with pytest.raises(packs.PackError) as unknown:
        packs.read_file(path, {})
    assert "does not trust" in str(unknown.value)
    raw = path.read_bytes()
    changed = raw.replace(b"Out-of-range signature accepted", b"Out-of-range signature rejected", 1)
    assert changed != raw
    with pytest.raises(packs.PackError) as tampered:
        packs.read_envelope(changed, keys)
    assert "changed after it was signed" in str(tampered.value)
    for entry in pack.pack["advisories"]:
        assert entry["ledger"] and entry["ledger"][0]["kind"] == "question"
        text = json.dumps(entry)
        assert "secure" not in text.lower() and "score" not in text.lower()


@pytest.mark.needs_otto
@pytest.mark.slow
def test_the_ledger_file_was_written_only_by_the_harness(built):
    """The ledger is a hash chain: Otto's own command line audits it from the pinned copy."""
    found = harness.status()
    done = subprocess.run([sys.executable, "-m", "otto", "--lab", str(built["folder"] / "lab"), "audit"], cwd=found.path,
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0 and "chain intact, every decision re-derived" in done.stdout, done.stdout[-400:] + done.stderr[-400:]


def test_the_app_never_imports_the_research_side():
    app = Path(__file__).resolve().parents[2] / "app"
    for path in app.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import ottolab" not in text and "from ottolab" not in text, path
