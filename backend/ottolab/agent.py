"""The agent command of Otto's research loop:  python -m ottolab.agent

Adam's loop starts this command for every step that needs judgement, with a role prompt on standard input and the
lab folder as the working directory. The prompt is read as DATA: only its "Action:" and "Target id:" lines are used,
and the target is looked up in the ledger itself. What the step then does is in ottolab/research.py; where it needs
judgement it asks Claude (the recorded answer for exactly that prompt, or a live call when the build command was
given --live and a key is present).

A step that has nothing it can honestly add leaves the ledger unchanged; the loop marks it as impeded.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from app.otto.model import ModelError
from ottolab import research, snapshot

_ACTION = re.compile(r"^Action: ([a-z_]+)$", re.M)
_TARGET = re.compile(r"^Target id: (sha256:[0-9a-f]{64})$", re.M)


def main() -> int:
    prompt = sys.stdin.read()
    action, target = _ACTION.search(prompt), _TARGET.search(prompt)
    if action is None or target is None:
        print("The step could not be read from the prompt; nothing was added.")
        return 0
    try:
        lab = research.open_lab(Path.cwd())
        snap = snapshot.read_snapshot(Path(os.environ[research.ENV_SNAPSHOT]))
        model = research.env_model()
        try:
            print(research.act(lab, model, snap, action.group(1), target.group(1)))
        finally:
            research.save_spent(model)
    except (research.ResearchError, snapshot.SnapshotError, ModelError, KeyError) as exc:
        print(f"The step stopped: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
