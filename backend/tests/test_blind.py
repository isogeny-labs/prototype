"""The blind test's three commands (docs/BLIND-TEST.md), rehearsed on our own demo program acme-sign 1.4.2 in demo mode.
This is a rehearsal of the mechanics only (seal, run, reveal, and the refusals). It is not a blind test: we planted that bug."""

import json

import pytest

from app import blind

EXPECTED = {
    "case": "rehearsal-acme",
    "library": {"name": "acme-sign", "version": "1.4.2", "algorithm": "ECDSA P-256"},
    "expect": [
        {"test": "official_vectors", "result": "Failed", "wrong_cases": ["168", "171", "364"]},
        {"test": "bad_signatures", "result": "Failed", "wrong_cases": ["r0-s0"]},
    ],
    "bug": "The verifier never checks that r and s are in range (a rehearsal: this is our own demo program).",
    "salt": "rehearsal-salt-0123456789-abcdefghijklmnopqrstuvwxyz",
}


def write(tmp_path, data, name="expected.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_seal_writes_only_the_fingerprint_and_is_never_replaced(tmp_path):
    said = []
    assert blind.seal(write(tmp_path, EXPECTED), tmp_path / "blind", said.append) == 0
    sealed = json.loads((tmp_path / "blind" / "rehearsal-acme" / "seal.json").read_text())
    assert sealed["expected_sha256"] == blind.read_expected(tmp_path / "expected.json")[1]
    assert (
        set(sealed["tests"]) == {"official_vectors", "bad_signatures", "speed_size"}
        and sealed["frozen_sha256"] == blind.frozen_fingerprint()
    )
    text = json.dumps(sealed)
    assert (
        EXPECTED["bug"] not in text and EXPECTED["salt"] not in text and "wrong_cases" not in text
    )  # nothing of the answer is in the seal
    with pytest.raises(blind.BlindError, match="already sealed"):
        blind.seal(write(tmp_path, EXPECTED), tmp_path / "blind", said.append)


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d.pop("salt"), "salt"),
        (lambda d: d.update(salt="short"), "salt"),
        (lambda d: d.update(case="../escape"), "case"),
        (lambda d: d["library"].pop("version"), "library"),
        (lambda d: d.update(expect=[]), "expect"),
        (lambda d: d.update(expect=[{"test": "no_such_test", "result": "Failed"}]), "expect"),
        (lambda d: d.update(expect=[{"test": "official_vectors", "result": "Maybe"}]), "expect"),
    ],
)
def test_a_badly_shaped_expected_file_is_refused(tmp_path, change, message):
    data = json.loads(json.dumps(EXPECTED))
    change(data)
    with pytest.raises(blind.BlindError, match=message):
        blind.read_expected(write(tmp_path, data))


def test_run_is_refused_when_a_test_changed_after_the_seal_or_the_library_is_not_registered(
    tmp_path, settings, monkeypatch
):
    folder = tmp_path / "blind"
    blind.seal(write(tmp_path, EXPECTED), folder, lambda text: None)
    monkeypatch.setattr(
        blind, "frozen_fingerprint", lambda: "0" * 64
    )  # as if a test, a rule or a test-set file had changed
    with pytest.raises(blind.BlindError, match="changed since this case was sealed"):
        blind.run("rehearsal-acme", folder, lambda text: None, settings)
    monkeypatch.undo()
    unknown = {
        **EXPECTED,
        "case": "unknown-library",
        "library": {"name": "not-a-library", "version": "9.9", "algorithm": "ECDSA P-256"},
    }
    blind.seal(write(tmp_path, unknown, "unknown.json"), folder, lambda text: None)
    with pytest.raises(blind.BlindError, match="not registered yet"):
        blind.run("unknown-library", folder, lambda text: None, settings)


@pytest.mark.slow
def test_seal_run_reveal_on_the_rehearsal_case(tmp_path, settings):
    folder, said = tmp_path / "blind", []
    expected = write(tmp_path, EXPECTED)
    blind.seal(expected, folder, said.append)
    assert blind.run("rehearsal-acme", folder, said.append, settings) == 0
    ran = json.loads((folder / "rehearsal-acme" / "run.json").read_text())
    by_test = {r["test"]: r for r in ran["results"]}
    assert by_test["official_vectors"]["result"] == "Failed" and by_test["official_vectors"]["wrong_cases"] == [
        "168",
        "171",
        "364",
    ]
    # (the rehearsal file lists only r0-s0 for this test; the app also finds s-plus-n, and the reveal says so below)
    assert by_test["bad_signatures"]["result"] == "Failed" and by_test["bad_signatures"]["wrong_cases"] == [
        "r0-s0",
        "s-plus-n",
    ]
    assert (folder / "rehearsal-acme" / "evidence.json").stat().st_size > 1000
    # a file that is not the sealed one is turned away, and nothing is compared
    other = write(tmp_path, {**EXPECTED, "bug": "a different story"}, "other.json")
    with pytest.raises(blind.BlindError, match="not the sealed file"):
        blind.reveal("rehearsal-acme", other, folder, said.append)
    assert not (folder / "rehearsal-acme" / "outcome.json").exists()
    assert blind.reveal("rehearsal-acme", expected, folder, said.append) == 0
    outcome = json.loads((folder / "rehearsal-acme" / "outcome.json").read_text())
    assert [(line["test"], line["outcome"]) for line in outcome["lines"]] == [
        ("official_vectors", "caught"),
        ("bad_signatures", "caught"),
    ]
    assert outcome["missed"] == 0 and outcome["bug"] == EXPECTED["bug"]
    assert (
        "s-plus-n" in outcome["lines"][1]["why"] and outcome["lines"][0]["why"] == ""
    )  # a case the expected file did not list is named


