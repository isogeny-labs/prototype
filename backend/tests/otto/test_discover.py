"""Phase 6, Otto's research loop: Look for new advisories, and Design and prove tests (app/otto/discover.py).

A look reads published advisories about the assessment's libraries from a public source (here: recorded answers in a
folder, or a stand-in for the network) and says where each one stands. It runs nothing and proposes nothing. A
research run is started by a second click; what it proves is signed into a test pack made on this computer, which
that same click installs. The real run, on public copies in containers, is the slow test at the end."""
import json
import sys
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

import otto_helpers as helpers
from app.accuracy_otto import DEPENDENCIES_FILE
from app.db import OttoLookupRow, OttoResearchRow, TestRunRow
from app.errors import Conflict
from app.otto import harness, lookup
from app.present import lookup as words
from app.web import models
from conftest import demo_plan
from tests.view_helpers import problems

BANNED = ("secure", "score", "severity", "critical", "cvss")


def _record(record_id, cve, package, introduced, fixed, summary, published="2099-01-02T10:11:12Z") -> dict:
    """A record in OSV's documented shape. Written for a test: it is not a published advisory."""
    return {"id": record_id, "summary": summary, "details": "Written for a test.\n\nA signature that is not genuine is accepted.",
            "aliases": [cve] if cve else [], "published": published, "modified": published,
            "database_specific": {"severity": "CRITICAL"}, "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N"}],
            "affected": [{"package": {"ecosystem": package[0], "name": package[1]},
                          "ranges": [{"type": "SEMVER", "events": [{"introduced": introduced}, *([{"fixed": fixed}] if fixed else [])]}]}]}


ELLIPTIC = [
    _record("GHSA-test-0001-aaaa", "CVE-2099-0001", ("npm", "elliptic"), "2.0.0", "6.5.7", "Written for a test: fixed in a version the app has"),
    _record("GHSA-test-0002-bbbb", "CVE-2099-0002", ("npm", "elliptic"), "0", "6.6.1", "Written for a test: fixed in a version the app has no copy of",
            published="2099-03-01T00:00:00Z"),
    _record("GHSA-test-0003-cccc", "CVE-2099-0003", ("npm", "elliptic"), "7.0.0", "7.0.1", "Written for a test: about versions you do not have"),
    _record("GHSA-test-0004-dddd", "CVE-2022-21449", ("npm", "elliptic"), "0", "6.5.7", "Written for a test: its id is in an installed pack"),
    _record("GHSA-test-0005-eeee", "CVE-2099-0005", ("npm", "elliptic"), "0", None, "Written for a test: no fixed version is named"),
]
ECDSA = [_record("PYSEC-2099-12", None, ("PyPI", "ecdsa"), "0", "0.13.3", "Written for a test: about python-ecdsa")]


