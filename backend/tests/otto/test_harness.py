"""Phase 5c, step 1: Adam's Otto harness at its pinned commit.

The pin names one commit and one fingerprint; a copy that differs by one byte is refused; without the copy the app
says "Otto is not installed", with the reason, and works as before."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app import prepare
from app.otto import harness

BACKEND = Path(__file__).resolve().parents[2]


def test_the_lock_names_one_full_commit_and_fingerprint():
    lock = harness.read_lock()
    assert lock.repository == "isogeny-labs/otto" and lock.url == "https://github.com/isogeny-labs/otto"
    assert len(lock.commit) == 40 and len(lock.tree_sha256) == 64
    data = json.loads(harness.LOCK_PATH.read_text())
    assert set(data) == {"repository", "url", "commit", "version", "tree_sha256", "note"}


def test_otto_is_not_in_this_repository_and_its_folder_is_ignored():
    """Adam's code is fetched, never copied in: git ignores the folder it is fetched into."""
    ignored = (BACKEND.parent / ".gitignore").read_text()
    assert "backend/.otto/" in ignored
    tracked = subprocess.run(["git", "ls-files", "backend/.otto"], cwd=BACKEND.parent, capture_output=True, text=True)
    assert tracked.returncode != 0 or tracked.stdout.strip() == ""


def test_a_missing_or_broken_pin_file_is_said_plainly(tmp_path):
    with pytest.raises(harness.OttoNotInstalled) as missing:
        harness.read_lock(tmp_path / "nothing.json")
    assert "pin file" in str(missing.value)
    short = tmp_path / "short.json"
    short.write_text(json.dumps({"repository": "x", "url": "https://x", "commit": "abc", "version": "1", "tree_sha256": "00"}))
    with pytest.raises(harness.OttoNotInstalled):
        harness.read_lock(short)
    found = harness.status(tmp_path / "nothing.json")
    assert found.installed is False and found.sentence.startswith("Otto is not installed on this computer: ")


