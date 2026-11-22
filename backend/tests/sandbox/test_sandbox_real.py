"""Sandbox research, for real: the whole line in locked containers, on recorded answers, with no internet and no key.

A weakness with no fix is on the Watch list (day 1). A look finds the fix (day 2). A person presses Design and prove
tests. The research command reads the advisory, designs a test, fetches six public versions of starkbank-ecdsa from the
recorded registry, has the asking code written twice (recorded answers), screens and checks each, registers the trial
and runs it in containers; what it proves is signed into a pack of the second format, which the same click installs.
The proven check is proposed with its proof. A person accepts it, runs it, and the separate reviewer decides. The
evidence file is then checked by the verify command.

Slow: it needs Docker and the prepared images, Otto's harness, and the six public package files (fetched once by
`tools/research_demo.py --sandbox`, kept in data/downloads)."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from app import prepare
from app.config import Settings
from app.db import OttoResearchRow, TestRunRow
from app.lab.hub import Lab
from app.otto import model, packs
from app.web import models
from conftest import free_port
from evidence.__main__ import main as evidence_main
from tests.view_helpers import problems
from tools import research_demo

ID = "CVE-2021-43572"
ITEM = f"{ID}~starkbank-ecdsa"
FILES_SKIP = ("Skipped: the public package files of the sandbox demo are not on this computer "
              "(run once, with internet: cd backend && .venv/bin/python tools/research_demo.py --sandbox /tmp/sandbox-demo).")


def _runs(lab) -> int:
    with lab.db() as db:
        return int(db.scalar(select(func.count(TestRunRow.id))) or 0)


@pytest.mark.needs_otto
def test_the_whole_line_from_no_fix_yet_to_a_proven_check_a_person_accepts_and_the_reviewer_decides(tmp_path, monkeypatch, docker_ready, capsys):
    if not all((prepare.DOWNLOADS_DIR / pin["file"]).is_file() for pin in research_demo.SANDBOX_PINS):
        pytest.skip(FILES_SKIP)                                  # (never fetched by a test: no test reaches a registry)
    monkeypatch.delenv(model.KEY_ENV, raising=False)             # no key: only the answers recorded during the build
    monkeypatch.setenv("EVIDENCE_LAB_SANDBOX_RESEARCH", "1")     # this computer is the sandbox (the research command reads it too)
    source, registry = research_demo.prepare_sandbox(tmp_path / "demo", day=1)
    monkeypatch.setenv("EVIDENCE_LAB_REGISTRY_SOURCE", str(registry))
    lab = Lab(Settings(data_dir=tmp_path / "data", demo_tls_port=free_port(), advisory_source_dir=source, registry_source_dir=registry,
                       sandbox_research=True, watch_clock=False, speed_rounds=25, speed_repeats=4))
    lab.start()
    try:
        assert lab.mode.name == "isolated" and lab.sandbox_blocked() == []
        lab.set_sandbox(on=True)
        imp = lab.import_file(research_demo.SANDBOX_FILE.name, research_demo.SANDBOX_FILE.read_bytes())
        pid = lab.ensure_plan(imp["id"])["id"]

        # ---- day 1: a weakness with no fix yet is on the Watch list, and nothing can be tried
        watch = lab.watch_list_look(pid)
        item = next(i for i in watch["items"] if i["key"] == ITEM)
        assert item["status"]["key"] == "no_fix" and "Demo data" in json.dumps(item)
        row = lab.lookup_view(pid)["last"]["rows"][0]
        assert row["state"]["key"] == "no_test" and row["watch"]["link"]["item"] == ITEM
        assert lab.lookup_view(pid)["research"]["can"] is False

        # ---- day 2: the source names a fixed version; the item is marked, and a test can be tried
        research_demo.sandbox_source(source, 2)
        watch = lab.watch_list_look(pid)
        item = next(i for i in watch["items"] if i["key"] == ITEM)
        assert item["status"]["key"] == "fix_published"
        block = lab.lookup_view(pid)
        assert block["last"]["rows"][0]["state"]["key"] == "new" and block["last"]["rows"][0]["sandbox"] is True
        assert block["research"]["can"] is True and any(line.startswith("From PyPI: starkbank-ecdsa 2.0.1") for line in block["research"]["dialog"]["lines"])
        assert lab.otto_proposals(pid, ("check",)) == []         # looking proposed nothing

        # ---- the click: design and prove
        runs_before = _runs(lab)
        lab.start_research(pid)
        lab.wait_until_research_done(3600)
        with lab.db() as db:
            end = db.scalars(select(OttoResearchRow).where(OttoResearchRow.kind == "finished")).one()
        assert end.exit_code == 0, end.output[-25:]
        assert end.sandbox is True and end.live is False and end.spent_nano == 0 and end.installed_first == ["2026.11.1", "2026.11.2"]
        made = end.pack_version
        installed = lab.otto_view()["packs"]["installed"]
        assert installed[-1]["version"] == made and installed[-1]["made_here"] is True
        view = lab.advisories_view(pid)
        assert problems(view, models.AdvisoriesView, "advisories after a sandbox research run") == []
        assert _runs(lab) == runs_before                         # nothing of the assessment ran

        # ---- the pack: second format, with everything the proof rests on
        with lab.db() as db:
            pack = next(p for _, p in lab._installed_packs(db) if p.version == made)
        assert pack.pack["schema"] == packs.PACK_SCHEMA_2
        entry = pack.advisory(ID)
        arms, extra = entry["test"]["trial"]["arms"], entry["test"]["sandbox"]
        assert entry["test"]["state"] == "ready" and entry["test"]["trial"]["outcome"] == "supported" and entry["test"]["trial"]["replayed"] is True
        assert (arms["affected"]["version"], arms["affected"]["wrong"], arms["affected"]["total"]) == ("2.0.0", 1, 64)
        assert (arms["fixed"]["version"], arms["fixed"]["wrong"]) == ("2.0.1", 0) and arms["accept-all"]["wrong"] == 64
        assert arms["affected-b"]["agree"] == 64 and arms["fixed-b"]["agree"] == 64          # the two authors' code agreed on every case
        assert extra["versions"]["more_fixed"] == ["2.0.2", "2.3.1"] and all(arms[f"more-fixed-{n}"]["wrong"] == 0 for n in (1, 2))
        assert {v["version"] for v in extra["versions"]["left_out"]} == {"1.1.0", "1.1.1"}  # the frozen code does not work there: left out, with the reason
        assert extra["known"]["controls_refused"] is True and extra["second_known"]["controls_refused"] is True
        assert [s["step"] for s in entry["steps"]] == ["read_advisory", "design_test", "write_wrapper", "write_wrapper", "propose_fix"]
        assert all(s["source"] == "recorded" and s["model"] is None and s["cost_nano_usd"] == 0 for s in entry["steps"])
        # the publisher's fix is not offered as proven: the fixed version still fails other locked tests, and that is said
        assert entry["fix"]["state"] == "not_proven" and entry["fix"]["version"] == "2.0.1"

        # ---- the proposal, with its proof; a person decides
        listed = next(r for r in view["rows"] if r["id"] == ID)
        card = listed["panel"]["here"]["rows"][0]["proposal"]
        assert card["status"]["key"] == "proposed" and card["proof"]["label"] == "Sandbox copy"
        assert card["proof"]["code"]["label"] == "Written by Otto" and card["proof"]["code"]["second"] is not None
        mine = next(p for p in lab.otto_proposals(pid, ("check",)) if p["about"]["advisory"] == ID)
        lab.otto_decide(pid, mine["id"], "accept")
        assert _runs(lab) == runs_before                         # accepting ran nothing
        item_id = next(r["item_id"] for r in lab.lab_view(pid)["rows"] if ID in str(r.get("title")))

        # ---- the accepted check runs on the sandbox copy, and the separate reviewer decides it
        lab.run_test(pid, item_id)
        lab.wait_until_idle(pid, 600)
        result = next(r for r in lab.lab_view(pid)["rows"] if r["item_id"] == item_id)["result"]
        assert (result["code"], result["label"], result["component"], result["mode"]) == ("failed", "Failed", "starkbank-ecdsa 2.0.0", "isolated")
        assert "got 1 of the 64 published cases" in result["plain"] and result["sandbox_copy"] is True
        assert result["control"]["outcome"] == "as_expected"
        here = next(r for r in lab.advisories_view(pid)["rows"] if r["id"] == ID)["panel"]["here"]["rows"][0]
        assert here["result"]["label"] == "Failed" and here["result"]["sandbox_copy"] is True
        assert "sandbox copy" in here["result"]["source_tag"]["note"]
        # the Watch list says where the item stands now, and decides nothing
        item = next(i for i in lab.watch_list_view(pid)["items"] if i["key"] == ITEM)
        assert item["status"]["key"] in ("test_proposed", "fix_published")

        # ---- the evidence, checked by the verify command
        export = lab.export_evidence(pid)
        name, raw, _ = lab.evidence_file(export["id"], "json")
        path = tmp_path / name
        path.write_bytes(raw)
        capsys.readouterr()
        assert evidence_main(["verify", str(path), "--data-dir", str(lab.settings.data_dir)]) == 0
        said = capsys.readouterr().out
        assert "Evidence verified" in said and "1 test tried on sandbox copies" in said and "on a sandbox copy, each in an image named after a copy set" in said

        # ---- the switch off: the copy is no longer seen, and nothing of it runs
        lab.set_sandbox(on=False)
        from app import real_libraries
        assert real_libraries.library("starkbank-ecdsa", "2.0.0") is None
    finally:
        lab.stop()
