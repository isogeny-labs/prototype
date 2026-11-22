"""The agent command of a sandbox research run:  python -m ottolab.sandbox_agent

The same command as `ottolab.agent` (which is not changed), for a run started with --sandbox: a step about an advisory
whose library has no pinned public copy takes the sandbox path (ottolab/sandbox.py); every other step is passed to
the research steps as they always were. The prompt is read as DATA: only its "Action:" and "Target id:" lines are used.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from app.otto import harness
from app.otto.model import ModelError
from ottolab import research, sandbox, snapshot

_ACTION = re.compile(r"^Action: ([a-z_]+)$", re.M)
_TARGET = re.compile(r"^Target id: (sha256:[0-9a-f]{64})$", re.M)


def act(lab, model, snap: dict, action: str, target: str) -> str:
    st = lab.state()
    record = st.get(target)
    if action == "propose":
        about = research.question_about(record)
        if about is None:
            return "This question is not one of the research side's; nothing was added."
        advisory = snapshot.advisory_of(snap, about[0])
        if not sandbox.wanted(lab, advisory):
            return research.act(lab, model, snap, action, target)
        lines, before = [], None
        while before != lab.ledger.head()["head"]:        # one step after another; each needs the checker's verdict on the one before
            before = lab.ledger.head()["head"]
            lines.append(sandbox.propose_test(lab, model, target, advisory, snap) if about[1] == "test"
                         else sandbox.propose_fix(lab, model, target, advisory))
            for cid, _ in research.step_claims(lab.state(), about[0]):
                if not lab.state().settled(cid):
                    lab.verify(cid)          # the harness's own verify step: it runs the pinned checker
        return " ".join(dict.fromkeys(lines))
    if action == "distill":
        decision = st.get(target, "decision")
        hyp = st.get(decision["hypothesis_id"], "hypothesis")
        return sandbox.distill(lab, target) if sandbox.is_sandbox_trial(hyp) else research.distill(lab, target)
    return research.act(lab, model, snap, action, target)


def main() -> int:
    prompt = sys.stdin.read()
    action, target = _ACTION.search(prompt), _TARGET.search(prompt)
    if action is None or target is None:
        print("The step could not be read from the prompt; nothing was added.")
        return 0
    try:
        lab = sandbox.open_lab(Path.cwd())
        snap = snapshot.read_snapshot(Path(os.environ[research.ENV_SNAPSHOT]))
        model = research.env_model()
        try:
            print(act(lab, model, snap, action.group(1), target.group(1)))
        finally:
            research.save_spent(model)
    except (research.ResearchError, snapshot.SnapshotError, ModelError, KeyError, harness.module("lab").LabError) as exc:
        # (also when the harness itself refuses a record: a stop that is said, never a crash that is taken for something)
        print(f"The step stopped: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
