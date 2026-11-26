"""Evidence as the full record only reads: it decides nothing, writes nothing and starts nothing.

The first tests read the package's source, so they hold for every state the app can be in. The others watch the five
reads on real assessments and compare everything the app keeps before and after."""

import ast
from pathlib import Path

import pytest
from sqlalchemy import func, select

import record_walk
from app import record
from app.db import ActionRow
from app.errors import Conflict
from app.lab import actions
from app.present import record as words
from record_walk import FIX, everything_kept

PACKAGE = Path(record.__file__).resolve().parent
WORDS = Path(words.__file__).resolve()
# Everything the package takes from the Lab. Each is a read: the pages' own views and the read gates behind them.
READS = {
    "db",  # a session it only selects from (the test below holds every call on one to that)
    "jobs",  # only to ask whether a proof is still running
    "ledger",
    "change_watch_state",
    "_blocks",
    "_plan",
    "_fix_details",
    "_migration_states",
    "_systems",
    "_claims",
    "_plan_changes",
    "_proof_review",
    "_proof_tests",
    "_watch_review",
    "_watch_tests",
}
# What the five views take from the Lab they are mixed into.
OF_SELF = {"db", "_plan", "lab_view", "_record_frame", "_record_choice", "_decision_row"}
# Nothing that writes, decides or runs may be imported: not the one writer of the actions table, not the job runner,
# not the reviewer, not the runner, not Otto's Claude client, not the research side.
FORBIDDEN = (
    "app.lab.actions",
    "app.jobs",
    "app.run",
    "app.engine.reviewer",
    "app.otto",
    "app.assistant",
    "ottolab",
    "subprocess",
    "urllib",
    "httpx",
    "socket",
)
WRITES = {
    "commit",
    "flush",
    "delete",
    "execute",
    "merge",
    "write",
    "write_text",
    "write_bytes",
    "unlink",
    "mkdir",
    "submit",
    "urlopen",
    "record_decision",
    "record_step",
}
# Every button of the app, and the two page reads that write the first time they are asked.
CHANGES = set(actions.PRESSES) | {
    "otto_decide",
    "otto_decide_view",
    "look_for_advisories",
    "start_research",
    "watch_list_mark",
    "watch_list_look",
    "install_pack",
    "set_live_otto",
    "set_decision_name",
    "assistant_say",
    "ensure_plan",
    "migration_view",
    "migration_view_for_import",
    "dependencies_view_for_import",
}