def _answer(records) -> bytes:
    return json.dumps({"vulns": records}).encode("utf-8")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A demo-mode Lab with one installed pack, the Acme Pay file, the demo dependency list, and a folder of recorded
    answers as the advisory source."""
    source = tmp_path / "advisory-source"
    source.mkdir()
    (source / "npm__elliptic.json").write_bytes(_answer(ELLIPTIC))
    (source / "PyPI__ecdsa.json").write_bytes(_answer(ECDSA))
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    made = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public], advisory_source_dir=source)
    made.plan = demo_plan(made)
    made.check_pack_updates()
    made.install_pack("2026.11.1")
    made.add_dependency_list(made.plan.id, DEPENDENCIES_FILE.name, DEPENDENCIES_FILE.read_bytes())
    yield made
    made.stop()


def _count(lab, row) -> int:
    with lab.db() as db:
        return int(db.scalar(select(func.count(row.id))) or 0)


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


# ---------------------------------------------------------------- before a look

def test_before_any_look_the_block_says_what_a_look_will_do_and_nothing_was_asked(lab):
    view = lab.advisories_view(lab.plan.id)
    assert problems(view, models.AdvisoriesView, "advisories") == []
    block = view["lookup"]
    assert block["title"] == "New advisories" and block["last"] is None and block["busy"] is False
    assert "elliptic 6.5.6" in block["libraries_line"] and "python-ecdsa 0.13.2" in block["libraries_line"]
    look = block["look"]
    assert look["label"] == "Look for new advisories" and look["can"] is True and look["blocked_reason"] is None
    said = " ".join(look["dialog"]["lines"])
    # the source here is a folder of recorded answers: nothing is sent, and the box says so
    assert "Nothing is sent anywhere." in said and "Reading is free: Claude is not asked, nothing runs, and nothing is proposed by looking." in said
    assert "Not asked about: " in said and "openssl" in said and "openjdk" in said
    assert (look["dialog"]["confirm"], look["dialog"]["cancel"]) == ("Look", "Cancel")
    assert block["research"]["shown"] is False and block["research"]["progress"] is None
    assert "No test yet" in block["covers"] and "OSV (osv.dev)" in block["covers"]
    assert _count(lab, OttoLookupRow) == 0


def test_with_the_public_source_the_box_names_exactly_what_is_sent_and_only_that_is_sent(lab, monkeypatch):
    object.__setattr__(lab.settings, "advisory_source_dir", None)        # (no folder of recorded answers: the public source)
    sent = []

    def transport(body, timeout):
        asked = json.loads(body)
        sent.append(asked)
        return 200, _answer({"elliptic": ELLIPTIC, "ecdsa": ECDSA}.get(asked["package"]["name"], []))
    monkeypatch.setattr(lookup, "_http_transport", transport)
    lines = lab.advisories_view(lab.plan.id)["lookup"]["look"]["dialog"]["lines"]
    assert lines[0].startswith("Asks OSV (osv.dev), a public database of published advisories")
    assert lines[1] == "What is sent: these package names, and nothing else: ecdsa (PyPI), elliptic (npm) and stdlib (Go)."
    assert "No version, no address and no file leaves this computer." in lines[2]
    assert sent == []                                    # reading the page asked nothing
    block = lab.look_for_advisories(lab.plan.id)["lookup"]
    assert sent == [{"package": {"name": "ecdsa", "ecosystem": "PyPI"}}, {"package": {"name": "elliptic", "ecosystem": "npm"}},
                    {"package": {"name": "stdlib", "ecosystem": "Go"}}]
    assert block["last"]["source_line"] == "Read from OSV (osv.dev). Sent: ecdsa (PyPI), elliptic (npm) and stdlib (Go), and nothing else."
    # nothing of the assessment but those names is in what was sent
    whole = json.dumps(sent)
    for private in ("6.5.6", "0.13.2", "localhost", "acme", "Acme"):
        assert private not in whole


# ---------------------------------------------------------------- a look

def test_a_look_says_where_each_advisory_stands_and_why_there_is_no_test_yet(lab):
    runs_before = _count(lab, TestRunRow)
    proposals_before = lab.otto_proposals(lab.plan.id)
    view = lab.look_for_advisories(lab.plan.id)
    assert problems(view, models.AdvisoriesView, "advisories after a look") == []
    last = view["lookup"]["last"]
    rows = {r["id"]: r for r in last["rows"]}
    assert set(rows) == {"CVE-2099-0002", "CVE-2022-21449", "CVE-2099-0001", "CVE-2099-0003", "CVE-2099-0005", "PYSEC-2099-12"}
    assert last["rows"][0]["id"] == "CVE-2099-0002"                         # the newest first
    # fixed in a version the app has a public copy of, and an older copy too: it can be tried
    new = rows["CVE-2099-0001"]
    assert new["state"] == {"key": "new", "label": "New: not tried yet", "tone": "warn"} and new["reason"] is None
    assert new["fits"] == "Names elliptic 6.5.6, which your dependency list lists; fixed in 6.5.7."
    assert new["title"] == "Written for a test: fixed in a version the app has" and new["publisher"] == "GitHub Advisory Database"
    assert new["url"] == "https://osv.dev/vulnerability/GHSA-test-0001-aaaa" and new["library"] == "elliptic"
    assert rows["PYSEC-2099-12"]["state"]["key"] == "new" and "python-ecdsa 0.13.2" in rows["PYSEC-2099-12"]["fits"]
    # fixed in a version the app has no public copy of: no test is designed, and it says why
    none = rows["CVE-2099-0002"]
    assert none["state"]["key"] == "no_test" and none["state"]["label"] == "No test yet"
    assert none["reason"] == ("No test yet: a test is proven against the fixed version, elliptic 6.6.1, and this version of the app has no "
                              "public copy of it (it has elliptic 6.5.6 and elliptic 6.5.7), so none was designed.")
    assert rows["CVE-2099-0005"]["reason"] == words.NO_FIXED_VERSION
    # about versions the assessment does not have
    assert rows["CVE-2099-0003"]["state"]["key"] == "not_yours"
    assert rows["CVE-2099-0003"]["fits"] == "elliptic 6.5.6, which your dependency list lists, is not among the versions it names."
    # its id is in an installed test pack already: it links to its row on this page
    packed = rows["CVE-2022-21449"]
    assert packed["state"]["key"] == "in_pack" and "test pack 2026.11.1" in packed["state"]["label"]
    assert packed["link"] == {"page": "advisories", "item": "CVE-2022-21449"}
    assert last["line"].startswith("Looked on ") and "6 published advisories about your libraries." in last["line"]
    assert "2 are new and can be tried here" in last["line"] and "2 have no test yet" in last["line"]
    assert last["source_line"] == "Read from recorded answers in a folder on this computer. Nothing was sent."
    # looking ran nothing, proposed nothing, and asked Claude nothing (the suite's stand-in would have failed the test)
    assert _count(lab, TestRunRow) == runs_before and lab.otto_proposals(lab.plan.id) == proposals_before
    assert _count(lab, OttoLookupRow) == 1 and _count(lab, OttoResearchRow) == 0
    # how serious an advisory is, is nowhere on the page
    for said in _texts(view["lookup"]):
        assert not any(word in said.lower() for word in BANNED), said


def test_a_look_is_kept_add_only_and_the_evidence_part_holds_what_was_asked_and_found(lab):
    lab.look_for_advisories(lab.plan.id)
    lab.look_for_advisories(lab.plan.id)
    assert _count(lab, OttoLookupRow) == 2
    with lab.db() as db:
        with pytest.raises(Exception, match="append-only"):
            db.execute(text("update otto_lookups set source = 'x'"))
            db.commit()
    part = lab.lookups_evidence(lab.plan.id)
    assert [look["number"] for look in part["looks"]] == [1, 2] and part["research"] == []
    one = part["looks"][0]
    assert one["source"] == "recorded" and one["sent"] == [] and one["by"] == "You"
    assert [a["library"] for a in one["asked"]] == ["python-ecdsa", "elliptic", "go-stdlib"]
    assert all(len(sha) == 64 for a in one["asked"] for sha in a["sha256"])
    assert {f["id"] for f in one["found"]} == {"CVE-2099-0001", "CVE-2099-0002", "CVE-2099-0003", "CVE-2022-21449", "CVE-2099-0005", "PYSEC-2099-12"}
    assert not any(word in json.dumps(part).lower() for word in BANNED)


def _verify(tmp_path, lab, name: str):
    """Download the evidence and check it with the verify command, as a customer would."""
    import subprocess
    from pathlib import Path
    made = lab.export_evidence(lab.plan.id)
    _, raw, _ = lab.evidence_file(made["id"], "json")
    file = tmp_path / name
    file.write_bytes(raw)
    done = subprocess.run([sys.executable, "-m", "evidence", "verify", str(file), "--data-dir", str(lab.settings.data_dir)],
                          cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=120)
    return json.loads(raw)["evidence"], done


@pytest.mark.needs_otto
def test_a_look_alone_is_in_the_signed_evidence_and_the_verify_command_checks_it(tmp_path, monkeypatch):
    """An assessment where a person only looked (no check added, no decision) still has the look in its evidence."""
    source = tmp_path / "advisory-source"
    source.mkdir()
    (source / "npm__elliptic.json").write_bytes(_answer(ELLIPTIC))
    (source / "PyPI__ecdsa.json").write_bytes(_answer(ECDSA))
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {}, [], advisory_source_dir=source)
    try:
        lab.plan = demo_plan(lab)
        lab.add_dependency_list(lab.plan.id, DEPENDENCIES_FILE.name, DEPENDENCIES_FILE.read_bytes())
        lab.verify(lab.plan.imp["id"])
        assert lab.otto_evidence(lab.plan.id) is None                 # nothing of Otto's yet: no Otto part
        lab.look_for_advisories(lab.plan.id)
        evidence, done = _verify(tmp_path, lab, "looked.json")
        part = evidence["otto"]
        assert part["checks"] == [] and part["packs"] == [] and len(part["lookups"]["looks"]) == 1 and part["lookups"]["research"] == []
        assert done.returncode == 0, done.stdout + done.stderr
        assert "Looks for new advisories: 1, each with what was asked and the fingerprint of each answer; research runs: 0 finished" in done.stdout
    finally:
        lab.stop()


@pytest.mark.needs_otto
def test_a_research_runs_pack_is_in_the_evidence_whether_or_not_a_check_of_it_was_accepted(lab, monkeypatch, tmp_path):
    """The proof of what a run found is in the pack it made. So that pack is in the file, signature and all, as soon as
    the run is on record; and a file whose run names a pack that is not in it does not check."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.db import OttoPackRow
    from app.otto import packs
    from evidence import otto as evidence_otto
    key = Ed25519PrivateKey.generate()                                 # stands for the key made on this computer
    (lab.settings.data_dir / packs.LOCAL_KEY_FILE).write_text(helpers.public_hex(key) + "\n", encoding="ascii")
    with lab.db() as db:
        first = db.scalars(select(OttoPackRow)).one().fingerprint
    second, _ = helpers.make_pack("2026.11.2", first, [helpers.pack_advisory("CVE-2099-0001", "Made for a test", "elliptic")], key=key)
    made = lab.settings.otto_local_updates
    lab.verify(lab.plan.imp["id"])
    lab.look_for_advisories(lab.plan.id)
    demo_mode = lab.mode
    _pretend_isolated(lab, monkeypatch)
    # (a stand-in for the research command that leaves a signed pack in the data folder's updates, as the real one does)
    _stand_in(lab, monkeypatch, "import pathlib; d = pathlib.Path(%r); d.mkdir(parents=True, exist_ok=True); "
                                "(d / '2026.11.2.json').write_bytes(bytes.fromhex(%r)); print('Wrote test pack 2026.11.2')" % (str(made), second.hex()))
    lab.start_research(lab.plan.id)
    lab.wait_until_research_done(60)
    with lab.db() as db:
        end = db.scalars(select(OttoResearchRow).where(OttoResearchRow.kind == "finished")).one()
    assert (end.exit_code, end.pack_version) == (0, "2026.11.2"), (end.output, end.reason)
    monkeypatch.setattr(lab, "mode", demo_mode)                        # (the download says which mode the app is in)
    evidence, done = _verify(tmp_path, lab, "after-a-run.json")
    part = evidence["otto"]
    assert part["checks"] == []                                        # nobody accepted anything
    assert [p["pack"]["version"] for p in part["packs"]] == ["2026.11.2"]
    assert done.returncode == 0, done.stdout + done.stderr
    assert "research runs: 1 finished, each pack they made is in the file." in done.stdout
    # the same record without the pack: the run's proof is missing, and the check says so
    without = evidence_otto.check_otto({**evidence, "otto": {**part, "packs": []}}, evidence_otto.pack_keys(lab.settings.data_dir))
    assert without.code != evidence_otto.OK and "names test pack 2026.11.2, which is not in the file" in (without.problem or "")


