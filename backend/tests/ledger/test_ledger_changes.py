"""Phase 5b: a migration change's try on a test copy, and the measurements the app made by itself after Apply and Roll
back, in the list of checks: each run once, in Migration, with where it came from and the change box it links back to.
(The walk takes a while, so it is in the full set.)"""
import pytest

from app.servers import migration_servers
from app.web import models
from tests.view_helpers import problems
from tests.conftest import free_port, free_ports, make_lab, play_back_speed

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def changed(tmp_path_factory):
    ports = free_ports(5)
    lab = make_lab(tmp_path_factory.mktemp("ledger-changes"), migration_ports=ports, lab_nginx_port=free_port())
    play_back_speed(lab)
    try:
        imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        lab.verify(imp["id"])
        plan = lab.ensure_plan(imp["id"])
        lab.measure_migration(plan["id"])
        lab.wait_until_measured(plan["id"], 300)
        address = f"localhost:{ports[1]}"                      # c1: classical, internet-facing, long-lived
        key = f"migration:server:{address}"
        lab.try_change(plan["id"], key)
        lab.wait_until_changes_idle(plan["id"])
        lab.ask_approval(plan["id"], key, ["you"])
        lab.approve_change(plan["id"], key, "you")
        lab.apply_change(plan["id"], key)
        lab.wait_until_changes_idle(plan["id"])
        lab.rollback_change(plan["id"], key)
        lab.wait_until_changes_idle(plan["id"])
        yield lab, plan["id"], address, key
    finally:
        lab.stop()


def test_the_try_is_a_check_in_migration_that_links_back_to_its_change_box(changed):
    lab, pid, address, key = changed
    view = lab.checks_view(pid)
    assert problems(view, models.ChecksView, "checks") == []
    migration = next(g for g in view["groups"] if g["key"] == "migration")
    tries = [r for r in migration["rows"] if r["came_from"]["key"] == "try"]
    assert tries and all(r["link"] == {"page": "migration/systems", "item": f"server:{address}"} for r in tries)
    assert all(r["result"] is not None for r in tries if not r["ran_on"].startswith("Real nginx"))


def test_the_measurements_after_apply_and_roll_back_are_runs_of_the_systems_own_check(changed):
    lab, pid, address, key = changed
    led = lab.ledger(pid)
    row = next(r for r in led["rows"] if r["id"] == f"system-server:{address}")
    origins = [h["came_from"] for h in row["history"]]
    assert origins[:2] == ["After Roll back", "After Apply"] and origins[-1] == "Measure status"
    assert row["came_from"]["label"] == "After Roll back"              # where its newest run came from
    # the newest result is the one the Systems page shows
    system = next(s for s in lab.migration_view(pid)["systems"] if s["key"] == f"server:{address}")
    assert row["result"]["label"] == system["status"]["label"]
    # every run once
    counted = [rid for r in led["rows"] for rid in r.get("run_ids") or []]
    assert len(counted) == len(set(counted))


def test_the_change_is_one_fix_in_migration_with_its_counts(changed):
    lab, pid, address, key = changed
    view = lab.fixes_view(pid)
    fix = next(f for f in view["fixes"] if (f.get("change_box") or {}).get("id") == key)
    assert fix["group"] == "migration" and fix["status"]["word"] == "Rolled back" and fix["fix_state"] == "open"
    assert fix["came_from_links"] == [{"label": "The migration plan", "link": {"page": "migration/systems", "item": f"server:{address}"}}]
    detail = lab.check_detail(pid, f"system-server:{address}")
    lines = {line["kind"]: line for line in detail["related"]}
    assert fix["id"] in {i["link"]["item"] for i in lines["fix"]["items"]}
