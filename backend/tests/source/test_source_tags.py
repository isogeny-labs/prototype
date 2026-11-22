"""Where it came from (22 November 2026): every result, system status and fix of the Acme Pay demo carries exactly one tag,
the right one, placed on the item the pages already show; reading a page still changes nothing; and the views keep the
shape the screens receive. The expected tag is worked out here from what each item ran on, apart from the app's rule.

Two walks. A fresh assessment (Verify, the dependency list; no test run yet) is quick and stays in the fast set. The
whole demo (every test, a retest, Measure status, a try, Apply and Roll back of the TLS fix) is long and is in the slow
set (`SLOW_SHARED_WALKS`)."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.web import models
from tests.assistant.assistant_walk import everything_kept
from tests.conftest import demo_plan, make_lab
from tests.view_helpers import problems

REPO = Path(__file__).resolve().parents[3]
DEMO_LIST = REPO / "demo" / "dependencies-demo.cdx.json"
SERVER_TESTS = {"tls_versions", "certificate", "pq_readiness"}
NO_RESULT = {"couldnt_run", "couldnt_trust", "couldnt_check"}
LABELS = {"live": "Observed live", "lab": "Proven in the lab", "file": "From your file", "published": "Published"}
BANNED = re.compile(r"\bsecure\b|\bscore\b|\bseverity\b", re.I)


def _setup(tmp_path) -> SimpleNamespace:
    lab = make_lab(tmp_path)
    plan = demo_plan(lab)
    verify = lab.verify(plan.imp["id"])
    deps = lab.add_dependency_list(plan.id, DEMO_LIST.name, DEMO_LIST.read_bytes())
    pay = next(g for g in deps["groups"] if g["label"] == "acme-pay-server 1.0.0")
    lab.tie_dependency(plan.id, pay["key"], f"server:{lab.settings.demo_address}")
    return SimpleNamespace(lab=lab, plan=plan, pid=plan.id, imp=plan.imp, verify=verify)


def _views(walk) -> dict:
    lab, pid = walk.lab, walk.pid
    return {"import": lab.import_json_for(walk.imp["id"]), "verify": walk.verify,
            "checks": lab.checks_view(pid), "lab": lab.lab_view(pid), "migration": lab.migration_view(pid),
            "dependencies": lab.dependencies_view(pid), "fixes": lab.fixes_view(pid), "advisories": lab.advisories_view(pid),
            "overview": lab.assessment_blocks(walk.imp["id"], pid)}


def _claim_kinds(walk) -> dict:
    return {r["claim"]["text"]: r["claim"]["location_kind"] for r in walk.verify["results"]}


def _expected_row(row: dict, claim_kinds: dict) -> str | None:
    """What a Checks row rests on, worked out from what it ran on."""
    code = (row.get("result") or {}).get("code")
    origin, kind = row["came_from"]["key"], row["kind"]
    if kind == "verify":
        if row["result"]["label"] not in ("True", "False"):
            return "file"
        return "live" if claim_kinds[row["name"]] == "server" else "lab"
    if code is None:
        return None
    if code in NO_RESULT:
        # only Measure status leaves a system's status on the file; a try, After Apply or Roll back that couldn't measure has none
        return "file" if origin == "measure" and kind in ("pq_status", "signing_status") else None
    if origin == "try":
        return "lab"
    if origin in ("after_apply", "after_rollback") or kind == "pq_status" or kind in SERVER_TESTS:
        return "live"
    return "lab"


def _key(tag) -> str | None:
    return tag["key"] if tag else None


def _every_tag(value, out=None):
    """Every tag anywhere in a view (a dict with a key and the words of one of the four)."""
    out = [] if out is None else out
    if isinstance(value, dict):
        if set(value) >= {"key", "label", "meaning"} and value.get("key") in LABELS:
            out.append(value)
        for v in value.values():
            _every_tag(v, out)
    elif isinstance(value, list):
        for v in value:
            _every_tag(v, out)
    return out


def _check_rows(view: dict) -> list[dict]:
    rows = []
    for g in view["groups"]:
        rows += g["rows"]
        parts = g.get("parts") or {}
        for name in ("retests", "proofs", "changes"):
            rows += [r for b in ((parts.get(name) or {}).get("blocks") or []) for r in b["rows"]]
        rows += ((parts.get("tries") or {}).get("rows") or [])
    return rows


def _assert_views(walk, views: dict) -> None:
    kinds = _claim_kinds(walk)
    # every tag says one of the four, in Kevin's words, with what it means, and no score and no severity
    for name, view in views.items():
        for tag in _every_tag(view):
            assert tag["label"] == LABELS[tag["key"]] and tag["meaning"], name
            assert not any(BANNED.search(str(tag.get(k) or "")) for k in ("label", "meaning", "note")), (name, tag)
    # Import: every claim is from the file until Verify checks it
    assert _key(views["import"]["claim_source_tag"]) == "file"
    # Verify: a server claim is live, the program's claim lab
    for r in walk.verify["results"]:
        want = "live" if r["claim"]["location_kind"] == "server" else "lab"
        assert _key(r["source_tag"]) == (want if r["result"] in ("True", "False") else "file")
    # Checks (and Evidence's other groups): exactly one tag, the right one, on every row that rests on something
    for row in _check_rows(views["checks"]):
        assert _key(row["source_tag"]) == _expected_row(row, kinds), (row["id"], row["kind"], row["came_from"], row["result"])
    # Evidence: each side of every result its own
    for row in views["lab"]["rows"]:
        for side in ("result", "after"):
            shown = row[side]
            want = None if shown is None or shown["code"] in NO_RESULT else ("live" if row["kind"] in SERVER_TESTS else "lab")
            assert _key((shown or {}).get("source_tag")) == want, (row["title"], side)
    # Migration: a server's status is live, a signing program's lab, before a measurement the file
    for system in views["migration"]["systems"]:
        code = system["status"]["code"]
        want = "file" if code in ("not_measured", "couldnt_check") else ("live" if system["kind_label"] == "Server" else "lab")
        assert _key(system["source_tag"]) == want, system["name"]
    # Dependencies: each library is from the list; each answer by the label it already carries
    for g in views["dependencies"]["groups"]:
        for r in g["rows"]:
            assert _key(r["source_tag"]) == "file"
            for c in r["cells"]:
                want = {"release_notes": "published", "public_copy": "lab"}.get(c["label"] or "",
                                                                                   "published" if c["answer"] == "doesnt_apply" else "file")
                assert _key(c["source_tag"]) == want, (r["label"], c["question"], c["answer"], c["label"])
    # Fixes: every fix has exactly one tag for what it came from
    for fix in views["fixes"]["fixes"]:
        assert fix["source_tag"] is not None, fix["id"]
        if fix["id"].startswith("fix-tls"):
            assert _key(fix["source_tag"]) == "live"
        elif fix["id"].startswith("dependency-"):
            assert _key(fix["source_tag"]) == "file"
        elif fix["kind"] == "code":
            assert _key(fix["source_tag"]) == "lab"
    # The Overview counts what Checks counts, by tag
    checks = {g["key"]: g for g in views["checks"]["groups"]}
    for g in views["overview"]["groups"]:
        assert g["source_counts"] == checks[g["key"]]["source_counts"], g["key"]
    # the views keep the shape the screens receive
    for name, shape in (("checks", models.ChecksView), ("lab", models.LabView), ("migration", models.MigrationView),
                        ("dependencies", models.DependenciesView), ("fixes", models.FixesView), ("import", models.Import),
                        ("overview", models.OverviewBlocks)):
        assert problems(views[name], shape, name) == [], name


@pytest.fixture
def fresh(tmp_path):
    walk = _setup(tmp_path)
    try:
        yield walk
    finally:
        walk.lab.stop()


def test_a_fresh_assessment_every_claim_answer_and_system_says_what_it_rests_on(fresh):
    lab = fresh.lab
    # (opening the Migration page writes each system's measurement down and locks it, once, by design since phase 4a: so
    # every page is opened once, as a person would, and then a read must change nothing)
    _views(fresh)
    before = everything_kept(lab)
    views = _views(fresh)
    _assert_views(fresh, views)
    # nothing has run: no test of the plan has a tag; the systems rest on the file; the claims are what Verify read
    assert all(r["source_tag"] is None for r in _check_rows(views["checks"]) if r["kind"] not in ("verify",))
    assert {_key(s["source_tag"]) for s in views["migration"]["systems"]} == {"file"}
    verification = next(g for g in views["checks"]["groups"] if g["key"] == "verification")
    assert [(c["key"], c["count"]) for c in verification["source_counts"]] == [("live", 2), ("lab", 1)]
    migration = next(g for g in views["checks"]["groups"] if g["key"] == "migration")
    assert [(c["key"], c["count"]) for c in migration["source_counts"]] == [("file", 2)]     # a server and a program, not measured
    # reading every page wrote nothing and started nothing, and reads the same again
    assert everything_kept(lab) == before and not lab.jobs.live(fresh.pid)
    assert _every_tag(_views(fresh)) == _every_tag(views)


@pytest.fixture(scope="module")
def tagged(tmp_path_factory):
    walk = _setup(tmp_path_factory.mktemp("source-tags"))
    lab, pid = walk.lab, walk.pid
    try:
        lab.run_all(pid)
        lab.wait_until_idle(pid, 300)
        lab.start_retest(pid, "1.4.3")
        lab.wait_until_idle(pid, 300)
        lab.measure_migration(pid)
        lab.wait_until_measured(pid, 300)
        walk.ran = _views(walk)
        fix = next(f for f in lab.fixes_view(pid)["fixes"] if f["id"].startswith("fix-tls"))
        key = fix["change_box"]["id"]
        lab.try_change(pid, key)
        lab.wait_until_changes_idle(pid)
        walk.tried = _views(walk)
        lab.ask_approval(pid, key, ["you"])
        lab.approve_change(pid, key, "you")
        lab.apply_change(pid, key)
        lab.wait_until_changes_idle(pid)
        walk.applied = _views(walk)
        lab.rollback_change(pid, key)
        lab.wait_until_changes_idle(pid)
        walk.rolled = _views(walk)
        walk.key = key
        yield walk
    finally:
        lab.stop()


@pytest.mark.parametrize("stage", ["ran", "tried", "applied", "rolled"])
def test_every_result_status_and_fix_of_the_whole_demo_carries_exactly_one_right_tag(tagged, stage):
    _assert_views(tagged, getattr(tagged, stage))


def test_crypto_tests_mixes_live_server_tests_and_lab_program_tests_and_verification_mixes_too(tagged):
    rows = {r["name"]: _key(r["source_tag"]) for g in tagged.ran["checks"]["groups"] if g["key"] == "encryption" for r in g["rows"]
            if r["id"].startswith("test-")}
    assert rows["Old TLS versions"] == "live" and rows["Certificate strength"] == "live"
    assert rows["Independent exam (Wycheproof)"] == "lab" and rows["Attacker tricks (our short list)"] == "lab"
    systems = {s["kind_label"]: _key(s["source_tag"]) for s in tagged.ran["migration"]["systems"]}
    assert systems == {"Server": "live", "Signing program": "lab"}


def test_the_try_box_says_where_each_column_came_from_and_after_apply_and_roll_back_are_live(tagged):
    def box(views):
        return next(f for f in views["fixes"]["fixes"] if f["id"].startswith("fix-tls"))["change_box"]
    tried = box(tagged.tried)
    # the label column, the server as measured before (live), the test copy (lab), and real nginx, which needs isolated
    # mode: skipped here, so it rests on nothing and has no tag
    assert [_key(t) for t in tried["try"]["column_source_tags"]] == [None, "live", "lab", None]
    assert tried["try"]["columns"][3].startswith("After:") and "Not tried" in "".join(p["v"] for p in tried["try"]["rows"][0]["cells"][2])
    assert _key(tried["try"]["source_tag"]) == "lab"
    # the small tags in the table keep their words and get their source's look
    cells = [p for row in tried["try"]["rows"] for cell in row["cells"] for p in cell if p["t"] == "tag"]
    assert {(p["v"], p.get("s")) for p in cells} >= {("measured", "live"), ("measured on the copy", "lab")}
    assert _key(box(tagged.applied)["applied"]["source_tag"]) == "live"
    assert "right after the change was applied" in box(tagged.applied)["applied"]["source_tag"]["note"]
    assert _key(box(tagged.rolled)["applied"]["source_tag"]) == "live"
    assert "earlier settings were put back" in box(tagged.rolled)["applied"]["source_tag"]["note"]
    # Checks lists the measurement after Apply as live, the try as lab
    rows = _check_rows(tagged.applied["checks"])
    assert any(r["came_from"]["key"] == "after_apply" and _key(r["source_tag"]) == "live" for r in rows)
    assert any(r["came_from"]["key"] == "try" and _key(r["source_tag"]) == "lab" for r in rows)


def test_the_cost_table_keeps_its_words_and_gives_each_small_tag_its_sources_look(tagged):
    server = next(s for s in tagged.ran["migration"]["systems"] if s["kind_label"] == "Server")
    program = next(s for s in tagged.ran["migration"]["systems"] if s["kind_label"] == "Signing program")
    def tags(system):
        return {(p["v"], p.get("s")) for row in (system["cost"] or {}).get("rows") or [] for cell in row["cells"] for p in cell if p["t"] == "tag"}
    assert ("measured", "live") in tags(server) and ("measured on our test server", "lab") in tags(server)
    assert any(v.startswith("published") and s == "published" for v, s in tags(server))
    assert ("measured", "lab") in tags(program)        # a signing program is measured by running a copy of it here


def test_a_retests_after_side_and_a_proof_rerun_of_a_server_test_stay_live(tagged):
    row = next(r for r in tagged.ran["lab"]["rows"] if r["kind"] == "tls_versions")
    assert _key(row["result"]["source_tag"]) == "live" and _key(row["after"]["source_tag"]) == "live"
    wy = next(r for r in tagged.ran["lab"]["rows"] if r["kind"] == "official_vectors")
    assert _key(wy["result"]["source_tag"]) == "lab" and "acme-sign 1.4.2" in wy["result"]["source_tag"]["note"]
    assert "acme-sign 1.4.3" in wy["after"]["source_tag"]["note"]


def test_reading_every_page_after_the_whole_demo_writes_nothing_and_starts_nothing(tagged):
    before = everything_kept(tagged.lab)
    again = _views(tagged)
    assert everything_kept(tagged.lab) == before and not tagged.lab.jobs.live(tagged.pid)
    assert _every_tag(again) == _every_tag(tagged.rolled)