def test_an_assessment_that_names_no_library_the_source_keeps_cannot_look_and_says_why(tmp_path, monkeypatch):
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    try:
        plan = demo_plan(lab)                 # the Acme Pay file alone: a demo program and a server, no known library
        block = lab.advisories_view(plan.id)["lookup"]
        assert block["look"]["can"] is False and block["look"]["blocked_reason"] == words.LOOK_NOTHING_TO_ASK
        assert block["libraries_line"] == "This assessment names no library the app knows."
        with pytest.raises(Conflict) as refused:
            lab.look_for_advisories(plan.id)
        assert str(refused.value) == words.LOOK_NOTHING_TO_ASK
    finally:
        lab.stop()


def test_a_source_that_cannot_be_read_changes_nothing_and_says_so(lab, monkeypatch):
    object.__setattr__(lab.settings, "advisory_source_dir", None)
    monkeypatch.setattr(lookup, "_http_transport", lambda body, timeout: (_ for _ in ()).throw(OSError("no route")))
    with pytest.raises(Conflict) as refused:
        lab.look_for_advisories(lab.plan.id)
    assert str(refused.value) == "OSV (osv.dev) could not be reached (OSError). Nothing was changed."
    assert _count(lab, OttoLookupRow) == 0


# ---------------------------------------------------------------- Design and prove tests: when it can be pressed