def _trees():
    for path in sorted(PACKAGE.glob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def _imports(tree) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(str(node.module))
    return found


def test_the_package_imports_nothing_that_writes_decides_or_runs():
    for path, tree in _trees():
        for name in _imports(tree):
            assert not any(name == bad or name.startswith(bad + ".") for bad in FORBIDDEN), (
                f"{path.name} imports {name}"
            )
    # every sentence is in the words module, and that module can read no record at all
    assert _imports(ast.parse(WORDS.read_text(encoding="utf-8"))) == {"__future__", "app.names"}


def test_the_package_takes_only_reads_from_the_lab_and_only_selects_from_the_database():
    taken, of_self = set(), set()
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in CHANGES, f"{path.name}:{node.lineno} names {node.attr}, which changes something"
                assert node.attr not in WRITES, f"{path.name}:{node.lineno} names .{node.attr}"
                value = node.value
                of_lab = (isinstance(value, ast.Name) and value.id == "lab") or (
                    isinstance(value, ast.Attribute)
                    and value.attr == "lab"
                    and isinstance(value.value, ast.Name)
                    and value.value.id in ("self", "r")
                )
                if of_lab:
                    taken.add(node.attr)
                    assert node.attr in READS, (
                        f"{path.name}:{node.lineno} takes lab.{node.attr}, which is not a listed read"
                    )
                if path.name == "views.py" and isinstance(value, ast.Name) and value.id == "self":
                    of_self.add(node.attr)
                if isinstance(value, ast.Attribute) and value.attr == "jobs":
                    assert node.attr == "live", f"{path.name}:{node.lineno} does more with the job runner than ask"
            if isinstance(node, ast.Call):
                func_ = node.func
                if isinstance(func_, ast.Attribute) and isinstance(func_.value, ast.Name) and func_.value.id == "db":
                    assert func_.attr in ("scalars", "scalar", "get"), (
                        f"{path.name}:{node.lineno} calls db.{func_.attr}()"
                    )
                if isinstance(func_, ast.Name):
                    assert func_.id not in ("open", "exec", "eval", "__import__"), f"{path.name}:{node.lineno}"
                    assert not func_.id.endswith("Row"), f"{path.name}:{node.lineno} makes a {func_.id}"
    assert taken == READS  # the list above is exactly what is used: nothing stale, nothing unlisted
    assert of_self == OF_SELF


@pytest.fixture
def walked(request, tmp_path_factory):
    return record_walk.shared(request, tmp_path_factory)


def _read_everything(lab, plan_id: int, keys: list[str]) -> None:
    lab.timeline_view(plan_id, area="watch", kind="runs", q="picked", tz="Europe/Paris")
    listed = [entry["id"] for day in lab.timeline_view(plan_id)["days"] for entry in day["entries"]]
    for entry_id in {
        next(i for i in listed if i.startswith(p))
        for p in ("start-", "import-", "merge-", "press-")
        if any(i.startswith(p) for i in listed)
    }:
        lab.timeline_entry_view(plan_id, entry_id)
    lab.decisions_view(plan_id)
    lab.decisions_view(plan_id, "fixes")
    lab.evidence_files_view(plan_id)
    for key in keys:
        lab.history_view(plan_id, key)


def test_the_five_reads_write_nothing_and_start_nothing(walked):
    lab, pid = walked.lab, walked.plan_id
    before = everything_kept(lab)
    jobs = (len(lab.jobs.live(pid)), lab.jobs.most_at_once)
    assert before["rows"] and any(
        "repos" in name for name in before["files"]
    )  # the connected repository is compared too
    _read_everything(
        lab,
        pid,
        [
            f"test:{walked.item['bad_signatures']}",
            f"claim:{walked.imp['claims'][0]['id']}",
            f"fix:{FIX}",
            f"system:{walked.server}",
            "advisory:CVE-2022-21449",
            "library:row-1",
            # asked by a row's own id: a claim's check, a library's row, a row of a proof's and of a watch run's block
            f"check:claim-{walked.imp['claims'][0]['id']}",
            "check:library-row-3",
            f"check:proof-{walked.item['bad_signatures']}-in-1",
            f"check:watch-{walked.item['bad_signatures']}-in-1",
        ],
    )
    assert everything_kept(lab) == before
    assert (len(lab.jobs.live(pid)), lab.jobs.most_at_once) == jobs


def test_reading_an_assessment_nobody_has_opened_a_page_of_writes_nothing(lab):
    """Opening Migration writes each system's measurement down, and locks it, the first time. The timeline and the
    histories must not do that in its place: before any page's own read they leave everything as it was."""
    w = record_walk.start(lab, "Unopened")
    before = everything_kept(lab)
    _read_everything(lab, w.plan_id, [f"test:{w.item['certificate']}", f"system:server:{w.address}"])
    assert everything_kept(lab) == before
    lab.migration_view(w.plan_id)  # the page's own read (it writes the measurements down)
    assert everything_kept(lab) != before
    assert lab.timeline_view(w.plan_id)["total"] == 4  # started, file in, the tick, the test taken out of the plan


def test_a_closed_assessment_is_read_as_before_and_takes_no_press(client):
    lab = client.app.state.lab
    made = client.post("/api/projects", json={"name": "Closing"}).json()
    aid = made["assessment_id"]
    imp = client.post("/api/import/demo", params={"assessment_id": aid}).json()
    address = imp["addresses"][0]["address"]
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": address, "confirmed": True})
    assert client.post(f"/api/import/{imp['id']}/verify").status_code == 200
    pid = client.post(f"/api/import/{imp['id']}/plan").json()["id"]
    closing = client.post(
        f"/api/assessments/{aid}", json={"close": True, "signed_off_by": "Kevin Bacon", "note": "Done."}
    )
    assert closing.status_code == 200
    with lab.db() as db:
        count = db.scalar(select(func.count(ActionRow.id)))
    # a changing request is refused, as it always was, and so nothing is recorded
    assert client.post(f"/api/plans/{pid}/run-all").status_code == 409
    assert client.post(f"/api/import/{imp['id']}/verify").status_code == 409
    with pytest.raises(Conflict):
        lab.refuse_if_closed(plan_id=pid)
    with lab.db() as db:
        assert db.scalar(select(func.count(ActionRow.id))) == count
    # the reads work on it as on an open one
    timeline = client.get(f"/api/plans/{pid}/timeline").json()
    newest = timeline["days"][0]["entries"][0]
    assert newest["lead"] == "Closed and signed off" and newest["who"]["name"] == "Kevin Bacon"
    assert newest["who"]["source"] == "signoff" and [p["name"] for p in newest["also"]] == ["You"]
    decisions = client.get(f"/api/plans/{pid}/decisions").json()
    signed = decisions["days"][0]["rows"][0]
    assert signed["decision"]["label"] == "Signed off" and signed["who"]["name"] == "Kevin Bacon"
    assert signed["pressed_by"]["name"] == "You" and signed["pressed_by"]["button"] == "Close and sign off"
    card = next(c for c in decisions["cards"] if c["key"] == "signoff")
    assert (card["value"], card["small"]) == ("Kevin Bacon", "who closed this assessment")
    story = client.get(f"/api/plans/{pid}/timeline/{newest['id']}").json()
    assert [(p["role"], p["who"]["name"]) for p in story["people"]] == [
        ("Signed off by", "Kevin Bacon"),
        ("Pressed by", "You"),
    ]
    # Download evidence is allowed on a closed assessment (it changes nothing in it), and that download is recorded
    assert client.post(f"/api/plans/{pid}/evidence").status_code == 200
    files = client.get(f"/api/plans/{pid}/evidence-files").json()
    assert [f["who"]["name"] for f in files["files"]] == ["You"]
