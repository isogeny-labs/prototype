"""Real libraries (phase 4c) through the same path as the buttons, driven as a Lab through its methods.

Demo mode (no Docker needed): a real library can't run there, and every screen says so. Isolated mode (real
containers, skipped with a message when Docker or the image of a family is not ready): the elliptic library through
Verify, Run all, Fixes, Retest, Download evidence; and the ML-KEM-768 key exchange exam of OpenSSL 3.5.9."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.run import runner
from app.accuracy_real import _fixes, _migration, _result, _rows
from app.engine.compare import COULDNT, TRUE
from app.config import DEMO_DIR
from app.evidence.export import PUBLIC_KEY_FILE
from evidence import verify_bytes
from conftest import csv_bytes, make_lab, result_of

BACKEND = Path(__file__).resolve().parents[1]
REAL_FILE = DEMO_DIR / "real-libraries.csv"
ELLIPTIC_ONLY = "elliptic 6.5.6,software,signature_algorithm,ECDSA P-256"
KEM_ONLY = "openssl 3.5.9,software,key_exchange,ML-KEM-768"
ACME = "acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256"
LABELS = [
    "openjdk 17.0.2",
    "python-ecdsa 0.13.2",
    "elliptic 6.5.6",
    "openssl 3.5.9 (ECDSA P-256)",
    "openssl 3.5.9 (ML-DSA-65)",
    "openssl 3.5.9 (ML-KEM-768)",
]
DEMO_NOTE = (
    "This is real software from outside. It runs only in isolated mode (Docker), and this run is in demo mode, "
    "so its tests can't run here."
)


def need(mode, *families: str) -> None:
    missing = [family for family in families if not mode.real_images.get(family)]
    if missing:
        pytest.skip(
            f"Skipped: the real-library image for {', '.join(missing)} is not prepared "
            "(run: cd backend && .venv/bin/python -m app.prepare)."
        )


def notes_of(imp: dict) -> list[str]:
    return list(imp.get("notices") or [])


# ------------------------------------------------------------------ demo mode: nothing of a real library runs


@pytest.fixture(scope="module")
def demo_mode(tmp_path_factory):
    """The whole real-libraries file in demo mode: import, Verify, the plan, Run all, Measure status. Every process the
    runner starts is recorded, so a test can say that no container was started."""
    lab = make_lab(tmp_path_factory.mktemp("real-demo"))  # demo mode, forced
    started, real_popen = [], subprocess.Popen
    patch = pytest.MonkeyPatch()
    patch.setattr(
        runner.subprocess, "Popen", lambda argv, *a, **kw: (started.append(list(argv)), real_popen(argv, *a, **kw))[1]
    )
    try:
        imp = lab.import_file(REAL_FILE.name, REAL_FILE.read_bytes())
        verify = lab.verify(imp["id"])
        plan = lab.ensure_plan(imp["id"])
        before_run = lab.lab_view(plan["id"])
        lab.run_all(plan["id"])
        lab.wait_until_idle(plan["id"], 300)
        after_run = lab.lab_view(plan["id"])
        lab.measure_migration(plan["id"])
        lab.wait_until_measured(plan["id"], 300)
        yield SimpleNamespace(
            lab=lab,
            imp=imp,
            verify=verify,
            plan=plan,
            before_run=before_run,
            after_run=after_run,
            started=started,
            migration=_migration(lab.migration_view(plan["id"])),
        )
    finally:
        patch.undo()
        lab.stop()


def test_demo_mode_import_says_real_software_needs_isolated_mode(demo_mode):
    imp = demo_mode.imp
    assert imp["is_demo"] is False, "a file of real libraries from outside must not be labelled demo data"
    notices = notes_of(imp)
    assert len(notices) == 1 and notices[0].startswith("Real software: "), notices
    assert "isolated mode" in notices[0] and "demo mode" in notices[0] and "not demo data" in notices[0], notices[0]
    assert len(imp["claims"]) == 6 and {c["location_kind"] for c in imp["claims"]} == {"software"}


def test_demo_mode_verify_couldnt_check_six_claims_naming_isolated_mode(demo_mode):
    results = [r for r in demo_mode.verify["results"] if r["claim"]["location_kind"] == "software"]
    assert len(results) == 6
    assert [r["result"] for r in results] == [COULDNT] * 6
    for r in results:
        assert "isolated mode" in r["summary"], r["summary"]


def test_demo_mode_plan_has_fifteen_tests_in_six_groups_each_with_the_note(demo_mode):
    assert len(demo_mode.plan["tests"]) == 15
    view = demo_mode.before_run
    assert [g["heading"].split(": ", 1)[-1] for g in view["groups"]] == LABELS
    assert [g["heading"].split(": ", 1)[0] for g in view["groups"]] == ["Signing program"] * 5 + [
        "Key exchange program"
    ]
    assert [g["note"] for g in view["groups"]] == [DEMO_NOTE] * 6
    assert Counter(row["group"] for row in view["rows"]).total() == 15
    lines = (view["not_tested"] or {}).get("items") or []
    assert (view["not_tested"] or {}).get("title") == "Not tested, and why"
    for label in LABELS:
        assert any(line.startswith(f"{label}: this is real software from outside") for line in lines), (label, lines)


def test_demo_mode_run_all_gives_fifteen_couldnt_run_and_starts_no_container(demo_mode):
    rows = _rows(demo_mode.lab, demo_mode.after_run, "result")
    assert len(rows) == 15
    for key, result in rows.items():
        assert (
            result is not None and result["code"] == "couldnt_run" and result["reason_code"] == "needs_isolated_mode"
        ), (key, result)
    assert [argv for argv in demo_mode.started if argv and argv[0] == "docker"] == [], (
        "a docker process was started in demo mode"
    )
    assert demo_mode.started == [], f"a process was started for a real library in demo mode: {demo_mode.started}"


def test_demo_mode_retest_menu_lists_six_versions_of_three_libraries(demo_mode):
    menu = demo_mode.after_run["retest"]["versions"]
    assert len(menu) == 6 and all(item["component"] for item in menu)
    assert Counter(item["component"] for item in menu) == {"openjdk": 2, "python-ecdsa": 2, "elliptic": 2}
    assert sorted(item["label"] for item in menu) == [
        "elliptic 6.5.6",
        "elliptic 6.5.7",
        "openjdk 17.0.2",
        "openjdk 17.0.3",
        "python-ecdsa 0.13.2",
        "python-ecdsa 0.13.3",
    ]


def test_demo_mode_migration_couldnt_check_all_five_systems(demo_mode):
    systems = demo_mode.migration
    assert len(systems) == 5, list(systems)
    assert not any("ML-KEM" in name for name in systems), "the ML-KEM-768 row has no Migration system"
    for name, system in systems.items():
        assert system["status"] == "Couldn't check" and "isolated mode" in system["today"], (name, system)


@pytest.mark.slow
def test_a_real_library_beside_acme_sign_keeps_the_file_demo_data_but_still_cannot_run(tmp_path):
    lab = make_lab(tmp_path)
    try:
        imp = lab.import_file("acme-and-elliptic.csv", csv_bytes(ACME, ELLIPTIC_ONLY))
        assert imp["is_demo"] is True, "acme-sign is ours, so the file stays labelled demo data"
        assert any(n.startswith("Real software: elliptic 6.5.6.") for n in notes_of(imp)), notes_of(imp)
        verify = {r["claim"]["location"]: r for r in lab.verify(imp["id"])["results"]}
        assert verify["acme-sign 1.4.2"]["result"] == TRUE
        assert verify["elliptic 6.5.6"]["result"] == COULDNT and "isolated mode" in verify["elliptic 6.5.6"]["summary"]
        plan = lab.ensure_plan(imp["id"])
        lab.run_all(plan["id"])
        lab.wait_until_idle(plan["id"], 300)
        view = lab.lab_view(plan["id"])
        notes = {g["heading"].split(": ", 1)[-1]: g["note"] for g in view["groups"]}
        assert notes == {"acme-sign 1.4.2": None, "elliptic 6.5.6": DEMO_NOTE}
        rows = _rows(lab, view, "result")
        acme = {kind: result for (label, kind), result in rows.items() if label == "acme-sign 1.4.2"}
        real = {kind: result for (label, kind), result in rows.items() if label == "elliptic 6.5.6"}
        assert (acme["official_vectors"]["label"], acme["bad_signatures"]["label"]) == ("Failed", "Failed"), (
            acme
        )  # ours still run, in demo mode
        assert acme["speed_size"]["label"] == "Measured"
        assert len(real) == 3 and all(
            r["code"] == "couldnt_run" and r["reason_code"] == "needs_isolated_mode" for r in real.values()
        ), real
    finally:
        lab.stop()


# ------------------------------------------------------------------ isolated mode: elliptic, start to finish


@pytest.fixture(scope="module")
def elliptic(docker_ready, tmp_path_factory):
    """A file with only elliptic 6.5.6: Verify, Run all, the Fixes view; the retest is made by the test that needs it."""
    need(docker_ready, "elliptic")
    lab = make_lab(tmp_path_factory.mktemp("real-elliptic"), force_mode=None, speed_rounds=40, speed_repeats=5)
    try:
        assert lab.mode.name == "isolated"
        imp = lab.import_file("elliptic.csv", csv_bytes(ELLIPTIC_ONLY))
        verify = lab.verify(imp["id"])
        plan = lab.ensure_plan(imp["id"])
        lab.run_all(plan["id"])
        lab.wait_until_idle(plan["id"], 900)
        yield SimpleNamespace(
            lab=lab,
            imp=imp,
            verify=verify,
            pid=plan["id"],
            first=lab.lab_view(plan["id"]),
            fixes=_fixes(lab, plan["id"]),
            fixes_view=lab.fixes_view(plan["id"]),
        )
    finally:
        lab.stop()


def test_elliptic_import_and_verify_in_isolated_mode(elliptic):
    assert elliptic.imp["is_demo"] is False
    assert any(
        n.startswith("Real software: elliptic 6.5.6.") and "own locked-down container with no network" in n
        for n in notes_of(elliptic.imp)
    )
    (result,) = elliptic.verify["results"]
    assert result["result"] == TRUE, result["summary"]


def test_elliptic_first_run_exam_fails_on_exactly_case_6_and_tricks_pass(elliptic):
    lab, view = elliptic.lab, elliptic.first
    exam, tricks, speed = (result_of(view, kind) for kind in ("official_vectors", "bad_signatures", "speed_size"))
    assert (exam["label"], tricks["label"], speed["label"]) == ("Failed", "Passed", "Measured")
    seen = _result(lab, exam)
    assert [w["id"] for w in seen["detail"]["wrong"]] == ["6"], seen["detail"]["wrong"]
    assert exam["real"] is True and seen["component"] == "elliptic 6.5.6"
    assert [a["id"] for a in exam["advisories"]["items"]] == ["CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459"]
    assert exam["fix_line"]["rest"] == "update to the fixed version"
    assert any("does not catch CVE-2024-42460" in line for line in _result(lab, tricks)["shows"])


def test_elliptic_fixes_holds_a_text_only_update_with_its_advisories(elliptic):
    (fix,) = elliptic.fixes
    assert fix["title"] == "Update elliptic to the fixed version (6.5.7)"
    assert fix["kind"] == "text" and fix["pull_request"] is None and fix["buttons"] == []
    assert len(fix["advisory_links"]) == 3 and all(
        str(h).startswith("https://github.com/advisories/") for h in fix["advisory_links"]
    )


def test_a_retest_needs_a_registered_version_of_a_program_in_the_file(elliptic):
    from app.errors import BadRequest

    lab = elliptic.lab
    with pytest.raises(BadRequest):
        lab.start_retest(elliptic.pid, "9.9.9", "elliptic")  # not a registered version
    with pytest.raises(BadRequest):
        lab.start_retest(elliptic.pid, "17.0.3", "openjdk")  # a registered library, but not in this file
    with pytest.raises(BadRequest):
        lab.start_retest(elliptic.pid, "6.5.7", "not-a-library")  # not a library at all
    assert lab.lab_view(elliptic.pid)["view"] == "results"  # nothing was started


def test_retest_on_6_5_7_passes_and_the_evidence_carries_the_advisories(elliptic, tmp_path):
    lab, pid = elliptic.lab, elliptic.pid
    lab.start_retest(pid, "6.5.7", "elliptic")
    lab.wait_until_idle(pid, 900)
    view = lab.lab_view(pid)
    assert view["view"] == "before_after"
    assert view["columns"]["before"] == "Before: elliptic 6.5.6" and view["columns"]["after"] == "After: elliptic 6.5.7"
    exam, tricks, speed = (
        result_of(view, kind, "after") for kind in ("official_vectors", "bad_signatures", "speed_size")
    )
    assert (exam["label"], tricks["label"]) == ("Passed", "Passed")
    assert speed["label"] in ("No slowdown beyond measured noise", "Slowdown found"), speed["label"]
    assert _result(lab, exam)["component"] == "elliptic 6.5.7"
    assert [f["title"] for f in _fixes(lab, pid)] == [], (
        "the elliptic entry should be gone from Fixes once every test passes"
    )

    # Download evidence after the retest: the JSON (the record) and the readable report.
    made = lab.export_evidence(pid)
    _, raw, _ = lab.evidence_file(made["id"], "json")
    _, page, _ = lab.evidence_file(made["id"], "html")
    envelope = json.loads(raw)
    tests = {t["kind"]: t for t in envelope["evidence"]["tests"]}
    first_run = next(r for r in tests["official_vectors"]["runs"] if r["phase"] == "first")
    assert [a["id"] for a in first_run["result"]["advisories"]["items"]] == [
        "CVE-2024-42460",
        "CVE-2024-42461",
        "CVE-2024-42459",
    ]
    html = page.decode("utf-8")
    assert '<a href="https://github.com/advisories/' in html and "Published advisories for this version" in html

    # The way a person checks the file: python -m evidence verify (also the library call it uses).
    public = (lab.settings.data_dir / PUBLIC_KEY_FILE).read_text().strip()
    assert verify_bytes(raw, public).ok
    saved = tmp_path / "evidence.json"
    saved.write_bytes(raw)
    done = subprocess.run(
        [sys.executable, "-m", "evidence", "verify", str(saved), "--data-dir", str(lab.settings.data_dir)],
        cwd=BACKEND,
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0 and done.stdout.startswith("Evidence verified"), done.stdout + done.stderr
    # Last, so the checks above all run first: the report's before/after sentence names the library and both versions.
    assert "elliptic 6.5.6 and then on elliptic 6.5.7" in html, "the report should name both versions"


# ------------------------------------------------------------------ isolated mode: the ML-KEM-768 key exchange exam


def test_openssl_ml_kem_768_key_exchange_exam_passes(docker_ready, tmp_path):
    need(docker_ready, "openssl")
    lab = make_lab(tmp_path, force_mode=None)
    try:
        imp = lab.import_file("mlkem.csv", csv_bytes(KEM_ONLY))
        assert imp["is_demo"] is False
        (verify,) = lab.verify(imp["id"])["results"]
        assert verify["result"] == TRUE and "key exchange round trip" in verify["summary"], verify
        plan = lab.ensure_plan(imp["id"])
        assert [t["title"] for t in plan["tests"]] == ["Key exchange exam (ML-KEM-768)"]
        lab.run_all(plan["id"])
        lab.wait_until_idle(plan["id"], 600)
        view = lab.lab_view(plan["id"])
        assert [row["title"] for row in view["rows"]] == ["Key exchange exam (ML-KEM-768)"]
        exam = result_of(view, "mlkem_vectors")
        assert exam["label"] == "Passed", exam["plain"]
        seen = _result(lab, exam)
        parts = seen["detail"]["parts"]
        assert [(p["right"], p["cases"]) for p in parts] == [(125, 125), (300, 300), (230, 230)], parts
        assert all(p["control"]["of"] and p["control"]["caught"] == p["control"]["of"] for p in parts), (
            "every broken copy must be caught"
        )
        assert any("timing attacks" in line and "outside this test" in line for line in exam["shows"]), exam["shows"]
        # No Migration system for it: the file names no system, and a key exchange row never makes one.
        assert not any("ML-KEM" in s["name"] for s in lab.migration_view(plan["id"])["systems"])
    finally:
        lab.stop()
