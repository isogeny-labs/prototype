"""Phase 6, Otto's research loop, for real: a research run that tries a test on public copies in containers.

The set-up is the one `tools/research_demo.py` prepares: only the first built-in pack is there, and the advisory
source is a recorded copy of the three elliptic advisories of the dated snapshot, so the answers recorded during the
build fit them and no key is needed. A person looks, then presses Design and prove tests. The research command reads
each advisory, designs a test, and tries it on elliptic 6.5.6 and 6.5.7 in their containers; what it proves is signed
into a pack made on this computer, which the same click installs. Slow: it needs Docker and takes several minutes."""
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.db import OttoResearchRow, TestRunRow
from app.lab.hub import Lab
from app.otto import model
from app.web import models
from conftest import free_port
from tests.view_helpers import problems
from tools import research_demo

REAL_FILE = research_demo.REPO / "demo" / "real-libraries.csv"


@pytest.mark.needs_otto
def test_a_real_research_run_proves_a_test_on_public_copies_and_the_proven_check_is_proposed(tmp_path, monkeypatch, docker_ready):
    monkeypatch.delenv(model.KEY_ENV, raising=False)             # no key: only the answers recorded during the build
    updates, source = research_demo.prepare(tmp_path / "demo")
    lab = Lab(Settings(data_dir=tmp_path / "data", demo_tls_port=free_port(), otto_updates_dir=updates, advisory_source_dir=source,
                       speed_rounds=25, speed_repeats=4))
    lab.start()
    try:
        assert lab.mode.name == "isolated"
        imp = lab.import_file(REAL_FILE.name, REAL_FILE.read_bytes())
        pid = lab.ensure_plan(imp["id"])["id"]
        assert lab.otto_view()["packs"]["installed"] == []       # nobody has installed a test pack

        # ---- the first click: look
        block = lab.look_for_advisories(pid)["lookup"]
        found = {r["id"]: r for r in block["last"]["rows"]}
        assert set(found) == {"CVE-2024-42459", "CVE-2024-42460", "CVE-2024-42461"}
        assert all(r["state"]["key"] == "new" for r in found.values())
        assert block["last"]["source_line"] == "Read from recorded answers in a folder on this computer. Nothing was sent."
        research = block["research"]
        assert research["can"] is True and research["label"] == "Design and prove tests (3)"
        assert any("the built-in test pack not installed yet (2026.11.1)" in line for line in research["dialog"]["lines"])
        assert lab.otto_proposals(pid, ("check",)) == []         # looking proposed nothing

        # ---- the second click: design and prove
        runs_before = _runs(lab)
        lab.start_research(pid)
        lab.wait_until_research_done(3600)
        with lab.db() as db:
            end = db.scalars(select(OttoResearchRow).where(OttoResearchRow.kind == "finished")).one()
        assert end.exit_code == 0, end.output[-20:]
        assert end.installed_first == ["2026.11.1"] and end.pack_version == "2026.11.2" and end.live is False
        view = lab.advisories_view(pid)
        assert problems(view, models.AdvisoriesView, "advisories after a research run") == []
        installed = lab.otto_view()["packs"]["installed"]
        assert [p["version"] for p in installed] == ["2026.11.1", "2026.11.2"] and installed[1]["made_here"] is True

        # ---- what was proven is proposed; what was not says why
        rows = {r["id"]: r for r in view["lookup"]["last"]["rows"]}
        assert rows["CVE-2024-42460"]["state"]["label"] == "Proven on public copies (test pack 2026.11.2)"
        for other in ("CVE-2024-42459", "CVE-2024-42461"):
            assert rows[other]["state"]["label"] == "No test yet (test pack 2026.11.2)" and rows[other]["reason"]
        listed = {r["id"]: r for r in view["rows"]}
        assert listed["CVE-2024-42460"]["test"]["key"] == "ready" and listed["CVE-2024-42460"]["new"] is not None
        proposed = lab.otto_proposals(pid, ("check",))
        mine = [p for p in proposed if p["about"]["advisory"] == "CVE-2024-42460" and p["about"]["pack"] == "2026.11.2"]
        assert mine and all(p["state"] == "proposed" for p in mine)                 # proposed, never added: a person decides
        assert any("elliptic 6.5.6" in p["about"]["program"] for p in mine)
        # the proof is the pack's own trial on public copies: it failed on the affected copy, passed on the fixed one
        tried = [line for p in mine for line in p["lines"] if line.startswith("Tried on public copies before the pack was signed")]
        assert tried and "elliptic 6.5.6 got" in tried[0] and "elliptic 6.5.7 got 0 wrong" in tried[0] and "the control that must fail did" in tried[0]
        # nothing of the assessment ran, and nothing was added to its test plan
        assert _runs(lab) == runs_before
        assert not any(t["kind"] == "advisory_cases" for t in lab.plan_view(pid)["tests"])
        # the run is on record for the evidence file, with the pack it made
        part = lab.lookups_evidence(pid)
        assert [(r["what"], r["pack_version"]) for r in part["research"]] == [("started", None), ("finished", "2026.11.2")]
    finally:
        lab.stop()


def _runs(lab) -> int:
    with lab.db() as db:
        return int(db.scalar(select(func.count(TestRunRow.id))) or 0)
