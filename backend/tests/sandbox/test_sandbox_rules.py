"""Sandbox research: the lines that may not move. They are read from the code itself, so they hold whoever changes it.

  - the separate reviewer is the file it was (cheating drill 14);
  - a design with no case that must be refused is refused before it is tried (cheating drill 8);
  - the app never imports the research side, and never the part that fetches, unpacks and builds;
  - a registry is reached from the research command only;
  - the asking code a pack carries is never imported or run by anything but a container.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from app.config import REPO_ROOT
from ottolab import prompts
from tools import record_sandbox_answers as demo

BACKEND = REPO_ROOT / "backend"
REVIEWER_SHA256 = "9c5b5811a547e3aa16349cad10ce64dea64d8591eead432e675217d3156e613b"       # backend/app/engine/reviewer.py, as it was before this work


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{a.name}" for a in node.names}
    return found


def _app_files() -> list[Path]:
    return sorted(p for p in (BACKEND / "app").rglob("*.py") if "__pycache__" not in p.parts)


def test_drill_14_the_reviewer_is_the_file_it_was():
    """The separate reviewer decides every run, and this work may not change it. A change to that file needs Kevin's OK
    first; whoever makes one changes this fingerprint on purpose."""
    assert hashlib.sha256((BACKEND / "app" / "engine" / "reviewer.py").read_bytes()).hexdigest() == REVIEWER_SHA256


def test_drill_8_a_design_with_no_case_that_must_be_refused_is_refused_before_it_is_tried():
    note = {**demo.DESIGN, "select": {"flags": ["ValidSignature"], "ids": []}}      # ten cases, all of which must be accepted
    advisory = {"id": "CVE-2021-43572", "aliases": [], "package": {"name": "starkbank-ecdsa", "ecosystem": "PyPI"}, "published": "2021-11-10",
                "sources": [{"title": "t", "publisher": "p", "url": "https://example.com", "fetched_from": "https://example.com", "fetched": "2026-11-22",
                             "sha256": "0" * 64, "license": None, "excerpts": ["x"]}]}
    with pytest.raises(prompts.Refused, match="no case that must be rejected"):
        prompts.check_design_note(json.dumps(note), advisory, {"plain_name": "Zero signature accepted"}, {"prompt_sha256": "0" * 64, "answer_sha256": "0" * 64})


def test_the_app_never_imports_the_research_side_or_the_part_that_fetches_and_builds():
    """Only the research command (backend/ottolab) and the prepare step may fetch a library or build an image. The web
    app reads the store of copies; it never makes one."""
    for path in _app_files():
        rel = path.relative_to(BACKEND).as_posix()
        found = _imports(path)
        assert not any(name == "ottolab" or name.startswith("ottolab.") for name in found), f"{rel} imports the research side"
        if rel not in ("app/sandbox/maker.py", "app/prepare.py"):
            assert not any(name in ("app.sandbox.maker", "app.sandbox.maker.make_set") or name.endswith(".maker") for name in found), f"{rel} imports the maker"


def test_a_registry_is_reached_from_the_research_command_only():
    """`source_for` and `LiveRegistry` make the one thing that can ask a registry. Inside the app only the maker (which
    the research command runs) and the readers' own module name them."""
    allowed = {"app/sandbox/maker.py", "app/sandbox/registries.py"}
    for path in _app_files():
        rel = path.relative_to(BACKEND).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel not in allowed:
            assert "source_for(" not in text and "LiveRegistry(" not in text and ".project(" not in text, f"{rel} can ask a registry"
    # (the app's research loop imports the readers' module for its two tables of names, and for nothing else)
    discover = (BACKEND / "app" / "otto" / "discover.py").read_text(encoding="utf-8")
    used = {word for word in ("ECOSYSTEMS", "WORDS", "HOSTS", "LiveRegistry", "RecordedRegistry", "source_for", "read_versions", "read_release")
            if f"sandbox_registries.{word}" in discover}
    assert used == {"ECOSYSTEMS", "WORDS"}


def test_asking_code_is_text_everywhere_but_in_a_container():
    """Nothing in the app or in the research command imports, compiles or runs a piece of asking code. The research
    side parses it (the screen reads its syntax tree), writes it into a build folder, and that is all."""
    for folder in ("app", "ottolab", "evidence"):
        for path in sorted((BACKEND / folder).rglob("*.py")):
            if "__pycache__" in path.parts or path.parent.name == "pinned" and path.name in ("trial.py", "check_model_step.py"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval", "compile", "__import__"):
                    raise AssertionError(f"{path.relative_to(BACKEND)} calls {node.func.id}")
    screens = (BACKEND / "ottolab" / "screens.py").read_text(encoding="utf-8")
    assert "ast.parse(" in screens and "importlib" not in screens and "runpy" not in screens


def test_the_two_new_instruments_are_pinned_scripts_and_the_old_ones_are_not_touched():
    """`trial.py` and `check_model_step.py` are named by fingerprint in the two shipped packs: frozen means frozen. The
    sandbox instruments are new files beside them."""
    shipped = json.loads((REPO_ROOT / "research" / "packs" / "2026.11.2.json").read_text(encoding="utf-8"))["pack"]["otto"]["scripts"]
    pinned = BACKEND / "ottolab" / "pinned"
    for name in ("trial.py", "check_model_step.py"):
        assert hashlib.sha256((pinned / name).read_bytes()).hexdigest() == shipped[name]
    for name in ("agent.py", "research.py", "prompts.py"):
        assert hashlib.sha256((BACKEND / "ottolab" / name).read_bytes()).hexdigest() == shipped[f"ottolab/{name}"]
    assert (pinned / "trial_sandbox.py").is_file() and (pinned / "qualify.py").is_file()
