"""One short walk of a demo-mode Lab for the tests of Evidence as the full record: a project and its assessment, the
Acme Pay demo file, the tick, Verify, a dependency list and a tie, a change to the test plan, Run, Run all, Mark
reviewed and Dig deeper, the fix from Connect demo code to the merge, Retest now, a system setting, a developer's
change brought in and its picked tests run, and two downloads of the evidence file. (`migration_walk` is the migration
demo with its measurements, a choice and a change tried, approved, applied and rolled back: the slow set.)

It is made once for the run (a few seconds; the speed test plays back made-up timings) and shared by the test files of
this folder, which only read it. `old_walk` makes a second, shorter assessment the way it was made before names were
kept: through the same methods without their recording, so it has no row in `actions`."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from conftest import make_lab, play_back_speed

FIX = "fix-ecdsa-range-check"
DEMO = Path(__file__).resolve().parents[3] / "demo"
REVERT = "revert-range-check"
_MADE: dict = {}


def everything_kept(lab) -> dict:
    """A fingerprint of everything the app keeps: every row of every table, and every file of the data folder (the
    connected repositories, the Otto ledgers, the signing key)."""
    with lab.db() as db:
        tables = sorted(sa_inspect(db.get_bind()).get_table_names())
        rows = {
            t: hashlib.sha256(
                repr(sorted(map(repr, db.execute(text(f'select * from "{t}"')).fetchall()))).encode()
            ).hexdigest()
            for t in tables
        }
    files = {}
    for path in sorted(Path(lab.settings.data_dir).rglob("*")):
        if path.is_file() and not path.name.endswith(("-wal", "-shm", "-journal")) and path.suffix != ".db":
            files[str(path.relative_to(lab.settings.data_dir))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"rows": rows, "files": files}


def download(lab, plan_id: int) -> SimpleNamespace:
    made = lab.export_evidence(plan_id)
    _, raw, _ = lab.evidence_file(made["id"], "json")
    _, report, _ = lab.evidence_file(made["id"], "html")
    return SimpleNamespace(id=made["id"], raw=raw, evidence=json.loads(raw)["evidence"], report=report.decode())


def start(lab, name: str = "Record walk") -> SimpleNamespace:
    """A project with its first assessment, the demo file brought in and ticked, and the test plan without its slowest test."""
    play_back_speed(lab)
    made = lab.create_project(name, None)
    imp = lab.import_demo(assessment_id=made["assessment_id"])
    address = imp["addresses"][0]["address"]
    lab.confirm_address(imp["id"], address, True)
    plan = lab.ensure_plan(imp["id"])
    item = {t["kind"]: t["id"] for t in plan["tests"]}
    lab.remove_test(plan["id"], item["official_vectors"])
    return SimpleNamespace(
        lab=lab, assessment_id=made["assessment_id"], imp=imp, address=address, plan_id=plan["id"], item=item
    )


def walk(lab) -> SimpleNamespace:
    w = start(lab)
    pid = w.plan_id
    lab.verify(w.imp["id"])
    deps = lab.add_dependency_list(
        pid, "dependencies-demo.cdx.json", (DEMO / "dependencies-demo.cdx.json").read_bytes()
    )
    pay = next(g for g in deps["groups"] if g["label"] == "acme-pay-server 1.0.0")
    lab.tie_dependency(pid, pay["key"], f"server:{w.address}")
    kept = [w.item[k] for k in ("tls_versions", "certificate", "bad_signatures", "speed_size")]
    lab.reorder(pid, [kept[1], kept[0], kept[2], kept[3]])
    lab.run_test(pid, w.item["certificate"])
    lab.wait_until_idle(pid, 120)
    lab.run_all(pid)
    lab.wait_until_idle(pid, 120)
    first = {r["kind"]: r["result"]["run_id"] for r in lab.lab_view(pid)["rows"]}
    lab.mark_reviewed(first["bad_signatures"])
    lab.dig_deeper(first["tls_versions"])
    lab.connect_code(pid)
    lab.wait_until_idle(pid, 120)
    lab.open_pull_request(pid, FIX, ["you", "a"])
    lab.approve(pid, FIX, "you")
    lab.approve(pid, FIX, "a")
    lab.merge(pid, FIX)
    lab.retest_now(pid, FIX)
    lab.wait_until_idle(pid, 120)
    server = f"server:{w.address}"
    lab.set_migration_setting(pid, server, "exposure", "internal")  # (it also writes each system's measurement down)
    w.first_download = download(lab, pid)
    w.before_watch = {"timeline": lab.timeline_view(pid), "decisions": lab.decisions_view(pid)}
    lab.bring_in_demo_change(pid, REVERT)
    w.change = next(c for c in lab.change_watch_state(pid)["changes"] if c["branch"].endswith(REVERT))
    lab.run_picked_tests(pid, w.change["id"])
    lab.wait_until_idle(pid, 120)
    w.download = download(lab, pid)
    w.first, w.server = first, server
    w.read = lab.record_entries(pid)  # one reading of the finished walk, for the tests that ask many reads of it
    return w


def migration_walk(lab, ports: tuple) -> SimpleNamespace:
    """The migration demo file measured, one system's option chosen, and its change tried on a test copy, approved,
    applied and rolled back (the slow set: the measurements take a while)."""
    from app.servers import migration_servers

    play_back_speed(lab)
    imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
    for a in imp["addresses"]:
        lab.confirm_address(imp["id"], a["address"], True)
    plan_id = lab.ensure_plan(imp["id"])["id"]
    lab.migration_view(plan_id)  # opening Migration writes each system's measurement down (once), as the page does
    lab.measure_migration(plan_id)
    lab.wait_until_measured(plan_id, 300)
    address = f"localhost:{ports[1]}"  # c1: classical, internet-facing, long-lived
    system, key = f"server:{address}", f"migration:server:{address}"
    lab.choose_migration_option(plan_id, system, "hybrid", "Chosen in the walk.", None)
    lab.try_change(plan_id, key)
    lab.wait_until_changes_idle(plan_id)
    lab.ask_approval(plan_id, key, ["you", "a"])
    lab.approve_change(plan_id, key, "you")
    lab.approve_change(plan_id, key, "a")
    lab.apply_change(plan_id, key)
    lab.wait_until_changes_idle(plan_id)
    lab.rollback_change(plan_id, key)
    lab.wait_until_changes_idle(plan_id)
    lab.measure_migration(plan_id)  # (now the button reads Measure again)
    lab.wait_until_measured(plan_id, 300)
    return SimpleNamespace(lab=lab, imp=imp, plan_id=plan_id, address=address, system=system, key=key)


def shared(request, tmp_path_factory) -> SimpleNamespace:
    """The walk, made once for the run and stopped at its end. It takes a few seconds, so by the rule of
    tests/conftest.py the tests that read it are in the slow set (their fixture is named `walked`)."""
    if "walk" not in _MADE:
        lab = make_lab(tmp_path_factory.mktemp("record-walk"))
        request.config.add_cleanup(lab.stop)
        _MADE["walk"] = walk(lab)
    return _MADE["walk"]


def short_walk(lab) -> SimpleNamespace:
    """A short assessment for the everyday run: started, the file in and ticked, a test taken out, Verify, Run, Run all,
    Mark reviewed, and two downloads of the evidence file. Under two seconds."""
    w = start(lab, "Short walk")
    pid = w.plan_id
    lab.verify(w.imp["id"])
    lab.run_test(pid, w.item["certificate"])
    lab.wait_until_idle(pid, 120)
    lab.run_all(pid)
    lab.wait_until_idle(pid, 120)
    w.first = {r["kind"]: r["result"]["run_id"] for r in lab.lab_view(pid)["rows"]}
    lab.mark_reviewed(w.first["bad_signatures"])
    w.first_download = download(lab, pid)
    w.download = download(lab, pid)
    w.read = lab.record_entries(pid)
    return w


def shared_short(request, tmp_path_factory) -> SimpleNamespace:
    """The short walk, made once for the run and stopped at its end. The tests that read it change nothing in it."""
    if "short" not in _MADE:
        lab = make_lab(tmp_path_factory.mktemp("record-short-walk"))
        request.config.add_cleanup(lab.stop)
        _MADE["short"] = short_walk(lab)
    return _MADE["short"]


def before_names(lab, name: str, *args, **kwargs):
    """One of the Lab's own actions, as it was before names were kept: the method itself, without its recording."""
    return getattr(type(lab), name).__wrapped__(lab, *args, **kwargs)


