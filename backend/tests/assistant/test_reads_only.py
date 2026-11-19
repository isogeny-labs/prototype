"""Phase 6a: the assistant is a faster way to press the same buttons, never a way around them.

Its own code reads, describes and keeps nothing: it decides, runs and changes nothing, and a read never asks Claude.
The first tests read the package's source, so they hold for every state the app can be in; the last ones watch a
real read on a walked assessment and compare everything the app keeps before and after."""
import ast
from pathlib import Path

import pytest

from app import assistant
from app.assistant.threads import PAGES
from app.otto import model

PACKAGE = Path(assistant.__file__).resolve().parent
# What the package may import. Nothing here decides, runs or writes: the tables and words of the panel, the errors, the
# words of a proposal as its page shows it, two constants and one pure rule of the proposals, and the harness's status.
ALLOWED_IMPORTS = {"__future__", "hashlib", "re", "typing", "app.assistant", "app.assistant.threads", "app.assistant.words", "app.errors",
                   "app.assistant.engine", "app.otto", "app.otto.proposals", "app.present"}
ALLOWED_NAMES = {"app.otto.proposals": {"CLOSED", "HOME", "accept_stands"}, "app.otto": {"harness"}, "app.present": {"otto"},
                 "app.assistant": {"words", "commands", "answers"}, "app.errors": {"BadRequest", "NotFound"}}
# Every method of the Lab the package may call. Each is a read the pages themselves make (their GET routes), or a
# read made for the panel; none starts a job, records a decision or writes a row.
READS = {"assessment_core", "otto_live_ready", "otto_proposals", "plan_view", "lab_view", "fixes_view", "migration_measure_view",
         "dependencies_view", "import_json_for", "latest_verify", "next_step_from", "decision_name_view", "otto_limit_words",
         # phase 6b: what was said (a read of the kept exchanges), and for a filtered table how many rows it lists
         "assistant_messages", "checks_view", "advisories_view"}
# What a page's button calls. None of these may appear anywhere in the package.
CHANGES = {"otto_decide", "otto_decide_view", "run_all", "run_test", "start_retest", "retest_now", "connect_code", "run_proof_again",
           "open_pull_request", "approve", "merge", "verify", "confirm_address", "measure_migration", "measure_dependencies", "try_change",
           "ask_approval", "approve_change", "apply_change", "rollback_change", "add_test", "remove_test", "reorder", "ensure_plan",
           "install_pack", "set_live_otto", "update_assessment", "export_evidence", "mark_reviewed", "dig_deeper", "add_dependency_list",
           "tie_dependency", "set_migration_setting", "choose_migration_option", "otto_model", "otto_record_step", "import_demo", "new_assessment"}
# (a set's own .add is fine: the package never holds a database session to add to, which the test below also checks)
WRITES = {"commit", "delete", "execute", "flush", "merge", "write", "write_text", "write_bytes", "unlink", "mkdir", "submit", "open",
          "record_decision", "record_step", "urlopen", "db", "jobs"}