def test_design_and_prove_is_off_with_the_reason_until_it_can_work(lab, monkeypatch):
    lab.look_for_advisories(lab.plan.id)
    research = lab.advisories_view(lab.plan.id)["lookup"]["research"]
    assert research["shown"] is True and research["label"] == "Design and prove tests (2)"
    # this Lab is in demo mode: a real library runs only in its own container
    assert research["can"] is False and research["blocked_reason"] == words.RESEARCH_NEEDS_ISOLATED
    with pytest.raises(Conflict) as refused:
        lab.start_research(lab.plan.id)
    assert str(refused.value) == words.RESEARCH_NEEDS_ISOLATED and _count(lab, OttoResearchRow) == 0
    said = " ".join(research["dialog"]["lines"])
    assert research["dialog"]["title"] == "Design and prove tests for 2 advisories?"
    assert "it fails on the affected version, passes on the fixed version, and the control that must fail does" in said
    assert "Live Otto is off: only answers recorded during the build are used." in said and "No recorded answer: this needs Live Otto." in said
    assert "that pack is installed by this click" in said and "Accepting or rejecting it stays with you" in said
    # without Otto: the sentence Settings shows
    missing = harness.OttoStatus(False, harness.NOT_FETCHED, "isogeny-labs/otto", "a" * 40, "0.1.0", None)
    monkeypatch.setattr(harness, "status", lambda *a, **k: missing)
    assert lab.advisories_view(lab.plan.id)["lookup"]["research"]["blocked_reason"] == missing.sentence