def old_walk(lab, with_fix: bool = True) -> SimpleNamespace:
    """A short assessment with no row in `actions`: file in, tick, Verify, Run all, and (unless left out) the fix
    connected, proved, approved and merged."""
    play_back_speed(lab)
    imp = before_names(lab, "import_demo")
    address = imp["addresses"][0]["address"]
    before_names(lab, "confirm_address", imp["id"], address, True)
    plan = lab.ensure_plan(imp["id"])
    item = {t["kind"]: t["id"] for t in plan["tests"]}
    before_names(lab, "remove_test", plan["id"], item["official_vectors"])
    before_names(lab, "verify", imp["id"])
    before_names(lab, "run_all", plan["id"])
    lab.wait_until_idle(plan["id"], 120)
    if not with_fix:
        return SimpleNamespace(lab=lab, imp=imp, address=address, plan_id=plan["id"], item=item)
    before_names(lab, "connect_code", plan["id"])
    lab.wait_until_idle(plan["id"], 120)
    before_names(lab, "open_pull_request", plan["id"], FIX, ["you", "a"])
    before_names(lab, "approve", plan["id"], FIX, "you")
    before_names(lab, "approve", plan["id"], FIX, "a")
    before_names(lab, "merge", plan["id"], FIX)
    return SimpleNamespace(lab=lab, imp=imp, address=address, plan_id=plan["id"], item=item)
