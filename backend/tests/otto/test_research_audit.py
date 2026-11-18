"""Phase 5c: the research side's audit command reads a lab folder as data.

`python -m ottolab.build audit [--lab DIR]` checks a research ledger. Otto's harness, asked to check entries again,
starts the checker file that stands in the lab folder, and whatever a verifier names. So the command never asks it
to: the harness checks the chain and the records and derives every decision again, and the command itself runs the
research side's own pinned checker (ottolab/pinned/check_model_step.py). A folder that holds a link, or a ledger that
names anything else, is refused before anything is run. These tests plant such folders; each has a marker that would
be written if anything from the folder ran."""
import json
import shutil
import sys
from types import SimpleNamespace

import pytest

from ottolab import build, research


@pytest.fixture
def said(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(build, "say", lines.append)
    return lines


def _audit(folder) -> int:
    return build.audit(SimpleNamespace(lab=str(folder)))


def _planted(marker) -> str:
    return f"import json\nopen({str(marker)!r}, 'w').write('ran')\nprint(json.dumps({{'status': 'accept', 'detail': 'planted'}}))\n"


@pytest.fixture
def lab_copy(tmp_path):
    """A copy of the repository's own research lab, to plant things in."""
    copy = tmp_path / "lab"
    shutil.copytree(build.LAB, copy)
    return copy


@pytest.mark.needs_otto
def test_the_repository_s_own_lab_passes_and_nothing_is_written_into_it(lab_copy, said):
    before = sorted((p.relative_to(lab_copy).as_posix(), p.stat().st_size) for p in lab_copy.rglob("*") if p.is_file())
    assert _audit(lab_copy) == 0, said
    assert said[-1].endswith("entries; chain intact, every decision re-derived, every pinned checker run again.")
    assert sorted((p.relative_to(lab_copy).as_posix(), p.stat().st_size) for p in lab_copy.rglob("*") if p.is_file()) == before


@pytest.mark.needs_otto
def test_a_link_in_the_lab_is_refused_and_nothing_runs(lab_copy, said, tmp_path):
    """The trick an independent review found: the lab's checker is a link whose target depends on the folder a program
    is started in. It reads as the pinned checker here, and as the folder's own program to a child started there."""
    marker = tmp_path / "ran.txt"
    (lab_copy / "ottolab" / "pinned").mkdir(parents=True)
    (lab_copy / "ottolab" / "pinned" / "check_model_step.py").write_text(_planted(marker))
    (lab_copy / "check_model_step.py").unlink()
    (lab_copy / "check_model_step.py").symlink_to("/proc/self/cwd/ottolab/pinned/check_model_step.py")
    assert _audit(lab_copy) == 1
    assert len(said) == 1 and said[0].startswith("PROBLEM: the lab folder holds something that is not a folder or a regular file")
    assert "check_model_step.py" in said[0] and said[0].endswith("Nothing was run") and not marker.exists()


@pytest.mark.needs_otto
def test_another_program_in_the_checker_s_place_is_never_started(lab_copy, said, tmp_path):
    """A regular file with other bytes where the lab's copy of the checker stands. The command starts its own pinned
    checker and never that file, and it says that the lab's copy is not the pinned one."""
    marker = tmp_path / "ran.txt"
    (lab_copy / "check_model_step.py").write_text(_planted(marker))
    assert _audit(lab_copy) == 1 and not marker.exists()
    assert said == ["PROBLEM: the lab's check_model_step.py is not the one in ottolab/pinned"]


@pytest.mark.needs_otto
def test_a_ledger_that_names_something_else_to_run_is_refused(lab_copy, said, tmp_path):
    """One entry is added to the end of the real ledger, through the harness's own writer: an objective that names a
    command to replay."""
    marker = tmp_path / "ran.txt"
    lab = build.harness.module("lab").Lab(str(lab_copy))
    lab.add({"type": "objective", "statement": "made for a test",
             "verifier": {"kind": "replay", "command": [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ran')"],
                          "code": {"trial.py": research.file_sha256(lab_copy / "trial.py")}}}, "a test")
    assert _audit(lab_copy) == 1 and not marker.exists()
    assert said == ["PROBLEM: an entry names something to run that is not the research side's own pinned checker. Nothing was run"]


@pytest.mark.needs_otto
def test_a_folder_that_holds_no_ledger_or_a_broken_one_is_said_plainly(tmp_path, said):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _audit(empty) == 1 and said == ["PROBLEM: there is no ledger file in this folder"]
    said.clear()
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "ledger.jsonl").write_text('{"not": "a ledger"}\n')
    assert _audit(broken) == 1
    assert len(said) == 1 and said[0].startswith("PROBLEM: the lab could not be audited (")
    said.clear()
    # text from the folder is printed as plain characters only
    odd = tmp_path / "odd"
    odd.mkdir()
    (odd / "ledger.jsonl").write_text(json.dumps({"seq": 0, "prev": None, "kind": "question", "ts": "x", "hash": "\x1b[2K\rEvidence verified",
                                                  "payload": {"type": "question"}}) + "\n")
    assert _audit(odd) == 1 and said and all(ch.isprintable() for line in said for ch in line)


def test_a_lab_folder_is_opened_only_when_it_holds_folders_and_regular_files(tmp_path):
    """Before the research command writes anything into a lab, and before the audit reads one. This needs no harness:
    the refusal comes first."""
    lab = tmp_path / "lab"
    (lab / "runs" / "abc").mkdir(parents=True)
    (lab / "ledger.jsonl").write_text("")
    (lab / "runs" / "abc" / "stdout").write_text("x")
    assert build.only_regular_files(lab) is None
    (lab / "trial.py").symlink_to(tmp_path / "elsewhere.py")                 # a link that leads nowhere yet
    assert "not a folder or a regular file (trial.py)" in build.only_regular_files(lab)
    with pytest.raises(research.ResearchError) as refused:
        build.open_lab(lab)
    assert "Nothing was done" in str(refused.value) and not (tmp_path / "elsewhere.py").exists()      # nothing was written through it
    (lab / "trial.py").unlink()
    (lab / "runs" / "abc" / "stdout").unlink()
    (lab / "runs" / "abc" / "stdout").symlink_to("/etc/hostname")
    assert "runs/abc/stdout" in build.only_regular_files(lab)
    link = tmp_path / "linked-lab"
    link.symlink_to(lab)
    assert build.only_regular_files(link) == "the lab folder is a link"


def test_the_pinned_checker_is_started_with_a_fixed_command_and_a_bare_environment(monkeypatch, tmp_path):
    seen = []
    real = build.subprocess.run

    def watch(argv, **kwargs):
        seen.append((list(argv), kwargs))
        return real(argv, **kwargs)
    monkeypatch.setattr(build.subprocess, "run", watch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "made-up-key-for-tests-0123456789")
    marker = tmp_path / "ran.txt"
    answer = build.run_pinned_checker({"step": "read_advisory", "advisory": "X", "command": ["sh", "-c", f"touch {marker}"]}, {"made": "up"})
    assert answer == "reject" and not marker.exists()
    (argv, kwargs), = seen
    assert argv == [sys.executable, "-I", str(research.PINNED / research.CHECKER)] and kwargs["shell"] is False
    assert kwargs["env"] == {"PATH": build.os.environ.get("PATH", "")}
    assert build.run_pinned_checker(None, None) in ("reject", "unavailable")
