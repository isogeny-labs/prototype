"""Phase 6a: one walk of a demo-mode Lab for the Otto panel's tests, read at each of its stages (not a conftest: a
second file of that name would hide tests/conftest.py from the helpers here).

The walk goes down the same path as the buttons (a test pack made for the test, the Acme Pay demo file, decisions,
Run all, a change written for the test, Measure status, the demo dependency list, a sign-off). At each stage every
page's read of the panel is kept, with the Overview's "Waiting for you" count. The tests then read those: the walk
itself runs once for the folder, in a few seconds (the speed test plays back made-up timings)."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy import inspect as sa_inspect

from app.assistant.threads import PAGES
from app.otto import model
from conftest import demo_plan, play_back_speed
from tests.otto import otto_helpers as helpers

# A change for acme-sign 1.4.2 that gives exactly our registered 1.4.3, in the shape Otto asks for. Written for the
# tests: it is a fixture, not an answer from Claude.
CHANGE = {
    "title": "Reject signatures whose r or s is out of range",
    "summary": "The verify command now refuses a signature whose two numbers are zero or not below the curve order.",
    "answers": [1, 2, 3],
    "edits": [
        {
            "file": "acme_sign.py",
            "title": "The range check",
            "why": "r and s must each be at least 1 and below n.",
            "find": ["    except ValueError:", '        return {"valid": False}', "    e = digest_int(message)"],
            "put": [
                "    except ValueError:",
                '        return {"valid": False}',
                "    if not (1 <= r < N and 1 <= s < N):",
                '        return {"valid": False}',
                "    e = digest_int(message)",
            ],
        },
        {
            "file": "acme_sign.py",
            "title": "The version number",
            "why": "So the changed program can be told from the one before.",
            "find": ['VERSION = "1.4.2"'],
            "put": ['VERSION = "1.4.3"'],
        },
    ],
}
REASON = "Not this quarter"
STAGES = ("proposed", "decided", "ran", "measured", "accepted", "closed")
# Phase 6b: what a person might type, asked at each stage of the walk, beside the page named. Asking is a read.
# (after the review of 6b) A plan change's title holds the word "fix", which elsewhere says which kind of suggestion is
# meant. Said whole, the title is that plan change.
PLAN_CHANGE = "Fix acme-sign 1.4.2 before its signatures move to post-quantum"
LONG_REJECT = "reject the blank signature check: " + "x" * 301
ASKED: dict[str, tuple[tuple[str, str], ...]] = {
    "empty": (
        ("overview", "what can you do?"),
        ("overview", "run all"),
        ("overview", "open checks"),
        ("overview", "accept the first suggestion"),
        # phase 6c: the fixed questions, before a file is in
        ("overview", "what should i do next?"),
        ("inventory/import", "what is this page for?"),
        ("checks", "why did this check fail?"),
        ("overview", "open import"),
        ("overview", "open settings"),
    ),
    "proposed": (
        ("checks", "show me failed checks"),
        ("checks", "accept the first suggestion"),
        ("checks", "accept the check"),
        ("checks", "reject the second suggestion: not this quarter"),
        ("checks", "run all"),
        ("checks", "what can you do?"),
        ("checks", "undo the first suggestion"),
        ("overview", "open evidence"),
        ("checks", "make me a sandwich"),
        ("checks", "accept the blank signature check"),
        ("checks", "run the speed test"),
        ("checks", "accept the fifth suggestion"),
        ("checks", "open the blank signature check"),
        ("advisories", "show proposed checks"),
        ("checks", "retest on 1.4.3"),
        ("inventory/import", "verify claims"),
        ("checks", "close the planning tab"),
        ("checks", "close the testing tab"),
        ("checks", "accept 21449"),
        ("overview", "accept the blank signature check"),
        # phase 6c
        ("checks", "where did this suggestion come from?"),
        ("checks", "where did the blank signature check come from?"),
        ("checks", "what happens if i accept the blank signature check?"),
        ("checks", "what is this page for?"),
        ("overview", "what is evidence for?"),
        ("overview", "what should i do next?"),
        ("checks", "why did this check fail?"),
        ("checks", "what is the moon for?"),
        # after the review of 6b: a button offered for none of what fits; a reason that is too long
        ("checks", "undo the check"),
        ("checks", LONG_REJECT),
    ),
    "ran": (
        ("checks", "show me failed checks"),
        ("evidence", "show failed results"),
        ("checks", "show the checks that passed"),
        ("evidence", "retest on 1.4.3"),
        ("evidence", "retest"),
        ("fixes", "connect demo code"),
        ("fixes", "accept the fix"),
        ("fixes", "merge it"),
        ("fixes", "approve the pull request"),
        ("checks", "run all"),
        ("checks", "show retests"),
        # phase 6c
        ("evidence", "why did this check fail?"),
        ("evidence", "why did the blank signature check fail?"),
        ("evidence", "what does the blank signature check show, and what doesn't it?"),
        ("evidence", "why did the speed test fail?"),
        ("checks", "what is this page for?"),
        ("evidence", "what is this page for?"),
        ("overview", "what should i do next?"),
        ("fixes", "where did this suggestion come from?"),
        ("fixes", "what happens if i accept this?"),
    ),
    "measured": (
        ("migration/systems", "accept " + PLAN_CHANGE),
        ("overview", "open " + PLAN_CHANGE),
        ("overview", "where did " + PLAN_CHANGE + " come from?"),
        ("migration/dependencies", "accept the python fix"),
        ("migration/dependencies", "reject the python fix: we stay on 0.13.2 until January"),
        ("overview", "accept the python fix"),
        ("fixes", "accept the fix"),
        ("migration/systems", "accept the plan change"),
        ("migration/dependencies", "measure all"),
        ("migration/systems", "measure status"),
        ("migration/roadmap", "measure status"),
        ("migration/dependencies", "open the python fix"),
        ("migration/dependencies", "undo the python fix"),
        ("migration/dependencies", "close the fixing tab"),
        ("fixes", "apply"),
        ("migration/systems", "choose the hybrid option"),
        ("overview", "close and sign off"),
        ("evidence", "download evidence"),
        ("evidence", "mark it reviewed"),
        ("overview", "turn on live otto"),
        ("inventory/import", "i own this system"),
    ),
    "accepted": (
        ("migration/dependencies", "undo the python fix"),
        ("migration/dependencies", "accept the python fix"),
        ("fixes", "connect demo code"),
        ("checks", "undo the first suggestion"),
    ),
    "closed": (
        ("fixes", "approve it"),
        ("fixes", "apply"),
        ("migration/dependencies", "accept the python fix"),
        ("checks", "show me failed checks"),
        ("checks", "what can you do?"),
        ("checks", "run all"),
        ("fixes", "merge it"),
        ("overview", "open evidence"),
        # phase 6c: a closed assessment still answers the fixed questions
        ("evidence", "why did the blank signature check fail?"),
        ("overview", "what should i do next?"),
    ),
}


def pack_files() -> tuple[dict[str, bytes], list[str]]:
    """One pack: two advisories about the demo's own program with a test each, one about a library of the demo
    dependency list (its fix is its publisher's fixed version), and one with no test yet."""
    first, public = helpers.make_pack(
        "2026.11.1",
        None,
        [
            helpers.pack_advisory(),
            helpers.pack_advisory("CVE-2024-42460", "Missing leading zero accepted", flags=("MissingZero",)),
            helpers.pack_advisory(
                "CVE-2019-14859",
                "Malformed signature accepted",
                package="python-ecdsa",
                flags=("BerEncodedSignature",),
                versions=("0.13.2", "0.13.3"),
            ),
            helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", state="none"),
        ],
    )
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
    model.write_recorded(
        lab.settings.otto_recorded,
        "write_fix",
        prompt,
        json.dumps(CHANGE, indent=1),
        "2026-11-17T12:00:00Z",
        "Written for a test, not an answer from Claude",
    )


def proposals(lab, kind: str) -> list[dict]:
    return lab.otto_proposals(lab.plan.id, (kind,))


def everything_kept(lab) -> dict:
    """A fingerprint of everything the app keeps for its assessments: every row of every table, and every file of the
    data folder with its content (the Otto ledgers, the connected repositories, the evidence downloads)."""
    with lab.db() as db:
        tables = sorted(sa_inspect(db.get_bind()).get_table_names())  # every table, on SQLite or PostgreSQL
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


def ask(lab, assessment_id: int, stage: str) -> SimpleNamespace:
    """Phase 6b: the answers to this stage's sentences, and whether asking left everything the app keeps as it was
    (with the jobs that run). A read, like the panel's own."""
    before, jobs = everything_kept(lab), len(lab.jobs.live(lab.plan.id))
    answers = {
        (page, said): lab.assistant_answer(assessment_id, page, None, said) for page, said in ASKED.get(stage, ())
    }
    # every option of every "Which one?" is said too, as a click on it would: an option must never ask again
    for (page, _said), reply in list(answers.items()):
        for option in reply.get("options") or []:
            if (page, option["say"]) not in answers:
                answers[(page, option["say"])] = lab.assistant_answer(assessment_id, page, None, option["say"])
    return SimpleNamespace(
        answers=answers, unchanged=everything_kept(lab) == before and len(lab.jobs.live(lab.plan.id)) == jobs
    )


def snapshot(lab, item: str | None = None, stage: str | None = None) -> SimpleNamespace:
    """Every page's read of the panel as it stands now, what the Overview counts as waiting, and (phase 6b) the answers
    to that stage's typed sentences."""
    overview = lab.assessment_view(lab.assessment_id)
    said = ask(lab, lab.assessment_id, stage) if stage else SimpleNamespace(answers={}, unchanged=True)
    return SimpleNamespace(
        pages={page: lab.assistant_view(lab.assessment_id, page, item) for page in PAGES},
        waiting=overview["waiting"]["total"],
        overview=overview,
        said=said.answers,
        asking_changed_nothing=said.unchanged,
    )


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
        asked_empty = ask(lab, empty["id"], "empty")
        at["empty"] = SimpleNamespace(
            pages={page: lab.assistant_view(empty["id"], page) for page in PAGES},
            waiting=0,
            overview=None,
            said=asked_empty.answers,
            asking_changed_nothing=asked_empty.unchanged,
        )

        at["proposed"] = snapshot(lab, stage="proposed")
        first, second = [p["id"] for p in proposals(lab, "check")][:2]
        ids.update(first=first, second=second)
        lab.otto_decide(pid, first, "accept")
        lab.otto_decide(pid, second, "reject", REASON)
        at["decided"] = snapshot(lab, stage="decided")

        play_back_speed(lab)
        lab.run_all(pid)
        lab.wait_until_idle(pid, 300)
        record_change(lab)
        ids["fix"] = proposals(lab, "fix")[0]["id"]
        at["ran"] = snapshot(lab, stage="ran")

        lab.measure_migration(pid)
        lab.wait_until_measured(pid, 300)
        lab.add_dependency_list(pid, DEPENDENCIES_FILE.name, DEPENDENCIES_FILE.read_bytes())
        ids["plan"] = proposals(lab, "plan")[0]["id"]
        ids["dependency"] = proposals(lab, "dependency")[0]["id"]
        at["measured"] = snapshot(lab, stage="measured")

        for kind in ("fix", "plan", "dependency"):
            lab.otto_decide(pid, ids[kind], "accept")
        at["fix_accepted"] = SimpleNamespace(
            pages={"fixes": lab.assistant_view(lab.assessment_id, "fixes")}, waiting=1, overview=None
        )
        # (the third proposed check, which nobody had decided so far: accepted now, and not run, so it can be undone)
        ids["third"] = next(p["id"] for p in proposals(lab, "check") if p["state"] == "proposed")
        lab.otto_decide(pid, ids["third"], "accept")
        at["accepted"] = snapshot(lab, stage="accepted")

        # Phase 6b: three sentences are sent the way the open text box sends them, so they are kept with the assessment.
        # Phase 6c: and one of the fixed questions, kept with the facts of its answer.
        kept_before = everything_kept(lab)
        sent = [
            (page, said, lab.assistant_say(pid, page, None, said))
            for page, said in (
                ("checks", "show me failed checks"),
                ("migration/dependencies", "undo the python fix"),
                ("checks", "make me a sandwich"),
                ("evidence", "why did the blank signature check fail?"),
            )
        ]
        kept_after = everything_kept(lab)
        at["said"] = snapshot(lab)
        at["said"].sent = sent
        at["said"].changed_tables = sorted(
            t for t in kept_after["rows"] if kept_after["rows"][t] != kept_before["rows"].get(t)
        )
        at["said"].changed_files = sorted(
            f
            for f in set(kept_after["files"]) | set(kept_before["files"])
            if kept_after["files"].get(f) != kept_before["files"].get(f)
        )

        lab.update_assessment(lab.assessment_id, {"close": True, "signed_off_by": "A tester"})
        at["closed"] = snapshot(lab, stage="closed")
    except BaseException:
        lab.stop()
        monkeypatch.undo()
        raise
    return (
        SimpleNamespace(lab=lab, at=at, ids=ids, plan_id=pid, assessment_id=lab.assessment_id, empty_id=empty["id"]),
        lab,
        monkeypatch,
    )
