"""Helpers for the Sandbox research tests (prototype, 22 November 2026).

The switch can be on only on a marked computer, in isolated mode, with Otto installed. A fast test has no Docker, so it
stands in for the two outside conditions (the mode and the harness) and leaves the switch's own rules as they are."""
from __future__ import annotations

from conftest import make_lab

from app.otto import harness, model
from app.run import runner

ISOLATED = runner.ModeInfo("isolated", "Isolated mode (stand-in for a test).", None, True, "stand-in", "stand-in")


def sandbox_lab(tmp_path, monkeypatch, *, marked: bool = True, isolated: bool = True, otto: bool = True, key: bool = False, **overrides):
    """A started lab on a computer that is (or is not) marked as the sandbox. The mode and the harness are stand-ins;
    `key` stands in for an API key being present (Live Otto still has to be switched on)."""
    lab = make_lab(tmp_path, sandbox_research=marked, **overrides)
    if isolated:
        monkeypatch.setattr(lab, "mode", ISOLATED)
    status = dict(harness.public_status())
    status["installed"] = otto
    monkeypatch.setattr(harness, "public_status", lambda: status)
    monkeypatch.setattr(model, "key_present", lambda env=None: key)
    return lab


def turn_on(lab, by_itself: bool = False) -> dict:
    view = lab.set_sandbox(on=True)
    if by_itself:
        lab.set_live_otto(on=True)
        view = lab.set_sandbox(by_itself=True)
    return view
