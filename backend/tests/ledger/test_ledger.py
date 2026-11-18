"""Phase 5b: every check in one list, in the four work groups; each run in one row only; every row in the words of the
page it came from; links that hold both ways; and nothing in the ledger that could decide a result."""
import ast
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import ReviewRow, TestRunRow
from app.ledger import groups as G
from app.present import fixes as present_fixes
from tests.conftest import make_lab, demo_plan

LEDGER = Path(__file__).resolve().parents[2] / "app" / "ledger"


def _rows(view):
    return {r["id"]: r for g in view["groups"] for r in g["rows"]}


def test_the_four_groups_in_order_with_counts_and_every_claim_and_test_in_its_group(demo_flow):
    lab, plan = demo_flow.lab, demo_flow.plan
    view = lab.checks_view(plan.id)
    assert [g["label"] for g in view["groups"]] == ["Verification", "Encryption tests", "Migration", "Dependencies"]
    by = {g["key"]: g for g in view["groups"]}
    claims = by["verification"]["rows"]
    assert len(claims) == 3 and {r["came_from"]["label"] for r in claims} == {"Verify"}
    assert [r["result"]["label"] for r in claims] == ["False", "True", "True"]       # expected.json V1 to V3
    assert by["verification"]["counts"] == {"open": 0, "in_progress": 0, "done": 3}
    tests = [r for r in by["encryption"]["rows"] if r["came_from"]["key"] == "plan"]
    retests = [r for r in by["encryption"]["rows"] if r["came_from"]["key"] == "retest"]
    assert len(tests) == len(plan.item) and len(retests) == len(plan.item)
    assert by["encryption"]["counts"]["done"] == len(tests) + len(retests)
    # Nothing measured for Migration in this walk, and no dependency list: each says why it is empty.
    assert by["migration"]["rows"] == [] and by["migration"]["empty_text"] == G.EMPTY_CHECKS["migration"]
    assert by["migration"]["counts"]["open"] == 2                                   # the server and the signing program
    assert by["dependencies"]["empty_text"] == G.EMPTY_CHECKS["dependencies"]


def test_every_row_repeats_the_words_of_the_page_it_came_from(demo_flow):
    lab, plan = demo_flow.lab, demo_flow.plan
    rows = _rows(lab.checks_view(plan.id))
    lab_rows = {r["item_id"]: r for r in lab.lab_view(plan.id)["rows"]}
    for item_id, shown in lab_rows.items():
        first, retest = rows[f"test-{item_id}"], rows[f"retest-{item_id}"]
        assert first["result"]["label"] == shown["result"]["label"] and first["plain"] == shown["result"]["plain"]
        assert retest["result"]["label"] == shown["after"]["label"] and retest["plain"] == shown["after"]["plain"]
        assert first["name"] == shown["title"]
    verify = {r["claim_id"]: r for r in demo_flow.verify["results"]}
    for claim_id, res in verify.items():
        row = rows[f"claim-{claim_id}"]
        assert row["result"]["label"] == res["result"] and row["plain"] == res["summary"] and row["name"] == res["claim"]["text"]


def test_each_reviewed_run_is_in_exactly_one_row(demo_flow):
    lab, plan = demo_flow.lab, demo_flow.plan
    led = lab.ledger(plan.id)
    counted = [rid for r in led["rows"] for rid in r.get("run_ids") or []]
    assert len(counted) == len(set(counted))
    with lab.db() as db:
        reviewed = set(db.scalars(select(ReviewRow.run_id).join(TestRunRow, TestRunRow.id == ReviewRow.run_id)
                                  .where(TestRunRow.plan_id == plan.id)).all())
    assert reviewed <= set(counted)


def test_a_detail_has_its_newest_result_its_earlier_runs_and_links_back(demo_flow):
    lab, plan = demo_flow.lab, demo_flow.plan
    item = plan.item["tls_versions"]
    detail = lab.check_detail(plan.id, f"test-{item}")
    assert detail["result"]["label"] == detail["check"]["result"]["label"]
    assert detail["runs"] and detail["runs"][0]["fingerprint"] and len(detail["runs"][0]["fingerprint"]) == 64
    lines = {line["kind"]: line for line in detail["related"]}
    claim = lines["claim"]["items"][0]
    assert claim["label"].endswith("accepts TLS 1.3 only") and claim["sub"] == "False"
    assert claim["link"] == {"page": "inventory/verify", "item": claim["key"].replace("claim:", "claim-")}
    assert lines["fix"]["items"][0]["link"]["page"] == "fixes"
    assert lines["system"]["items"][0]["link"]["page"] == "migration/roadmap"
    # The claim's own Related block names the same test: the link holds both ways.
    back = {line["kind"]: line for line in lab.related(plan.id, claim["key"])}
    assert f"test:{item}" in {i["key"] for i in back["test"]["items"]}