def _trees():
    for path in sorted(PACKAGE.glob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_the_assistants_code_imports_nothing_that_decides_runs_or_changes():
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name in ALLOWED_IMPORTS, f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                assert node.module in ALLOWED_IMPORTS, f"{path.name} imports from {node.module}"
                wanted = ALLOWED_NAMES.get(node.module)
                if wanted is not None:
                    assert {a.name for a in node.names} <= wanted, f"{path.name} takes {[a.name for a in node.names]} from {node.module}"
    # (and so, like the rest of the app, it never imports the research side or Otto's Claude client)
    source = "\n".join(path.read_text(encoding="utf-8") for path, _ in _trees())
    assert "ottolab" not in source and "app.otto.model" not in source and "app.db" not in source and "app.jobs" not in source


def test_the_assistants_code_calls_only_reads_of_the_lab():
    called_on_lab = set()
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in CHANGES, f"{path.name}:{node.lineno} names {node.attr}, which changes an assessment"
                assert node.attr not in ("db", "jobs", "settings"), f"{path.name}:{node.lineno} reaches for .{node.attr}"
                # anything taken from the lab is a listed read, also when it is only named and called later
                of_lab = (isinstance(node.value, ast.Name) and node.value.id == "lab") or \
                         (isinstance(node.value, ast.Attribute) and node.value.attr == "_lab")
                assert not of_lab or node.attr in READS, f"{path.name}:{node.lineno} takes lab.{node.attr}, which is not a listed read"
            if isinstance(node, ast.Name):
                assert node.id not in ("db", "session"), f"{path.name}:{node.lineno} holds a database session"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                target = node.func.value
                on_lab = (isinstance(target, ast.Name) and target.id == "lab") or \
                         (isinstance(target, ast.Attribute) and target.attr == "_lab")
                if on_lab:
                    called_on_lab.add(node.func.attr)
                    assert node.func.attr in READS, f"{path.name}:{node.lineno} calls lab.{node.func.attr}, which is not a listed read"
                else:
                    assert node.func.attr not in WRITES, f"{path.name}:{node.lineno} calls .{node.func.attr}()"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("open", "exec", "eval", "__import__"), f"{path.name}:{node.lineno} calls {node.func.id}()"
    assert called_on_lab == READS            # the list above is exactly what is used: nothing stale, nothing unlisted


def test_every_listed_read_is_what_a_get_route_or_the_panel_itself_calls():
    from app.lab.hub import Lab
    for name in READS:
        assert callable(getattr(Lab, name)), name
    routes = "\n".join(p.read_text(encoding="utf-8") for p in (PACKAGE.parent / "web").glob("*.py"))
    # the reads the pages make are behind GET routes; the three made for the panel only read too (their own tests)
    for name in ("plan_view", "lab_view", "fixes_view"):
        assert f"lab.{name}(" in routes, name
    # The Migration page's own read is not among them: it writes each system's measurement down the first time it is
    # asked. The panel reads the Measure status button through a read of its own that writes nothing.
    assert "migration_view" not in READS and "migration_view_for_import" not in READS and "ensure_plan" not in READS


def _everything_kept(lab) -> dict:
    """A fingerprint of everything the app keeps for its assessments (tests/assistant/assistant_walk.py)."""
    from tests.assistant import assistant_walk as made
    return made.everything_kept(lab)


@pytest.mark.needs_otto
def test_a_read_writes_nothing_and_starts_nothing(assistant_walk):
    lab = assistant_walk.lab
    before = _everything_kept(lab)
    jobs_before = (len(lab.jobs.live(assistant_walk.plan_id)), lab.jobs.most_at_once)
    assert before["rows"] and any("otto" in name for name in before["files"])          # the ledger is among what is compared
    fix_id = next(f["id"] for f in lab.fixes_view(assistant_walk.plan_id)["fixes"])
    for page in PAGES:
        for item in (None, "test-1", fix_id, "CVE-2022-21449", "no-such-item"):
            lab.assistant_view(assistant_walk.assessment_id, page, item)
    lab.assistant_view(assistant_walk.empty_id, "overview")
    assert _everything_kept(lab) == before
    assert (len(lab.jobs.live(assistant_walk.plan_id)), lab.jobs.most_at_once) == jobs_before


def test_a_read_writes_nothing_in_an_assessment_whose_pages_nobody_has_opened_yet(tmp_path, monkeypatch):
    """The Migration page writes each system's measurement down the first time it is opened. The panel must not do
    that in its place: beside any page, before any page's own read, its read leaves everything as it was. And the
    button it offers is the page's: the same name, state and reason."""
    from tests.assistant import assistant_walk as made
    lab = made.start_lab(tmp_path, monkeypatch, record_prompts=False)
    try:
        before = _everything_kept(lab)
        offered = {}
        for page in PAGES:
            view = lab.assistant_view(lab.assessment_id, page)
            offered[page] = [e for e in view["on_page"]["entries"] if e["what"] == "next:measure_status"]
            assert _everything_kept(lab) == before, page
        step = offered["migration/systems"][0]
        on_the_page = lab.migration_view(lab.plan.id)["measure"]            # the page's own read (it writes the measurements down)
        assert _everything_kept(lab) != before
        assert (step["title"], step["step"]["can"], step["step"]["blocked_reason"]) == (on_the_page["label"], on_the_page["enabled"], None)
        assert lab.migration_measure_view(lab.plan.id)["measure"] == on_the_page
    finally:
        lab.stop()


def test_a_read_never_asks_claude_even_with_live_otto_on(tmp_path, monkeypatch):
    from tests.assistant import assistant_walk as made
    lab = made.start_lab(tmp_path, monkeypatch, record_prompts=False)
    try:
        asked = []
        monkeypatch.setenv(model.KEY_ENV, "test-key-not-a-real-one")
        monkeypatch.setattr(model, "_http_transport", lambda body, headers, timeout: asked.append(body) or (_ for _ in ()).throw(AssertionError("asked Claude")))
        lab.set_live_otto(on=True)
        before = _everything_kept(lab)
        for page in PAGES:
            view = lab.assistant_view(lab.assessment_id, page)
            assert view["status"] == {"text": "Live Otto is on.", "live": True, "link": None}
        assert asked == [] and _everything_kept(lab) == before
        # the key is in no sentence of the panel
        assert "test-key-not-a-real-one" not in repr([lab.assistant_view(lab.assessment_id, page) for page in PAGES])
    finally:
        lab.stop()
