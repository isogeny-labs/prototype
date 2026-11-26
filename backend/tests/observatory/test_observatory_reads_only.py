"""The Observatory only reads. Its code decides, runs and changes nothing, and asking for the map, a box or a place
leaves everything the app keeps exactly as it was.

The first tests read the source of the package (and of its reader, its words and its routes), so they hold for every
state the app can be in. The last ones watch real reads and compare every row of every table and every file of the
data folder before and after, the way tests/assistant/test_reads_only.py does for the Otto panel."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app import observatory
from app.observatory import build
from tests.assistant.assistant_walk import everything_kept
from tests.conftest import make_lab
from tests.observatory import observatory_walk as W

APP = Path(observatory.__file__).resolve().parents[1]
PACKAGE = sorted((APP / "observatory").glob("*.py"))
AROUND = [APP / "importer" / "structure.py", APP / "present" / "observatory.py", APP / "web" / "observatory.py"]
# What the package may import: the files' readers, the rows it reads, the pages' own constants, and its own words.
ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "hashlib",
    "re",
    "typing",
    "sqlalchemy",
    "app.db",
    "app.dependencies.tree",
    "app.engine",
    "app.errors",
    "app.importer",
    "app.importer.common",
    "app.ledger.checks",
    "app.ledger.relations",
    "app.names",
    "app.observatory",
    "app.observatory.match",
    "app.present",
    "app.present.times",
}
ALLOWED_NAMES = {
    "sqlalchemy": {"select"},
    "app.db": {"DependencyListRow", "ImportFileRow", "ImportRow", "PlanRow", "iso"},
    "app.engine": {"research"},  # (only its lists of the servers and programs a file names)
    "app.ledger.checks": {"VERIFY_TONES"},
    "app.ledger.relations": {"migration_view_if_written"},
    "app.errors": {"NotFound"},
}
# Every method of the Lab the package calls. Each is a read a page itself makes; none starts a job or writes a row.
READS = {
    "db",
    "dependencies_view",
    "latest_verify",
    "lab_view",
    "checks_view",
    "ledger",
    "plan_view",
    "relation_graph",
    "related",
    "assessment_core",
}
# What a page's button calls, and what writes: none of these may be named anywhere in the package.
CHANGES = {
    "verify",
    "confirm_address",
    "ensure_plan",
    "run_all",
    "run_test",
    "start_retest",
    "retest_now",
    "measure_migration",
    "measure_dependencies",
    "migration_view",  # (the Migration page's own read writes each system's measurement down the first time)
    "migration_view_for_import",
    "add_dependency_list",
    "tie_dependency",
    "try_change",
    "apply_change",
    "rollback_change",
    "connect_code",
    "merge",
    "otto_decide",
    "otto_model",
    "import_demo",
    "import_file",
    "run_picked_tests",
    "export_evidence",
    "_submit",
    "_lock_spec",
    "_ensure_migration_items",
    "_store",
}
WRITES = {"add", "add_all", "commit", "delete", "execute", "flush", "merge", "write_text", "write_bytes", "unlink"}


def _trees(paths):
    for path in paths:
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_the_package_imports_nothing_that_decides_runs_or_changes():
    for path, tree in _trees(PACKAGE):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name in ALLOWED_IMPORTS, f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                assert node.module in ALLOWED_IMPORTS, f"{path.name} imports from {node.module}"
                wanted = ALLOWED_NAMES.get(str(node.module))
                if wanted is not None:
                    assert {a.name for a in node.names} <= wanted, f"{path.name} takes more from {node.module}"
    source = "\n".join(path.read_text(encoding="utf-8") for path in [*PACKAGE, *AROUND])
    for never in (
        "reviewer",
        "app.run",
        "app.jobs",
        "app.otto",
        "ottolab",
        "subprocess",
        "socket",
        "urllib",
        "anthropic",
    ):
        assert never not in source, never


def test_the_package_calls_only_reads_of_the_lab_and_only_reads_the_database():
    called = set()
    for path, tree in _trees(PACKAGE):
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in CHANGES, f"{path.name}:{node.lineno} names {node.attr}"
                if isinstance(node.value, ast.Name) and node.value.id == "lab" and node.attr != "__dict__":
                    called.add(node.attr)
                    assert node.attr in READS, f"{path.name}:{node.lineno} takes lab.{node.attr}, not a listed read"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                # the one module that holds a database session only gets and selects with it (a set's own .add, in the
                # layout, is no write: that module never sees a session)
                if path.name == "build.py":
                    assert node.func.attr not in WRITES, f"{path.name}:{node.lineno} calls .{node.func.attr}()"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("open", "exec", "eval", "compile", "__import__"), (
                    f"{path.name}:{node.lineno}"
                )
            if isinstance(node, ast.Name) and path.name != "build.py":
                assert node.id not in ("db", "session", "lab"), f"{path.name}:{node.lineno} holds {node.id}"
    assert called == READS  # the list above is exactly what is used: nothing stale, nothing unlisted


def test_the_reader_the_words_and_the_routes_run_nothing_and_the_routes_only_answer_get():
    for path, tree in _trees(AROUND):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("open", "exec", "eval", "compile", "__import__"), (
                    f"{path.name}:{node.lineno}"
                )
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [str(getattr(node, "module", ""))]
                assert not {"os", "subprocess", "importlib", "pathlib", "socket"} & set(names), f"{path.name} {names}"
    routes = (APP / "web" / "observatory.py").read_text(encoding="utf-8")
    assert routes.count("@router.get(") == 4 and "@router.post" not in routes and "@router.put" not in routes


@pytest.fixture
def lab(tmp_path):
    lab = make_lab(tmp_path)
    yield lab
    lab.stop()


def _ask_everything(lab, plan) -> dict:
    view = build.view_of_plan(lab, plan.id)
    assessment = lab.assessment_for(plan_id=plan.id)
    assert build.view_of_assessment(lab, assessment.id) == view
    for box in W.boxes(view):
        build.panel_of_plan(lab, plan.id, box["key"])
    for key in ("claim:1", "test:1", "system:" + plan.server, "library:row-1", "fix:x", "nothing"):
        build.place_of_plan(lab, plan.id, key)
    return view


def test_reading_the_map_writes_nothing_and_starts_nothing_before_any_page_was_opened(lab):
    """The Migration page writes each system's measurement down the first time it is opened. The map must not do that
    in its place: asked before any page, it leaves everything as it was, and says the status is not measured yet."""
    plan = W.start(lab)
    before = everything_kept(lab)
    assert before["rows"]
    jobs = (len(lab.jobs.live(plan.id)), lab.jobs.most_at_once)
    view = _ask_everything(lab, plan)
    assert everything_kept(lab) == before
    assert (len(lab.jobs.live(plan.id)), lab.jobs.most_at_once) == jobs
    statuses = [c for c in W.checks(view) if c["kind"] == "status"]
    assert len(statuses) == 3 and all(c["word"] == "Not measured yet" and not c["checked"] for c in statuses)
    # the page's own read is what writes them down; the map then reads them, and still writes nothing itself
    lab.migration_view(plan.id)
    opened = everything_kept(lab)
    assert opened != before
    _ask_everything(lab, plan)
    assert everything_kept(lab) == opened


def test_reading_the_map_writes_nothing_after_verify_and_with_a_dependency_list_and_reads_the_same_twice(lab):
    plan = W.start(lab)
    W.add_list(lab, plan)
    lab.verify(plan.imp["id"])
    lab.tie_dependency(plan.id, "acme-pay-server", plan.server)
    before = everything_kept(lab)
    first = _ask_everything(lab, plan)
    again = _ask_everything(lab, plan)
    assert everything_kept(lab) == before and not lab.jobs.live(plan.id)
    assert first == again  # worked out from the records each time: nothing is kept between two reads but the file read
    assert [key[0] for key in lab.__dict__["_observatory_structures"]] == [plan.imp["id"]]  # (the file, read once)


def test_a_closed_assessment_is_still_read_and_nothing_in_it_changes(lab):
    plan = W.start(lab)
    lab.verify(plan.imp["id"])
    assessment = lab.assessment_for(plan_id=plan.id)
    lab.update_assessment(assessment.id, {"close": True, "signed_off_by": "A reviewer"})
    before = everything_kept(lab)
    view = _ask_everything(lab, plan)
    assert view["state"] == "checked" and everything_kept(lab) == before