def test_a_closed_assessment_can_neither_look_nor_start_a_run(lab):
    lab.look_for_advisories(lab.plan.id)
    lab.update_assessment(lab.assessment_for(plan_id=lab.plan.id).id, {"close": True, "signed_off_by": "A tester"})
    block = lab.advisories_view(lab.plan.id)["lookup"]
    assert block["look"]["can"] is False and block["look"]["blocked_reason"] == words.CLOSED_SENTENCE
    assert block["research"]["can"] is False and block["research"]["blocked_reason"] == words.CLOSED_SENTENCE
    assert block["last"] is not None            # what was found before closing is still shown


# ---------------------------------------------------------------- a research run (the command is a stand-in here)

def _pretend_isolated(lab, monkeypatch):
    monkeypatch.setattr(lab, "mode", SimpleNamespace(name="isolated"))


def _stand_in(lab, monkeypatch, script: str) -> list[list[str]]:
    """Replace the research command by a small script (the real one needs Docker; it has the slow test below)."""
    seen: list[list[str]] = []
    real = lab._research_command

    def command(inbox, live, limit_nano):
        seen.append(real(inbox, live, limit_nano))
        return [sys.executable, "-c", script, str(inbox)]
    monkeypatch.setattr(lab, "_research_command", command)
    return seen


@pytest.mark.needs_otto
def test_a_research_run_is_started_by_the_click_runs_in_the_background_and_its_end_is_kept(lab, monkeypatch):
    lab.look_for_advisories(lab.plan.id)
    _pretend_isolated(lab, monkeypatch)
    seen = _stand_in(lab, monkeypatch, "import sys, json; d = json.load(open(sys.argv[1] + '/advisories.json')); "
                                       "print('read', [a['id'] for a in d['advisories']]); print('Stopped: written for a test'); sys.exit(1)")
    view = lab.start_research(lab.plan.id)
    assert problems(view, models.AdvisoriesView, "advisories while a run goes on") == []
    assert view["lookup"]["busy"] in (True, False)          # (a stand-in this short may already have ended)
    lab.wait_until_research_done(60)
    block = lab.advisories_view(lab.plan.id)["lookup"]
    progress = block["research"]["progress"]
    assert block["busy"] is False and progress["running"] is False
    assert progress["lines"] == ["read ['CVE-2099-0001', 'PYSEC-2099-12']", "Stopped: written for a test"] or \
        progress["lines"] == ["read ['PYSEC-2099-12', 'CVE-2099-0001']", "Stopped: written for a test"]
    assert progress["line"].endswith("without a test pack: Stopped: written for a test")
    # only the advisories that can be tried were handed over, in the snapshot's own shape, and the command is the research side's
    assert seen[0][1:5] == ["-m", "ottolab.build", "next", "--inbox"] and "--live" not in seen[0]
    assert seen[0][seen[0].index("--limit") + 1] == "2.00"
    with lab.db() as db:
        rows = list(db.scalars(select(OttoResearchRow).order_by(OttoResearchRow.id)))
    assert [(r.kind, r.exit_code, r.pack_version) for r in rows] == [("started", None, None), ("finished", 1, None)]
    assert sorted(rows[0].advisories) == ["CVE-2099-0001", "PYSEC-2099-12"] and rows[0].live is False and rows[0].installed_first == []
    part = lab.lookups_evidence(lab.plan.id)["research"]
    assert [(r["what"], r["exit_code"]) for r in part] == [("started", None), ("finished", 1)]
    # the advisories are still new: nothing was proposed, and nothing of the assessment ran
    states = {r["id"]: r["state"]["key"] for r in block["last"]["rows"]}
    assert states["CVE-2099-0001"] == "new" and states["PYSEC-2099-12"] == "new"
    assert all(p["about"].get("advisory") == "CVE-2022-21449" for p in lab.otto_proposals(lab.plan.id, ("check",)))