def test_compare_names_a_miss_a_part_catch_and_something_not_listed():
    expected = {
        "expect": [
            {"test": "official_vectors", "result": "Failed", "wrong_cases": ["168", "999"]},
            {"test": "bad_signatures", "result": "Failed"},
            {"test": "speed_size", "result": "Passed"},
        ]
    }
    ran = {
        "results": [
            {"test": "official_vectors", "title": "x", "result": "Failed", "wrong_cases": ["168", "171"]},
            {"test": "bad_signatures", "title": "y", "result": "Passed", "wrong_cases": []},
            {
                "test": "mldsa_vectors",
                "title": "Signature exam (ML-DSA-65)",
                "result": "Failed",
                "wrong_cases": ["nist-sign-31"],
            },
        ]
    }
    lines = {line["test"]: line for line in blind.compare(expected, ran)}
    assert (
        lines["official_vectors"]["outcome"] == "caught in part"
        and "999" in lines["official_vectors"]["why"]
        and "171" in lines["official_vectors"]["why"]
    )
    assert lines["bad_signatures"]["outcome"] == "missed"  # a miss is said as a miss
    assert lines["speed_size"]["outcome"] == "no result"  # the test did not run: nothing is claimed
    assert lines["mldsa_vectors"]["outcome"] == "found something not listed"


def test_the_freeze_covers_every_app_file_but_the_registry_and_the_exam_controls(tmp_path, monkeypatch):
    """What a seal freezes: every code file of the app except real_libraries.py (where a new library goes), the harness and
    its controls, the post-quantum exams' controls and the test-set files. A change to any of them changes the fingerprint."""
    app, real, parts, sets = (
        tmp_path / "backend" / "app",
        tmp_path / "demo" / "real-libraries",
        tmp_path / "demo" / "components",
        tmp_path / "demo" / "vectors",
    )
    for folder in (app / "execute", real / "openssl", real / "newlib", parts / "harness", parts / "controls", sets):
        folder.mkdir(parents=True)
    files = {
        app / "present.py": "words",
        app / "runner.py": "runs",
        app / "execute" / "signing.py": "asks",
        app / "real_libraries.py": "pins",
        real / "openssl" / "pq_controls.py": "controls",
        real / "openssl" / "openssl_adapter.py": "wrapper",
        real / "newlib" / "adapter.py": "new wrapper",
        parts / "harness" / "driver.py": "driver",
        parts / "controls" / "accept_all.py": "broken",
        sets / "cases.json": "{}",
    }
    for path, text in files.items():
        path.write_text(text)
    for name, value in (
        ("APP_DIR", app),
        ("REAL_DIR", real),
        ("COMPONENTS_DIR", parts),
        ("VECTORS_DIR", sets),
        ("REPO_ROOT", tmp_path),
    ):
        monkeypatch.setattr(blind, name, value)
    sealed = blind.frozen_fingerprint()
    for path in files:
        before = path.read_text()
        path.write_text(before + " changed")
        may_change = path in (app / "real_libraries.py", real / "newlib" / "adapter.py")  # adding the library itself
        assert (blind.frozen_fingerprint() == sealed) == may_change, path
        path.write_text(before)
    assert blind.frozen_fingerprint() == sealed


@pytest.mark.slow
def test_the_run_records_the_reviewers_own_verdict(tmp_path, settings):
    folder = tmp_path / "blind"
    blind.seal(write(tmp_path, EXPECTED), folder, lambda text: None)
    blind.run("rehearsal-acme", folder, lambda text: None, settings)
    ran = json.loads((folder / "rehearsal-acme" / "run.json").read_text())
    assert {r["test"]: (r["code"], r["result"]) for r in ran["results"]} == {
        "official_vectors": ("failed", "Failed"),
        "bad_signatures": ("failed", "Failed"),
        "speed_size": ("measured", "Measured"),
    }
