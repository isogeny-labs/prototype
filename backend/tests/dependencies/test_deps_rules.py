"""Phase 4d: the rules the answer key relies on, on the Lab itself in demo mode: tying a top entry, the blocker rule,
the label rule, the Fixes entry, the records that only accept new rows, and that an import with no list is exactly as
it was before this phase."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import make_lab

from app.dependencies import state as dep_state
from app.dependencies.target import LABELS, label_of

REPO = Path(__file__).resolve().parents[3]
CDX = (REPO / "demo/dependencies-demo.cdx.json").read_bytes()


@pytest.fixture
def lab(tmp_path):
    lab = make_lab(tmp_path)
    yield lab
    lab.stop()


def _start(lab, data: bytes | None = CDX):
    imp = lab.import_demo()
    for address in imp["addresses"]:
        lab.confirm_address(imp["id"], address["address"], True)
    pid = lab.ensure_plan(imp["id"])["id"]
    view = lab.add_dependency_list(pid, "list.json", data) if data else lab.dependencies_view(pid)
    return imp, pid, view


def _group(view, label):
    return next(g for g in view["groups"] if g["label"] == label)


def _server(view):
    return next(o["key"] for o in view["groups"][0]["picker"]["options"] if o["key"].startswith("server:"))


def test_a_top_entry_equal_to_a_program_of_the_file_is_tied_by_name_and_version(lab):
    _, _, view = _start(lab)
    sign = _group(view, "acme-sign 1.4.2")
    assert sign["tie_source"] == "name_version" and sign["system"].startswith("software:") and sign["rows"] == []
    assert sign["tie_words"] == "Part of acme-sign 1.4.2, tied by name and version."


def test_the_persons_tie_overrides_and_none_of_these_unties(lab):
    _, pid, view = _start(lab)
    sign = _group(view, "acme-sign 1.4.2")
    view = lab.tie_dependency(pid, sign["key"], None)
    assert _group(view, "acme-sign 1.4.2")["system"] is None and _group(view, "acme-sign 1.4.2")["tie_source"] == "user"
    view = lab.tie_dependency(pid, sign["key"], sign["system"])
    assert _group(view, "acme-sign 1.4.2")["tie_words"].endswith("set by you.")


def test_an_untied_entry_answers_but_blocks_nothing(lab):
    _, _, view = _start(lab)
    assert [s["name"] for s in view["systems"]] == ["acme-sign 1.4.2"]  # only the tie the app made itself
    assert all(r["blocks"] == [] for g in view["groups"] for r in g["rows"])
    ledger = _group(view, "acme-ledger 5.1.0")
    assert ledger["tie_words"] == "Not tied to a system in your file: its libraries are answered and block nothing."


def test_the_blocker_rule_by_track_and_kind_of_library(lab):
    _, pid, view = _start(lab)
    server = _server(view)
    # acme-ledger has OpenJDK 17.0.2 (tls, key exchange, signatures: no on all three) and python-ecdsa (signatures only)
    view = lab.tie_dependency(pid, _group(view, "acme-ledger 5.1.0")["key"], server)
    system = next(s for s in view["systems"] if s["key"] == server)
    lines = [line["text"] for line in system["blocker_lines"]]
    # a server's tracks look only at TLS libraries: openjdk and the Go standard library 1.23.4 block; python-ecdsa and
    # elliptic (no tls role) never block a server, whatever they answer
    assert any("openjdk 17.0.2" in t for t in lines) and any("Go standard library 1.23.4" in t for t in lines)
    assert not any("python-ecdsa" in t or "elliptic" in t or "openssl 3.5.9" in t for t in lines)
    # libraries without a yes or no are things to check, never blockers
    assert not any(w in " ".join(lines) for w in ("wolfssl", "boringssl", "devel"))
    # no yes or no on any question that applies: python-ecdsa, elliptic, wolfssl, Go devel, boringssl
    assert system["without_answer"] == 5


def test_a_signing_program_is_blocked_only_by_a_signatures_library(lab):
    _, pid, view = _start(lab)
    sign = _group(view, "acme-sign 1.4.2")
    view = lab.tie_dependency(pid, _group(view, "acme-ledger 5.1.0")["key"], sign["system"])
    system = next(s for s in view["systems"] if s["key"] == sign["system"])
    lines = " ".join(line["text"] for line in system["blocker_lines"])
    assert "Blocks its signatures track: openjdk 17.0.2" in lines and "Go standard library 1.23.4" in lines
    assert "key exchange" not in lines and "authentication" not in lines


def test_the_label_rule_your_environment_is_never_produced():
    assert label_of("public_copy") == "public_copy" and label_of(None) is None and label_of("anything else") is None
    assert LABELS["your_environment"] == "your_environment"  # defined for Level 3 ...
    from app.real_libraries import CAPABILITY_COPIES

    copies = [c for versions in CAPABILITY_COPIES.values() for c in versions.values()]
    assert copies and all("target_kind" not in c for c in copies)  # ... and no copy is anything but a public one


def test_the_label_rule_on_every_answer_of_the_demo_list(lab):
    _, pid, view = _start(lab)
    lab.tie_dependency(pid, _group(view, "acme-pay-server 1.0.0")["key"], _server(view))
    text_of_everything = json.dumps(lab.dependencies_view(pid))
    for r in (r for g in lab.dependencies_view(pid)["groups"] for r in g["rows"]):
        for c in r["cells"]:
            if c["answer"] in ("yes", "no"):
                assert c["label"] in ("release_notes", "public_copy") and c["label_words"] and c["reason"]
            else:
                assert c["label"] is None and c["reason"]
            assert c["tone"] == "neutral" or c["state"] == "measured"  # a lookup is never a pass
    assert "Measured in your environment" not in text_of_everything
    for word in ("secure", "score", "time to hack", "safe"):
        assert word not in text_of_everything.lower().replace("doesn't prove a system secure", "")


def test_one_fixes_entry_per_blocking_library_and_system(lab):
    _, pid, view = _start(lab)
    server = _server(view)
    view = lab.tie_dependency(pid, _group(view, "acme-pay-server 1.0.0")["key"], server)
    fixes = [f for f in lab.fixes_view(pid)["fixes"] if f["id"].startswith("dependency-")]
    row = next(r for r in _group(view, "acme-pay-server 1.0.0")["rows"] if r["label"] == "openssl 3.0.22")
    assert [f["title"] for f in fixes] == ["Update OpenSSL to 3.5.0 or later"] and fixes[0]["kind"] == "text"
    assert (
        fixes[0]["actions"]["buttons"] == [] and fixes[0]["pull_request"] is None
    )  # text only: no code, no pull request
    assert {b["fix_id"] for b in row["blocks"]} == {fixes[0]["id"]}  # one entry for both tracks
    assert fixes[0]["id"] == dep_state.fix_id_for(
        server, next(r["key"] for r in _rows_of(lab, pid) if r["label"] == "openssl 3.0.22")
    )


def _rows_of(lab, pid):
    with lab.db() as db:
        return lab._dependency_state(db, lab._plan(db, pid))["rows"]


def test_a_newer_list_replaces_the_older_one_and_its_ties_start_over(lab):
    _, pid, view = _start(lab)
    lab.tie_dependency(pid, _group(view, "acme-pay-server 1.0.0")["key"], _server(view))
    view = lab.add_dependency_list(pid, "again.json", CDX)
    assert _group(view, "acme-pay-server 1.0.0")["system"] is None and view["list_file"]["filename"] == "again.json"


@pytest.mark.parametrize("table, column", [("dependency_lists", "filename"), ("dependency_ties", "system_key")])
def test_raw_sql_cannot_change_or_delete(lab, table, column):
    _, pid, view = _start(lab)
    lab.tie_dependency(pid, _group(view, "acme-pay-server 1.0.0")["key"], _server(view))
    with lab.db() as db:
        before = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert before > 0
        for statement in (f"UPDATE {table} SET {column} = 'x'", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == before


@pytest.mark.slow  # over 5 s on a slow machine (17 November 2026); runs with --full
def test_an_import_with_no_list_is_exactly_as_before(lab, monkeypatch):
    """With no list, the Migration and Fixes views must be what they were before phase 4d: the same as when the
    dependency part is switched off altogether."""
    _, pid, _ = _start(lab, None)
    lab.measure_migration(pid)
    lab.wait_until_measured(pid, 120)
    migration, fixes = lab.migration_view(pid), lab.fixes_view(pid)
    with lab.db() as db:
        assert lab._dependency_blockers(db, lab._plan(db, pid)) == {}
    monkeypatch.setattr(type(lab), "_dependency_blockers", lambda self, db, plan: {})
    monkeypatch.setattr(type(lab), "_fixes_for_dependencies", lambda self, db, plan, items, shown: [])
    assert lab.migration_view(pid) == migration and lab.fixes_view(pid) == fixes
    assert "dependency" not in json.dumps(migration).lower().replace('"dependencies": "dependencies"', "")


def test_view_in_fixes_works_before_anything_is_measured(lab):
    """A blocker's Fixes entry opens the Fixes step even when Migration has measured nothing yet."""
    imp, pid, view = _start(lab)
    assert lab.plan_view(pid)["has_migration"] is False
    lab.tie_dependency(pid, _group(view, "acme-pay-server 1.0.0")["key"], _server(view))
    assert lab.plan_view(pid)["has_migration"] is True


def test_a_measured_no_never_names_a_first_version_the_copy_is_already_past():
    from app.dependencies.state import DependenciesMixin
    from app.knowledge.base import knowledge_base

    kb = knowledge_base()
    entry = kb.find("pkg:generic/openssl", "openssl")
    measured = {
        "code": "measured",
        "target_kind": "public_copy",
        "detail": {"answers": {"ml_dsa_65": "no"}, "library_says": {"ml_dsa_65": "unsupported"}},
    }
    newer = DependenciesMixin._answer(
        "ml_dsa_65",
        kb.look_up("pkg:generic/openssl@3.5.9", "openssl", "3.5.9")["ml_dsa_65"],
        True,
        True,
        True,
        measured,
        entry,
        kb,
        "3.5.9",
    )
    assert (newer["answer"], newer["first_version"], newer["agreement"]) == ("no", "none_known", "differs")
    older = DependenciesMixin._answer(
        "ml_dsa_65",
        kb.look_up("pkg:generic/openssl@3.0.22", "openssl", "3.0.22")["ml_dsa_65"],
        True,
        True,
        True,
        measured,
        entry,
        kb,
        "3.0.22",
    )
    assert (older["answer"], older["first_version"], older["agreement"]) == ("no", "3.5.0", "agrees")