def test_a_retested_check_is_related_by_the_version_its_newest_result_ran_on(demo_flow):
    """After a retest a test's newest result is on another version of the program. The Related block names that
    version beside the result, never the version the file names beside a result that version did not give."""
    lab, plan = demo_flow.lab, demo_flow.plan
    nodes = lab.relation_graph(plan.id)["nodes"]
    assert nodes[f"test:{plan.item['official_vectors']}"]["sub"] == "acme-sign 1.4.3 · Passed"
    assert nodes[f"test:{plan.item['bad_signatures']}"]["sub"] == "acme-sign 1.4.3 · Passed"
    server = nodes[f"test:{plan.item['tls_versions']}"]["sub"]          # a server test names its address, as before
    assert server.startswith("localhost:") and server.endswith(" · Failed")


def test_every_relation_is_recorded_both_ways(demo_flow):
    graph = demo_flow.lab.relation_graph(demo_flow.plan.id)
    for a, near in graph["edges"].items():
        for b in near:
            assert a in graph["edges"][b], (a, b)


def test_fixes_are_in_their_group_once_with_counts_and_links_to_where_they_came_from(demo_flow):
    view = demo_flow.lab.fixes_view(demo_flow.plan.id)
    assert [g["label"] for g in view["groups"]] == ["Verification", "Encryption tests", "Migration", "Dependencies"]
    listed = [fid for g in view["groups"] for fid in g["fix_ids"]]
    assert sorted(listed) == sorted(f["id"] for f in view["fixes"]) and len(listed) == len(set(listed))
    groups = {g["key"]: g for g in view["groups"]}
    assert groups["verification"]["empty_text"] == G.EMPTY_FIXES["verification"]
    for f in view["fixes"]:
        assert f["group"] in G.GROUP_KEYS and f["fix_state"] == G.fix_state(f["status"]["word"])
        if f["group"] == "encryption":
            assert f["came_from_links"] and all(link["link"]["page"] == "evidence" for link in f["came_from_links"])
    for g in view["groups"]:
        assert sum(g["counts"].values()) == len(g["fix_ids"])


def test_every_fix_status_word_the_app_can_show_is_sorted():
    words = set(present_fixes.STATUS_WORDS.values())
    source = (Path(__file__).resolve().parents[2] / "app" / "present" / "changes.py").read_text()
    badge_words = {"Text only", "In place (measured)", "Applied · matches the try", "Applied · does not match the try",
                   "Applied · measuring", "Ready to download", "Rolled back", "Try running", "Try did not pass",
                   "Ready to apply", "Try passed", "Waiting for approval", "Ready to try"}
    for word in badge_words:
        assert f'"{word}"' in source, word          # each is a real badge of the change box
    assert (words | badge_words) <= set(G.FIX_STATE_BY_WORD)
    assert G.fix_state("Merged") == G.fix_state("In place (measured)") == "done"


