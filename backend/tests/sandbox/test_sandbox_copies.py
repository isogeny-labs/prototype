"""Sandbox research: a copy set's record is data, read strictly; a copy is seen only while the switch is on; a file
is used only with the registry's own fingerprint, and a version's file never changes on this computer."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import random
import tarfile
import zipfile
from pathlib import PurePosixPath

import pytest
from sandbox_fixtures import copy_set

from app import real_libraries
from app.sandbox import copies, maker, registries


def _sdist(files: dict[str, bytes], top: str = "thing-1.0.0", link: str | None = None) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if link:
            info = tarfile.TarInfo(f"{top}/{link}")
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            archive.addfile(info)
    return raw.getvalue()


class _Source:
    key = "recorded"

    def __init__(self, data: bytes) -> None:
        self.data = data

    def file(self, registry, wanted):
        return self.data


def _release(data: bytes, version: str = "1.0.0") -> registries.Release:
    return registries.Release("pypi", "thing", version, "2021-01-01",
                              registries.File(f"thing-{version}.tar.gz", "https://files.pythonhosted.org/x", "sdist", len(data),
                                              sha256=hashlib.sha256(data).hexdigest()))


# ---------------------------------------------------------------- the record

def test_a_real_copy_sets_record_reads_and_is_named_by_the_fingerprint_of_its_content():
    record = copies.check_set(copy_set())
    assert record["id"] == copies.set_id(record) and record["image"]["tag"] == copies.image_tag(record["library"], record["id"])
    assert copies.versions_of(record) == ["1.1.0", "1.1.1", "2.0.0", "2.0.1", "2.0.2", "2.3.1"] or set(copies.versions_of(record)) >= {"2.0.0", "2.0.1"}
    assert copies.family_of(record) == "sandbox-" + record["id"]
    made = copies.as_library(record)
    assert made["sandbox"] == record["id"] and made["checks_only"] is True and made["fixed_in"]["2.0.0"] == "2.0.1"
    assert "2.0.2" not in made["fixed_in"]                      # a version after the fix needs no fix


@pytest.mark.parametrize("change", [
    lambda r: r["asking"].__setitem__("source", r["asking"]["source"] + "\n# one more line\n"),          # the code, not its fingerprint
    lambda r: r["versions"][0]["files"][0].__setitem__("sha256", "0" * 64),                              # a file swapped
    lambda r: r["versions"][0].__setitem__("tree_sha256", "1" * 64),
    lambda r: r.__setitem__("id", "0" * 16),
    lambda r: r["image"].__setitem__("tag", "python:3.12"),                                              # another image
    lambda r: r.__setitem__("extra", 1),
    lambda r: r["versions"].append(dict(r["versions"][0])),                                              # a version twice
    lambda r: r["asking"].__setitem__("kind", "trusted"),
    lambda r: r["versions"][0]["files"][0].__setitem__("source", "somewhere"),
])
def test_a_record_that_was_changed_is_refused(change):
    record = copy_set()
    change(record)
    with pytest.raises(copies.CopyError, match="not written as this version writes it"):
        copies.check_set(record)


def test_seeded_fuzz_of_a_damaged_record_is_a_plain_refusal_or_the_record_itself():
    rng = random.Random(20261122)
    seed = json.dumps(copy_set()).encode()
    for _ in range(500):
        raw = bytearray(seed)
        for _ in range(rng.randint(1, 5)):
            at = rng.randrange(len(raw))
            how = rng.random()
            if how < 0.5:
                raw[at] = rng.randrange(256)
            elif how < 0.8:
                del raw[at:at + rng.randint(1, 40)]
            else:
                raw[at:at] = bytes(rng.randrange(32, 127) for _ in range(rng.randint(1, 10)))
        try:
            read = copies.read_set(bytes(raw))
            assert read["id"] == copies.set_id(read)             # whatever still reads is whole
        except copies.CopyError as refused:
            assert str(refused)


# ---------------------------------------------------------------- seen only with the switch on

def test_a_copy_is_seen_only_while_its_apps_switch_is_on(tmp_path):
    record = copy_set()
    copies.write_set(tmp_path, record)
    on = {"value": False}
    copies.register(tmp_path, lambda: on["value"])
    try:
        assert copies.find("starkbank-ecdsa", "2.0.0") is None and real_libraries.library("starkbank-ecdsa", "2.0.0") is None
        assert real_libraries.known("starkbank-ecdsa") is None and real_libraries.family_of_subject("starkbank-ecdsa-2.0.0") is None
        on["value"] = True
        found = real_libraries.library("starkbank-ecdsa", "2.0.0")
        assert found is not None and found["sandbox"] == record["id"] and real_libraries.is_sandbox("starkbank-ecdsa", "2.0.0")
        assert real_libraries.library("starkbank-ecdsa", "9.9.9") is None                # exact name and version only
        assert real_libraries.family_of_subject("starkbank-ecdsa-2.0.0") == "sandbox-" + record["id"]
        assert real_libraries.family_label("sandbox-" + record["id"]) == "starkbank-ecdsa (sandbox copy)"
        # the pinned libraries always come first, and nothing here adds to them
        assert real_libraries.library("python-ecdsa", "0.13.2") is real_libraries.LIBRARIES["python-ecdsa"]
        assert "starkbank-ecdsa" not in real_libraries.LIBRARIES
    finally:
        copies.unregister(tmp_path)
    assert copies.find("starkbank-ecdsa", "2.0.0") is None


def test_an_image_counts_only_if_it_is_the_one_the_record_names(tmp_path, monkeypatch):
    record = copy_set()
    copies.write_set(tmp_path, record)
    copies.register(tmp_path, lambda: True)
    try:
        seen = {}
        monkeypatch.setattr(copies, "image_is", lambda tag, the_id: seen.setdefault("asked", (tag, the_id)) and False)
        assert copies.images_present() == {}                     # a changed image is not run: its family has no image
        assert seen["asked"] == (record["image"]["tag"], record["image"]["id"])
        monkeypatch.setattr(copies, "image_is", lambda tag, the_id: True)
        assert copies.images_present() == {"sandbox-" + record["id"]: record["image"]["tag"]}
    finally:
        copies.unregister(tmp_path)


def test_a_damaged_record_in_the_store_is_left_out_never_half_used(tmp_path):
    record = copy_set()
    path = copies.write_set(tmp_path, record)
    assert [r["id"] for r in copies.sets_in(tmp_path)] == [record["id"]]
    path.write_text(path.read_text().replace(record["asking"]["sha256"], "0" * 64))
    assert copies.sets_in(tmp_path) == []


# ---------------------------------------------------------------- fetching and unpacking (the research command only)

def test_a_file_without_the_registrys_own_fingerprint_is_not_used(tmp_path):
    data = _sdist({"thing/__init__.py": b"x = 1\n"})
    release = _release(data)
    changed = bytearray(data)
    changed[len(changed) // 2] ^= 1                              # the same size, one bit apart
    with pytest.raises(copies.CopyError, match="does not have the fingerprint PyPI itself gives"):
        maker.fetch(tmp_path, _Source(bytes(changed)), release)
    with pytest.raises(copies.CopyError, match="not the size PyPI gives"):
        maker.fetch(tmp_path, _Source(data + b"more"), release)
    assert not (tmp_path / "files").exists()                     # nothing was kept


def test_a_versions_file_never_changes_on_this_computer(tmp_path):
    first, second = _sdist({"thing/__init__.py": b"x = 1\n"}), _sdist({"thing/__init__.py": b"x = 2\n"})
    made = maker.fetch(tmp_path, _Source(first), _release(first))
    assert made["sha256"] == hashlib.sha256(first).hexdigest() and made["registry_fingerprint"] == "sha256:" + made["sha256"]
    again = maker.fetch(tmp_path, _Source(first), _release(first))
    assert again["fetched_at"] == made["fetched_at"]             # the day it was first fetched stands
    # the registry now gives another file for the same version, with a fingerprint of its own that holds: still refused
    with pytest.raises(copies.CopyError, match="is not the file this computer fetched"):
        maker.fetch(tmp_path, _Source(second), _release(second))


@pytest.mark.parametrize("name", ["../outside.py", "/etc/passwd", "a/../../b.py"])
def test_a_path_that_leaves_the_folder_refuses_the_whole_file(name):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as archive:
        info = tarfile.TarInfo(name)
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(copies.CopyError, match="not a plain file"):
        maker._members(raw.getvalue(), "thing-1.0.0.tar.gz")


def test_a_link_inside_a_package_refuses_the_whole_file():
    with pytest.raises(copies.CopyError, match="not a plain file"):
        maker._members(_sdist({"thing/__init__.py": b""}, link="thing/evil"), "thing-1.0.0.tar.gz")
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        info = zipfile.ZipInfo("thing/evil")
        info.external_attr = 0xA1ED0000                          # a symbolic link
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(copies.CopyError, match="not a plain file"):
        maker._members(raw.getvalue(), "thing-1.0.0-py3-none-any.whl")


def test_what_is_not_a_package_file_is_refused_plainly():
    for data in (b"", b"not a package", gzip.compress(b"not a tar file")):
        with pytest.raises(copies.CopyError, match="could not be read as a package file"):
            maker._members(data, "thing-1.0.0.tar.gz")


def test_a_source_packages_set_up_program_is_left_out_and_nothing_of_it_runs():
    data = _sdist({"setup.py": b"raise SystemExit('this must never run')\n", "PKG-INFO": b"Name: thing\nVersion: 1.0.0\n\nbody\n",
                   "thing/__init__.py": b"VALUE = 1\n", "thing/core.py": b"def f():\n    return 1\n", "tests/test_x.py": b"import os\n",
                   "conftest.py": b"raise SystemExit\n"})
    tree, says = maker._python_tree({"file": "thing-1.0.0.tar.gz"}, data)
    assert set(tree) == {PurePosixPath("thing/__init__.py"), PurePosixPath("thing/core.py")}
    assert says == {"name": "thing", "version": "1.0.0"}
    with pytest.raises(copies.CopyError, match="holds no Python code"):
        maker._python_tree({"file": "thing-1.0.0.tar.gz"}, _sdist({"setup.py": b"x\n", "README": b"y\n"}))


def test_the_subjects_of_an_image_are_the_copies_and_the_two_dummy_controls():
    table = maker.subjects_for("thing", "python", ["1.0.0", "1.0.1"], {"kind": "written"})
    assert set(table) == {"thing-1.0.0", "thing-1.0.1", "dummy-yes:thing-1.0.0", "dummy-no:thing-1.0.0", "dummy-yes:thing-1.0.1", "dummy-no:thing-1.0.1"}
    for command in table.values():
        assert command[0] == "/usr/local/bin/python" and "-I" in command      # (isolated: nothing beside the copy is on its path)
