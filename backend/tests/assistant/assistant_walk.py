"""Phase 6a: one walk of a demo-mode Lab for the Otto panel's tests, read at each of its stages (not a conftest: a
second file of that name would hide tests/conftest.py from the helpers here).

The walk goes down the same path as the buttons (a test pack made for the test, the Acme Pay demo file, decisions,
Run all, a change written for the test, Measure status, the demo dependency list, a sign-off). At each stage every
page's read of the panel is kept, with the Overview's "Waiting for you" count. The tests then read those: the walk
itself runs once for the folder, in a few seconds (the speed test plays back made-up timings)."""
import json
from types import SimpleNamespace

import pytest

from app.assistant.threads import PAGES
from app.otto import model
from conftest import demo_plan, play_back_speed
from tests.otto import otto_helpers as helpers

# A change for acme-sign 1.4.2 that gives exactly our registered 1.4.3, in the shape Otto asks for. Written for the
# tests: it is a fixture, not an answer from Claude.
CHANGE = {"title": "Reject signatures whose r or s is out of range",
          "summary": "The verify command now refuses a signature whose two numbers are zero or not below the curve order.",
          "answers": [1, 2, 3],
          "edits": [{"file": "acme_sign.py", "title": "The range check", "why": "r and s must each be at least 1 and below n.",
                     "find": ["    except ValueError:", '        return {"valid": False}', "    e = digest_int(message)"],
                     "put": ["    except ValueError:", '        return {"valid": False}', "    if not (1 <= r < N and 1 <= s < N):",
                             '        return {"valid": False}', "    e = digest_int(message)"]},
                    {"file": "acme_sign.py", "title": "The version number", "why": "So the changed program can be told from the one before.",
                     "find": ['VERSION = "1.4.2"'], "put": ['VERSION = "1.4.3"']}]}
REASON = "Not this quarter"
STAGES = ("proposed", "decided", "ran", "measured", "accepted", "closed")


def pack_files() -> tuple[dict[str, bytes], list[str]]:
    """One pack: two advisories about the demo's own program with a test each, one about a library of the demo
    dependency list (its fix is its publisher's fixed version), and one with no test yet."""
    first, public = helpers.make_pack("2026.11.1", None, [
        helpers.pack_advisory(),
        helpers.pack_advisory("CVE-2024-42460", "Missing leading zero accepted", flags=("MissingZero",)),
        helpers.pack_advisory("CVE-2019-14859", "Malformed signature accepted", package="python-ecdsa", flags=("BerEncodedSignature",),
                              versions=("0.13.2", "0.13.3")),
        helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", state="none")])
    return {"2026.11.1.json": first}, [public]


def start_lab(tmp_path, monkeypatch, record_prompts: bool = True):
    """A started demo-mode Lab with the pack installed and the Acme Pay demo file in, its claims verified."""
    monkeypatch.delenv(model.KEY_ENV, raising=False)
    files, keys = pack_files()
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, files, keys)
    lab.prompts = []
    if record_prompts:
        real = model.OttoModel.recorded

        def recorded(self, step, prompt):
            lab.prompts.append((step, prompt))
            return real(self, step, prompt)
        monkeypatch.setattr(model.OttoModel, "recorded", recorded)
    lab.plan = demo_plan(lab)
    lab.verify(lab.plan.imp["id"])
    lab.check_pack_updates()
    lab.install_pack("2026.11.1")
    lab.assessment_id = lab.assessment_for(plan_id=lab.plan.id).id
    return lab


def record_change(lab) -> None:
    """Record the change above for exactly the prompt Otto asks for this assessment."""
    lab.fix_states(lab.plan.id)
    step, prompt = lab.prompts[-1]
    assert step == "write_fix"
    model.write_recorded(lab.settings.otto_recorded, "write_fix", prompt, json.dumps(CHANGE, indent=1), "2026-11-17T12:00:00Z",
                         "Written for a test, not an answer from Claude")


def proposals(lab, kind: str) -> list[dict]:
    return lab.otto_proposals(lab.plan.id, (kind,))


def snapshot(lab, item: str | None = None) -> SimpleNamespace:
    """Every page's read of the panel as it stands now, and what the Overview counts as waiting."""
    overview = lab.assessment_view(lab.assessment_id)
    return SimpleNamespace(pages={page: lab.assistant_view(lab.assessment_id, page, item) for page in PAGES},
                           waiting=overview["waiting"]["total"], overview=overview)


def make_walk(tmp_path_factory) -> tuple[SimpleNamespace, object, pytest.MonkeyPatch]:
    """The walk, read at each stage: `walk.at[stage]` (see STAGES), and `walk.lab` as it stands at the end (closed).
    Returns the walk, its Lab and the patches to undo (tests/conftest.py holds the fixture, `assistant_walk`)."""
    from app.accuracy_otto import DEPENDENCIES_FILE
    monkeypatch = pytest.MonkeyPatch()
    tmp_path = tmp_path_factory.mktemp("assistant-walk")
    lab = start_lab(tmp_path, monkeypatch)
    pid = lab.plan.id
    at: dict[str, SimpleNamespace] = {}
    ids: dict[str, str] = {}
    try:
        # a second assessment of the same project with no file in it yet
        project_id = lab.assessment_for(plan_id=pid).project_id
        empty = lab.new_assessment(project_id)
        at["empty"] = SimpleNamespace(pages={page: lab.assistant_view(empty["id"], page) for page in PAGES}, waiting=0, overview=None)

        at["proposed"] = snapshot(lab)
        first, second = [p["id"] for p in proposals(lab, "check")][:2]
        ids.update(first=first, second=second)
        lab.otto_decide(pid, first, "accept")
        lab.otto_decide(pid, second, "reject", REASON)
        at["decided"] = snapshot(lab)

        play_back_speed(lab)
        lab.run_all(pid)
        lab.wait_until_idle(pid, 300)
        record_change(lab)
        ids["fix"] = proposals(lab, "fix")[0]["id"]
        at["ran"] = snapshot(lab)

        lab.measure_migration(pid)
        lab.wait_until_measured(pid, 300)
        lab.add_dependency_list(pid, DEPENDENCIES_FILE.name, DEPENDENCIES_FILE.read_bytes())
        ids["plan"] = proposals(lab, "plan")[0]["id"]
        ids["dependency"] = proposals(lab, "dependency")[0]["id"]
        at["measured"] = snapshot(lab)

        for kind in ("fix", "plan", "dependency"):
            lab.otto_decide(pid, ids[kind], "accept")
        at["fix_accepted"] = SimpleNamespace(pages={"fixes": lab.assistant_view(lab.assessment_id, "fixes")}, waiting=1, overview=None)
        # (the third proposed check, which nobody had decided so far: accepted now, and not run, so it can be undone)
        ids["third"] = next(p["id"] for p in proposals(lab, "check") if p["state"] == "proposed")
        lab.otto_decide(pid, ids["third"], "accept")
        at["accepted"] = snapshot(lab)

        lab.update_assessment(lab.assessment_id, {"close": True, "signed_off_by": "A tester"})
        at["closed"] = snapshot(lab)
    except BaseException:
        lab.stop()
        monkeypatch.undo()
        raise
    return SimpleNamespace(lab=lab, at=at, ids=ids, plan_id=pid, assessment_id=lab.assessment_id, empty_id=empty["id"]), lab, monkeypatch