@pytest.mark.needs_otto
def test_a_research_run_is_ended_with_the_app_and_never_left_behind(lab, monkeypatch, tmp_path):
    """Stopping the app ends a run that is still going, with what it started. Its end is kept and says so."""
    lab.look_for_advisories(lab.plan.id)
    _pretend_isolated(lab, monkeypatch)
    alive = tmp_path / "still-going"
    # (a stand-in that would go on for a minute, and starts a child of its own, as the real command starts containers)
    _stand_in(lab, monkeypatch, "import subprocess, sys, time, pathlib; print('started', flush=True); "
                                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
                                f"time.sleep(60); pathlib.Path({str(alive)!r}).write_text('it went on')")
    lab.start_research(lab.plan.id)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not any("started" in line for s in lab._research_live.values() for line in s["lines"]):
        time.sleep(0.05)
    [state] = list(lab._research_live.values())
    process = state["process"]
    began = time.monotonic()
    lab.stop_research()
    assert time.monotonic() - began < 20 and process.poll() is not None and not state["thread"].is_alive()
    with lab.db() as db:
        end = db.scalars(select(OttoResearchRow).where(OttoResearchRow.kind == "finished")).one()
    assert end.pack_version is None and end.reason == words.INTERRUPTED
    block = lab.advisories_view(lab.plan.id)["lookup"]
    assert block["busy"] is False and block["research"]["progress"]["line"].endswith(words.INTERRUPTED)
    time.sleep(0.5)
    assert not alive.exists()
    # the child it had started is gone too: nothing of the run goes on working
    # (a process that has ended can stay listed as "defunct" until something collects it: that one works on nothing)
    import subprocess as sp
    from pathlib import Path
    listed = sp.run(["pgrep", "-g", str(process.pid)], capture_output=True, text=True).stdout.split()

    def working(pid: str) -> bool:
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return False
    assert [pid for pid in listed if working(pid)] == []


@pytest.mark.needs_otto
@pytest.mark.parametrize("table, column", [("otto_lookups", "source"), ("otto_research", "kind")])
def test_raw_sql_cannot_change_or_delete_a_look_or_a_research_run(lab, monkeypatch, table, column):
    """Both records only accept new rows: the database itself refuses a change or a removal."""
    lab.look_for_advisories(lab.plan.id)
    _pretend_isolated(lab, monkeypatch)
    _stand_in(lab, monkeypatch, "print('Stopped: written for a test'); raise SystemExit(1)")
    lab.start_research(lab.plan.id)
    lab.wait_until_research_done(60)
    with lab.db() as db:
        before = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert before > 0
        for statement in (f"UPDATE {table} SET {column} = 'x'", f"DELETE FROM {table}"):
            with pytest.raises(Exception, match="append-only"):
                db.execute(text(statement))
                db.commit()
            db.rollback()
        assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == before


@pytest.mark.needs_otto
def test_only_one_research_run_at_a_time(lab, monkeypatch):
    lab.look_for_advisories(lab.plan.id)
    _pretend_isolated(lab, monkeypatch)
    _stand_in(lab, monkeypatch, "import time; print('started'); time.sleep(3)")
    lab.start_research(lab.plan.id)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not lab.advisories_view(lab.plan.id)["lookup"]["research"]["progress"]["lines"]:
            time.sleep(0.05)
        block = lab.advisories_view(lab.plan.id)["lookup"]
        assert block["busy"] is True and block["research"]["progress"]["running"] is True
        assert block["research"]["can"] is False and block["research"]["blocked_reason"] == words.RESEARCH_RUNNING
        rows = {r["id"]: r["state"]["label"] for r in block["last"]["rows"]}
        assert rows["CVE-2099-0001"] == "Being tried"
        with pytest.raises(Conflict) as refused:
            lab.start_research(lab.plan.id)
        assert str(refused.value) == words.RESEARCH_RUNNING
    finally:
        lab.wait_until_research_done(60)
    assert lab.advisories_view(lab.plan.id)["lookup"]["research"]["progress"]["line"].endswith(words.RESEARCH_NO_PACK)