def test_the_fingerprint_covers_every_file_and_ignores_what_running_leaves_behind(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.py").write_text("x = 1\n")
    (tmp_path / "two.md").write_text("two\n")
    first = harness.tree_sha256(tmp_path)
    (tmp_path / "a" / "__pycache__").mkdir()
    (tmp_path / "a" / "__pycache__" / "one.cpython-312.pyc").write_bytes(b"\x00")
    assert harness.tree_sha256(tmp_path) == first          # compiled files don't count
    (tmp_path / "two.md").write_text("two!\n")
    assert harness.tree_sha256(tmp_path) != first          # one changed byte does
    (tmp_path / "two.md").write_text("two\n")
    (tmp_path / "three.md").write_text("")
    assert harness.tree_sha256(tmp_path) != first          # so does one more file


def test_unpacking_leaves_out_links_and_anything_outside_the_folder(tmp_path):
    import io
    import tarfile
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        good = tarfile.TarInfo("otto/__init__.py")
        data = b"__version__ = \"0\"\n"
        good.size = len(data)
        tar.addfile(good, io.BytesIO(data))
        link = tarfile.TarInfo("otto/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    assert harness._unpack(buffer.getvalue(), tmp_path / "ok") is True
    assert (tmp_path / "ok" / "otto" / "__init__.py").is_file() and not (tmp_path / "ok" / "otto" / "link").exists()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        bad = tarfile.TarInfo("../outside.py")
        bad.size = 1
        tar.addfile(bad, io.BytesIO(b"x"))
    assert harness._unpack(buffer.getvalue(), tmp_path / "bad") is False
    assert not (tmp_path / "outside.py").exists()


def test_prepare_reports_otto_and_never_stops_the_start(monkeypatch):
    said = []
    monkeypatch.setattr(harness, "read_lock", lambda *a, **k: (_ for _ in ()).throw(harness.OttoNotInstalled("its pin file can't be read")))
    assert prepare.prepare_otto(True, said.append) is False
    assert said and said[0].startswith("Otto: not installed")


def test_prepare_with_otto_alone_looks_at_the_harness_only_and_never_at_docker(monkeypatch):
    """`python -m app.prepare --otto` is what ./run-demo.sh runs on every computer: the harness and nothing else. It
    asks Docker nothing and its exit code is 0 whether Otto could be fetched or not, so it can't stop the start."""
    said, asked = [], []
    monkeypatch.setattr(prepare, "docker_running", lambda *a, **k: asked.append("docker") or True)
    monkeypatch.setattr(prepare, "prepare_otto", lambda check_only, say: asked.append(("otto", check_only)) or False)
    assert prepare.main(["--otto"], say=said.append) == 0
    assert prepare.main(["--otto", "--check"], say=said.append) == 0
    assert asked == [("otto", False), ("otto", True)] and not any("Isolated mode" in line for line in said)
    # a fetch that goes wrong is said in a plain line and is not an error
    lock = harness.read_lock()
    monkeypatch.undo()
    monkeypatch.setattr(harness, "status", lambda *a, **k: harness.OttoStatus(False, harness.NOT_FETCHED, lock.repository, lock.commit, lock.version, None))
    monkeypatch.setattr(harness, "fetch", lambda *a, **k: (_ for _ in ()).throw(OSError("no network")))
    monkeypatch.setattr(prepare, "docker_running", lambda *a, **k: asked.append("docker") or True)
    assert prepare.main(["--otto"], say=said.append) == 0
    assert any(line.startswith("Otto harness: missing") for line in said) and any("advisory checks are off" in line for line in said)
    assert "docker" not in asked


@pytest.mark.needs_otto
def test_the_pinned_copy_is_the_one_the_lock_names():
    found = harness.status()
    lock = harness.read_lock()
    assert found.installed and found.path == lock.folder
    assert harness.tree_sha256(lock.folder) == lock.tree_sha256
    package = harness.load()
    assert package.__version__ == lock.version
    assert Path(package.__file__).parent.parent == lock.folder      # loaded from the pinned folder, nowhere else
    assert harness.module("lab").Lab and harness.module("ledger").Ledger


@pytest.mark.needs_otto
def test_a_copy_that_differs_by_one_byte_is_not_installed(tmp_path, monkeypatch):
    lock = harness.read_lock()
    copy_home = tmp_path / ".otto"
    shutil.copytree(lock.folder, copy_home / lock.commit, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(harness, "OTTO_HOME", copy_home)
    harness._forget()
    try:
        assert harness.status().installed is True
        target = copy_home / lock.commit / "otto" / "ledger.py"
        target.write_bytes(target.read_bytes() + b"\n")
        harness._forget()
        found = harness.status()
        assert found.installed is False and "not the pinned one" in found.reason
        with pytest.raises(harness.OttoNotInstalled):
            harness.load()
    finally:
        monkeypatch.undo()
        harness._forget()
    assert harness.status().installed is True


@pytest.mark.needs_otto
def test_a_fetch_with_the_wrong_fingerprint_installs_nothing(tmp_path, monkeypatch):
    lock = harness.read_lock()
    archive = _archive_of(lock.folder)        # the real pinned files, read before the folder is pointed elsewhere
    wrong = harness.Lock(lock.repository, lock.url, lock.commit, lock.version, "0" * 64)
    monkeypatch.setattr(harness, "OTTO_HOME", tmp_path / ".otto")
    monkeypatch.setenv(harness.SOURCE_ENV, str(tmp_path / "no-such-checkout"))
    monkeypatch.setattr(harness, "archive_of", lambda commit, source, url: archive)
    said = []
    assert harness.fetch(wrong, said.append) is False
    assert not wrong.folder.exists() and any("not the pinned copy" in line for line in said)
    assert harness.fetch(lock, said.append) is True and (tmp_path / ".otto" / lock.commit / "otto" / "lab.py").is_file()
    monkeypatch.undo()
    harness._forget()


def _archive_of(folder: Path) -> bytes:
    import io
    import tarfile
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and not path.is_symlink():
                tar.add(path, arcname=path.relative_to(folder).as_posix())
    return buffer.getvalue()


@pytest.mark.needs_otto
@pytest.mark.slow
def test_adams_own_tests_and_audit_pass_from_the_pinned_copy():
    """Adam's two checks (AGENTS.md of his repository), run on a copy of the pinned files with this app's Python."""
    before = harness.tree_sha256(harness.status().path)
    done = harness.own_checks(600)
    assert done["tests_ok"], done["tests_line"]
    assert done["audit_ok"] and "chain intact, every decision re-derived" in done["audit_line"]
    assert harness.tree_sha256(harness.status().path) == before       # running them left the pinned copy as it was


def test_another_folder_can_be_named_for_the_harness_and_an_empty_one_reads_as_not_installed(tmp_path):
    """EVIDENCE_LAB_OTTO_HOME names the folder the pinned copy is kept in (the end-to-end walk points it at an empty
    one). The app then says, plainly, that Otto is not installed here; nothing is fetched and nothing else changes."""
    import os
    import subprocess
    import sys
    code = ("from app.otto import harness; s = harness.status(); "
            "print(harness.OTTO_HOME); print(s.installed); print(s.sentence)")
    env = {**os.environ, harness.HOME_ENV: str(tmp_path)}
    done = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    home, installed, sentence = done.stdout.strip().splitlines()
    assert Path(home) == tmp_path.resolve() and installed == "False"
    assert sentence.startswith("Otto is not installed on this computer") and "has not been fetched" in sentence
    assert list(tmp_path.iterdir()) == []                                  # looking fetched nothing