def test_the_ledger_imports_nothing_that_decides_a_result():
    for path in LEDGER.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                     [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert "reviewer" not in name and not name.startswith("app.run") and not name.startswith("app.checks"), (path.name, name)


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    """The Acme Pay demo verified and measured for Migration (no tests run): quick."""
    lab = make_lab(tmp_path_factory.mktemp("ledger-measured"))
    try:
        plan = demo_plan(lab)
        lab.verify(plan.imp["id"])
        lab.measure_migration(plan.id)
        lab.wait_until_measured(plan.id, 300)
        yield lab, plan
    finally:
        lab.stop()


def test_a_migration_measurement_is_a_check_in_migration_in_the_words_of_the_systems_page(measured):
    lab, plan = measured
    view = lab.checks_view(plan.id)
    migration = next(g for g in view["groups"] if g["key"] == "migration")
    systems = {s["key"]: s for s in lab.migration_view(plan.id)["systems"]}
    assert len(migration["rows"]) == len(systems) == 2
    for row in migration["rows"]:
        key = row["id"].removeprefix("system-")
        assert row["came_from"]["label"] == "Measure status" and row["link"] == {"page": "migration/systems", "item": key}
        assert row["result"]["label"] == systems[key]["status"]["label"]
    assert migration["counts"] == {"open": 0, "in_progress": 0, "done": 2}
    # Tests not run yet are open rows of the test plan, never results.
    encryption = next(g for g in view["groups"] if g["key"] == "encryption")
    assert encryption["counts"]["open"] == len(plan.item) and all(r["result"] is None for r in encryption["rows"])


def test_evidence_can_be_downloaded_after_only_a_verify_and_holds_every_check(tmp_path):
    lab = make_lab(tmp_path)
    try:
        plan = demo_plan(lab)
        assert lab.lab_view(plan.id)["download"]["can_start"] is False
        assert "Verify the claims first" in lab.lab_view(plan.id)["download"]["blocked_reason"]
        lab.verify(plan.imp["id"])
        lab.verify(plan.imp["id"])                                  # twice: every Verify run is kept in the file
        assert lab.lab_view(plan.id)["download"]["can_start"] is True
        export = lab.export_evidence(plan.id)
        from app.evidence.export import build_evidence
        evidence = build_evidence(lab, plan.id)
        assert len(evidence["verify_runs"]) == 2 and evidence["verify"] == evidence["verify_runs"][0]
        checks = {c["check"]: c for c in evidence["checks"]}
        claim_rows = [c for c in checks.values() if c["group"] == "verification"]
        assert len(claim_rows) == 3 and all(len(c["runs"]) == 2 and c["came_from"] == "Verify" for c in claim_rows)
        assert export["fingerprint"]
    finally:
        lab.stop()


def test_the_overview_counts_each_test_once_by_its_newest_result_as_evidence_shows_it(demo_flow):
    """Every test of this walk was retested: the Overview counts each test once, by the result Evidence leads with (the
    after result), never the first and the retest side by side."""
    lab, plan = demo_flow.lab, demo_flow.plan
    blocks = lab.assessment_blocks(plan.imp["id"], plan.id)
    encryption = next(g for g in blocks["groups"] if g["key"] == "encryption")
    newest = [row.get("after") or row.get("result") for row in lab.lab_view(plan.id)["rows"]]
    newest = [r for r in newest if r]
    assert sum(f["value"] for f in encryption["facts"]) == len(newest) == len(plan.item)
    failed = next(f for f in blocks["findings"] if f["label"] == "Failed tests")["value"]
    assert failed == sum(1 for r in newest if r["code"] == "failed")
    # The Projects table and the Project overview read the same: one result per test.
    from app.projects.counts import assessment_counts
    assert failed == assessment_counts(lab, plan.imp["id"])["tests"]["failed"]


def test_the_same_measurement_in_two_places_is_marked_on_both_with_links(measured):
    """Plan decision 4: a signing program's Verify claim and its Measure status run the same measurement. Each keeps its
    own run and result; each names the other, with a link to it on Checks."""
    lab, plan = measured
    rows = _rows(lab.checks_view(plan.id))
    claim = next(r for r in rows.values() if r["kind"] == "verify" and r["ran_on"] == "acme-sign 1.4.2")
    system = next(r for r in rows.values() if r["kind"] == "signing_status")
    assert [o["id"] for o in claim["same_as"]] == [system["id"]]
    assert [o["id"] for o in system["same_as"]] == [claim["id"]]
    assert claim["same_as"][0]["link"] == {"page": "checks", "item": system["id"]}
    # A claim about something else is not marked.
    tls = next(r for r in rows.values() if r["kind"] == "verify" and "TLS" in r["name"])
    assert tls["same_as"] == []


def test_migration_links_the_readiness_test_and_the_post_quantum_claim_from_its_foot():
    """Plan decision 3: the Post-quantum readiness test sits in Encryption tests and Verify's post-quantum claim in
    Verification; Migration links both from its foot, as the same measurement as Measure status. Neither is moved or
    counted twice."""
    from app.ledger.checks import LedgerMixin, _measure_key
    link = {"page": "evidence", "item": "x"}
    claim = {"id": "claim-4", "group": "verification", "kind": "verify", "name": "localhost:8451 is post-quantum",
             "ran_on": "localhost:8451", "evidence_link": link,
             "verify": {"claim": {"location_kind": "server", "kind": "post_quantum", "location": "localhost:8451"}}}
    test = {"id": "test-7", "group": "encryption", "kind": "pq_readiness", "name": "Post-quantum readiness",
            "ran_on": "localhost:8451", "evidence_link": link}
    system = {"id": "system-server:localhost:8451", "group": "migration", "kind": "pq_status", "name": "Post-quantum status",
              "ran_on": "localhost:8451", "evidence_link": link}
    other = {"id": "test-8", "group": "encryption", "kind": "tls_versions", "name": "Old TLS versions",
             "ran_on": "localhost:8451", "evidence_link": link}

    def public(r):
        out = dict(r)
        out["measures"] = _measure_key(dict(r))
        if r["kind"] == "verify":
            out["pq_claim"] = True
        out.pop("verify", None)
        return out
    groups = [{"key": "verification", "label": "Verification", "rows": [public(claim)]},
              {"key": "encryption", "label": "Encryption tests", "rows": [public(test), public(other)]},
              {"key": "migration", "label": "Migration", "rows": [public(system)]},
              {"key": "dependencies", "label": "Dependencies", "rows": []}]
    LedgerMixin._mark_same_measurements(groups)
    by = {g["key"]: g for g in groups}
    assert [a["id"] for a in by["migration"]["also"]] == ["claim-4", "test-7"]
    assert by["verification"]["also"] == [] and by["encryption"]["also"] == []
    assert {o["id"] for o in by["migration"]["rows"][0]["same_as"]} == {"claim-4", "test-7"}
    assert by["encryption"]["rows"][1]["same_as"] == []                                # another test is not marked
    assert all("measures" not in r and "pq_claim" not in r for g in groups for r in g["rows"])


def test_the_dependencies_group_counts_the_same_on_checks_evidence_and_the_overview(measured):
    """One rule on every page: a library of the list is done once answered (release notes or a measurement)."""
    lab, plan = measured
    data = (Path(__file__).resolve().parents[3] / "demo" / "dependencies-demo.cdx.json").read_bytes()
    lab.add_dependency_list(plan.id, "dependencies-demo.cdx.json", data)
    view = lab.checks_view(plan.id)
    deps = next(g for g in view["groups"] if g["key"] == "dependencies")
    by_state = G.counts(lib["state"] for lib in view["libraries"])
    assert deps["counts"] == view["evidence_counts"]["dependencies"] == by_state
    assert by_state["done"] == sum(1 for lib in view["libraries"] if any(c["answer"] in ("yes", "no") for c in lib["cells"]))
    blocks = lab.assessment_blocks(plan.imp["id"], plan.id)
    assert next(g for g in blocks["groups"] if g["key"] == "dependencies")["checks"] == by_state


def test_the_overview_checks_and_related_only_read_they_never_lock_a_measurement(tmp_path):
    """Phase 5b's pages repeat what the other pages say. Looking at them writes nothing down: before Migration is
    opened, no measurement of it is locked by the Overview, Checks, Related or the Project overview."""
    from app.db import PlanItemRow, TestSpecRow
    lab = make_lab(tmp_path)
    try:
        plan = demo_plan(lab)
        lab.verify(plan.imp["id"])

        def written():
            with lab.db() as db:
                return (db.query(TestSpecRow).count(),
                        db.query(PlanItemRow).filter(PlanItemRow.plan_id == plan.id, PlanItemRow.origin == "migration").count())
        before = written()
        lab.assessment_blocks(plan.imp["id"], plan.id)
        lab.checks_view(plan.id)
        graph = lab.relation_graph(plan.id)
        assert written() == before and before[1] == 0
        # The systems the file names are still there to link to, not measured yet.
        systems = [n for n in graph["nodes"].values() if n["kind"] == "system"]
        assert {n["label"] for n in systems} == {"localhost:" + str(lab.settings.demo_tls_port), "acme-sign 1.4.2"}
        assert all(n["sub"] == "Not measured yet" for n in systems)
    finally:
        lab.stop()
