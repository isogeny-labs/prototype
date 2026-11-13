"""The eight web routes of the Fixes step: login, ids, bodies, every refusal with its sentence, the patch
download, and that nothing happens unless its own route is called. One small plan is driven through the routes
once (old TLS versions, certificate strength, bad signatures); the tests read what each call answered."""
import hashlib
import re
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import components
from app.config import DEMO_CBOM, Settings
from app.db import ApprovalRow, ChangeRow, CodeConnectionRow, MergeRow, ProofRow, PullRequestRow, RetestRow
from app.gitrepo import GitRepo
from app.main import ApproveBody, PullRequestBody, create_app
from conftest import PASSWORD, free_port, upload
from fixes_shapes import FIXES_VIEW, LAB_VIEW, fix as fix_of, problems
from test_fixes_view import held
from test_gitrepo import real_git
from test_plan_api import start, wait

FIX, TLS = "fix-ecdsa-range-check", "fix-tls-versions"
OLD_FILE = components.lookup("acme-sign", "1.4.2").read_bytes()
NEW_FILE = components.lookup("acme-sign", "1.4.3").read_bytes()
NO_FIX = "That fix does not exist."
NO_PLAN = "That test plan does not exist."
RUN_FIRST = "Run every test in the plan first, so there is a result to compare with."
PROOF_RUNNING = "A proof is running in Fixes. Wait until it has finished."
TEXT_ONLY = "This fix is a text-only suggestion: there is no code change to act on."
PICK = "Pick one or more reviewers from the list, each of them once."
# The eight routes, as (method, the path after /api/plans/<plan>/fixes, a body it accepts).
ROUTES = [("GET", "", None), ("POST", "/connect", None), ("POST", "/{fix}/proof", None), ("POST", "/{fix}/pull-request", {"reviewers": ["you"]}),
          ("POST", "/{fix}/approve", {"reviewer": "you"}), ("POST", "/{fix}/merge", None), ("POST", "/{fix}/retest", None),
          ("GET", "/{fix}/patch", None)]
FIX_ROUTES = [route for route in ROUTES if "{fix}" in route[1]]


def call(client, plan_id, route, fix_id=FIX, body="default"):
    method, tail, default = route
    return client.request(method, f"/api/plans/{plan_id}/fixes{tail.format(fix=fix_id)}", json=default if body == "default" else body)


def refused(response, status=409) -> str:
    """The sentence a refused call answers with (and that it is the app's usual error shape)."""
    assert response.status_code == status, (response.status_code, response.text[:200])
    assert set(response.json()) == {"error"} and set(response.json()["error"]) == {"message", "line", "field"}
    return response.json()["error"]["message"]


def counts(lab) -> dict:
    with lab.db() as db:
        return {name: db.query(row).count() for name, row in (("connections", CodeConnectionRow), ("changes", ChangeRow), ("proofs", ProofRow),
                                                              ("pull_requests", PullRequestRow), ("approvals", ApprovalRow), ("merges", MergeRow),
                                                              ("retests", RetestRow))}


def main_branch(lab, plan_id) -> str | None:
    with lab.db() as db:
        row = db.query(CodeConnectionRow).filter_by(plan_id=plan_id).one_or_none()
    return GitRepo(lab.settings.data_dir / row.folder).branch("main") if row is not None else None


def small_plan(client) -> tuple[dict, int, dict]:
    imp = start(client)
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    items = {t["kind"]: t["id"] for t in plan["tests"]}
    for kind in ("official_vectors", "speed_size"):
        assert client.post(f"/api/plans/{plan['id']}/tests/{items.pop(kind)}/remove").status_code == 200
    return imp, plan["id"], items


@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    settings = Settings(data_dir=tmp_path_factory.mktemp("fixes-api") / "data", demo_tls_port=free_port(), force_mode="demo",
                        speed_rounds=25, speed_repeats=4)
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        yield client


@pytest.fixture(scope="module")
def api(app_client):
    """One plan taken through every route, in the order a person would press the buttons, with what each call
    answered. The proof fails first (the server's address is unconfirmed while it runs) and is then run again."""
    client, lab = app_client, app_client.app.state.lab
    imp, pid, items = small_plan(client)
    address = imp["addresses"][0]["address"]
    s = SimpleNamespace(client=client, lab=lab, pid=pid, items=items, steps={}, counts={})

    def go(route_tail: str, body="default", fix_id=FIX):
        return call(client, pid, next(r for r in ROUTES if r[1] == route_tail), fix_id, body)

    def note(name: str) -> None:
        s.counts[name] = (counts(lab), main_branch(lab, pid))

    # nothing has been run: no test has failed, so there is no fix yet
    s.empty = go("").json()
    s.before_any_result = {tail: refused(go(tail), 404) for _, tail, _ in FIX_ROUTES}
    s.connect_too_early = refused(go("/connect"))
    client.post(f"/api/plans/{pid}/run-all")
    wait(client, pid)
    s.not_connected = go("").json()
    s.before_connecting = {tail: refused(go(tail)) for _, tail, _ in FIX_ROUTES}
    s.text_only = {tail: refused(go(tail, fix_id=TLS)) for _, tail, _ in FIX_ROUTES}
    note("not_connected")
    # connect (the proof starts by itself); while it runs everything else waits
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": address, "confirmed": False})
    with held(lab):
        s.connected = go("/connect")
        s.while_proving = {
            "connect": refused(go("/connect")), "proof": refused(go("/{fix}/proof")), "pull-request": refused(go("/{fix}/pull-request")),
            "run-all": refused(client.post(f"/api/plans/{pid}/run-all")), "evidence": refused(client.post(f"/api/plans/{pid}/evidence")),
            "retest": refused(client.post(f"/api/plans/{pid}/retest", json={"version": "1.4.3"}))}
        s.polled_while_proving = go("").json()
    wait(client, pid)
    s.failed = go("").json()
    s.after_failed_proof = {"pull-request": refused(go("/{fix}/pull-request")), "merge": refused(go("/{fix}/merge")), "patch": refused(go("/{fix}/patch"))}
    note("failed")
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": address, "confirmed": True})
    with held(lab):
        s.proof_again = go("/{fix}/proof")
    wait(client, pid)
    s.ready = go("").json()
    s.proof_when_passed = refused(go("/{fix}/proof"))
    note("ready")
    # the plan changes after the proof: a pull request needs a proof of exactly the tests in the plan
    added = client.post(f"/api/plans/{pid}/tests", json={"catalog_id": "mldsa_compare"}).json()
    s.plan_changed = {"view": go("").json(), "pull-request": refused(go("/{fix}/pull-request")), "proof": refused(go("/{fix}/proof"))}
    client.post(f"/api/plans/{pid}/tests/{next(t['id'] for t in added['tests'] if t['kind'] == 'mldsa_compare')}/remove")
    # the reviewers must be a list of ids from the fixed list, each once
    s.bad_reviewers = {repr(body): go("/{fix}/pull-request", body) for body in (
        {"reviewers": []}, {"reviewers": ["you", "you"]}, {"reviewers": ["c"]}, {"reviewers": ["You"]}, {"reviewers": "you"}, {"reviewers": [1]},
        {"reviewers": [["you"]]}, {"reviewers": None}, {}, None, {"reviewers": ["you"] * 9}, {"reviewers": ["x" * 17]}, ["you"], {"reviewer": "you"})}
    note("after_bad_reviewers")
    s.opened = go("/{fix}/pull-request", {"reviewers": ["a", "you"], "file": "/tmp/x.py", "merge": True})
    s.opened_twice = refused(go("/{fix}/pull-request"))
    s.proof_with_pull_request = refused(go("/{fix}/proof"))
    note("opened")
    s.bad_reviewer = {repr(body): go("/{fix}/approve", body) for body in (
        {"reviewer": "c"}, {"reviewer": "You"}, {"reviewer": ""}, {"reviewer": 1}, {"reviewer": ["you"]}, {"reviewer": None}, {}, None,
        {"reviewer": "x" * 17}, {"reviewers": ["you"]})}
    s.not_picked = refused(go("/{fix}/approve", {"reviewer": "b"}))
    s.merge_too_early = refused(go("/{fix}/merge"))
    s.retest_too_early = refused(go("/{fix}/retest"))
    note("before_approvals")
    s.approved_you = go("/{fix}/approve", {"reviewer": "you"})
    s.approved_twice = refused(go("/{fix}/approve", {"reviewer": "you"}))
    s.merge_with_one_missing = refused(go("/{fix}/merge"))
    s.approved_a = go("/{fix}/approve", {"reviewer": "a"})
    note("approved")
    s.patch = go("/{fix}/patch")
    s.polled_before_merge = (go("").json(), client.get(f"/api/plans/{pid}/lab").json())
    note("before_merge")  # every reviewer has approved, the view and the patch have been fetched: still not merged
    s.merged = go("/{fix}/merge")
    s.merged_twice = refused(go("/{fix}/merge"))
    s.approve_after_merge = refused(go("/{fix}/approve", {"reviewer": "a"}))
    note("merged")
    s.patch_after_merge = go("/{fix}/patch")
    s.retest = go("/{fix}/retest")
    s.retest_twice = refused(go("/{fix}/retest"))
    wait(client, pid)
    s.after_retest = (go("").json(), client.get(f"/api/plans/{pid}/lab").json())
    note("after_retest")
    return s


# ---------------------------------------------------------------- who may call, and with which ids

@pytest.mark.parametrize("route", ROUTES, ids=[f"{m} {t or '/'}" for m, t, _ in ROUTES])
def test_every_route_needs_a_login(anon_client, route):
    for plan_id in (1, 999):
        response = call(anon_client, plan_id, route)
        assert refused(response, 401) == "Please log in."
    assert counts(anon_client.app.state.lab)["connections"] == 0


@pytest.mark.parametrize("route", ROUTES, ids=[f"{m} {t or '/'}" for m, t, _ in ROUTES])
def test_an_unknown_plan_is_404(api, route):
    assert refused(call(api.client, 999, route), 404) == NO_PLAN
    assert call(api.client, "x", route).status_code == 422  # a plan id is a number


@pytest.mark.parametrize("route", FIX_ROUTES, ids=[f"{m} {t}" for m, t, _ in FIX_ROUTES])
def test_a_fix_id_of_the_wrong_shape_or_that_does_not_exist_is_404(api, route):
    """A fix id is lower-case letters, digits and hyphens, at most 48 of them; anything else is not looked up at all."""
    wrong_shape = ["FIX-ECDSA-RANGE-CHECK", "fix_ecdsa_range_check", "fix ecdsa", "fix.ecdsa", "a" * 49, "fix-ecdsa-range-check;", "%2e%2e",
                   "fix-écdsa", "1'or'1", "fix-ecdsa-range-check%00", "...", "~"]
    for fix_id in wrong_shape:
        for plan_id in (api.pid, 999):  # the shape is checked before anything is looked up
            assert refused(call(api.client, plan_id, route, fix_id), 404) == NO_FIX, fix_id
    for fix_id in ("fix-nothing", "fix-certificate", "fix", "a" * 48, "0", "fix-ecdsa-range-check-"):
        assert refused(call(api.client, api.pid, route, fix_id), 404) == NO_FIX, fix_id
    # more path after the id is no route of this app
    extra = api.client.request(route[0], f"/api/plans/{api.pid}/fixes/{FIX}/x{route[1].split('}')[1]}/y", json=route[2])
    assert refused(extra, 404) == "There is no such address in this app."


def test_only_the_eight_routes_exist_and_none_accepts_a_file_or_software(api):
    routes = [r for r in api.client.app.routes if isinstance(r, APIRoute) and "/fixes" in r.path]
    assert sorted((sorted(r.methods)[0], r.path.removeprefix("/api/plans/{plan_id}/fixes")) for r in routes) == sorted(
        (method, tail.replace("{fix}", "{fix_id}")) for method, tail, _ in ROUTES)
    # two of them take a body: one small JSON object each, naming reviewers from the fixed list. Nothing else is read.
    bodies = {r.path.rsplit("/", 1)[1]: r.body_field.field_info.annotation for r in routes if r.body_field is not None}
    assert bodies == {"pull-request": PullRequestBody, "approve": ApproveBody}
    assert set(PullRequestBody.model_fields) == {"reviewers"} and set(ApproveBody.model_fields) == {"reviewer"}
    for route in routes:
        names = set(route.endpoint.__code__.co_varnames)
        assert names <= {"plan_id", "fix_id", "body", "filename", "data"} and not names & {"request", "file", "upload"}, route.path
    # the other methods are not there
    for method, tail, _ in ROUTES:
        other = "POST" if method == "GET" else "GET"
        response = api.client.request(other, f"/api/plans/{api.pid}/fixes{tail.format(fix=FIX)}")
        assert response.status_code in (404, 405) and "error" in response.json()
    for method in ("PUT", "PATCH", "DELETE"):
        assert api.client.request(method, f"/api/plans/{api.pid}/fixes/{FIX}/merge").status_code in (404, 405)
    # a file sent to a route that takes no body is not read, stored or run: the answer is the same refusal as without it
    # (asked where each call is refused anyway: the code is connected, the pull request is merged, a text-only fix has no retest)
    before = counts(api.lab)
    for tail, fix_id in (("/connect", FIX), ("/{fix}/proof", FIX), ("/{fix}/merge", FIX), ("/{fix}/retest", TLS)):
        path = f"/api/plans/{api.pid}/fixes{tail.format(fix=fix_id)}"
        plain_answer = api.client.post(path)
        with_file = api.client.post(path, content=b"import os\nos.system('id')\n", headers={"Content-Type": "application/octet-stream"})
        assert with_file.status_code == plain_answer.status_code == 409 and with_file.json() == plain_answer.json(), tail
    assert counts(api.lab) == before
    files = [p for p in api.lab.settings.data_dir.rglob("*") if p.is_file()]
    assert files and not any(b"os.system('id')" in p.read_bytes() for p in files)


# ---------------------------------------------------------------- the flow, call by call

def test_every_successful_post_answers_with_the_whole_view(api):
    for name, key in (("connected", "proving"), ("proof_again", "proving"), ("opened", "waiting"), ("approved_you", "waiting"),
                      ("approved_a", "ready_to_merge"), ("merged", "merged")):
        response = getattr(api, name)
        assert response.status_code == 200, name
        view = response.json()
        assert problems(view, FIXES_VIEW, name) == [] and view["plan_id"] == api.pid
        assert fix_of(view, FIX)["status"]["key"] == key and [f["id"] for f in view["fixes"]] == [FIX, TLS]
    assert api.connected.json()["busy"] is True and api.proof_again.json()["busy"] is True  # so the screen asks again
    # "Retest now" answers with the Evidence Lab view, where the retest then shows
    assert api.retest.status_code == 200 and problems(api.retest.json(), LAB_VIEW, "retest") == []
    assert api.retest.json()["view"] == "before_after" and api.retest.json()["retest"]["running"] is True
    # the GET answers are the same shape, at every moment
    for view in (api.empty, api.not_connected, api.polled_while_proving, api.failed, api.ready, api.plan_changed["view"], api.polled_before_merge[0],
                 api.after_retest[0]):
        assert problems(view, FIXES_VIEW) == []
    assert api.empty["fixes"] == [] and api.empty["empty_text"] == "No failed test has a fix. Fixes for failed tests show here."
    assert problems(api.polled_before_merge[1], LAB_VIEW) == [] and problems(api.after_retest[1], LAB_VIEW) == []


def test_what_each_step_shows(api):
    def status(view):
        return fix_of(view, FIX)["status"]["word"]

    assert [status(v) for v in (api.not_connected, api.connected.json(), api.polled_while_proving, api.failed, api.proof_again.json(), api.ready,
                                api.plan_changed["view"], api.opened.json(), api.approved_you.json(), api.approved_a.json(), api.merged.json(),
                                api.after_retest[0])] == [
        "Code not connected", "Proving", "Proving", "Proof failed", "Proving", "Ready for review", "Proof failed", "Waiting for approval",
        "Waiting for approval", "Ready to merge", "Merged", "Merged"]
    # the reviewers are stored in the fixed order, whatever order they were sent in; nothing else from the body is kept
    rows = fix_of(api.opened.json(), FIX)["approvers"]["rows"]
    assert [(r["id"], r["name"], r["approved_at"]) for r in rows] == [("you", "You", None), ("a", "Demo reviewer A", None)]
    with api.lab.db() as db:
        request = db.query(PullRequestRow).filter_by(plan_id=api.pid).one()
        assert (request.number, request.title, request.reviewers) == (1, "Reject signatures whose r or s is out of range", ["you", "a"])
        assert [(a.reviewer, a.name) for a in db.query(ApprovalRow).filter_by(pull_request_id=request.id).order_by(ApprovalRow.id)] == [
            ("you", "You"), ("a", "Demo reviewer A")]
    rows = fix_of(api.approved_you.json(), FIX)["approvers"]["rows"]
    assert [bool(r["approved_at"]) for r in rows] == [True, False] and rows[0]["approved_text"] == "Approved"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", rows[0]["approved_at"])  # recorded with the time
    after = api.after_retest[1]
    assert after["view"] == "before_after" and [r["after"]["label"] for r in after["rows"]] == ["Failed", "Passed", "Passed"]
    assert after["columns"]["after_heading"].startswith("After: acme-sign 1.4.3, the merged fix (commit ")


def test_every_refusal_says_why_in_a_plain_sentence(api):
    proof, request, approve, merge, retest, patch = (tail for _, tail, _ in FIX_ROUTES)
    assert api.connect_too_early == RUN_FIRST
    assert api.before_any_result == {tail: NO_FIX for tail in (proof, request, approve, merge, retest, patch)}  # no failed test, no fix
    assert api.before_connecting == {
        proof: "Connect the demo code first.", request: "Connect the demo code first.", approve: "Open a pull request first.",
        merge: "Open a pull request first.", retest: "Retest now is available after the merge.",
        patch: "The patch can be downloaded once a pull request is open."}
    assert api.text_only == {tail: TEXT_ONLY for tail in (proof, request, approve, merge, retest, patch)}
    assert api.while_proving == {"connect": "The demo code is already connected for this file.", "proof": PROOF_RUNNING,
                                 "pull-request": "A pull request can be opened only after the proof has passed.",
                                 "run-all": PROOF_RUNNING, "evidence": PROOF_RUNNING, "retest": PROOF_RUNNING}
    assert api.after_failed_proof == {"pull-request": "A pull request can be opened only after the proof has passed.",
                                      "merge": "Open a pull request first.", "patch": "The patch can be downloaded once a pull request is open."}
    assert api.proof_when_passed == "The proof has passed. It can be run again only after it failed or was interrupted."
    assert api.plan_changed["pull-request"] == "The test plan has changed since the proof ran. Run the proof again first."
    assert api.plan_changed["proof"] == RUN_FIRST  # the added test has no first result to compare with
    assert api.opened_twice == "A pull request is already open for this change."
    assert api.proof_with_pull_request == "A pull request is already open for this change, so its proof stays as it is."
    assert api.not_picked == "That reviewer was not picked for this pull request."
    assert api.merge_too_early == api.merge_with_one_missing == "Every picked reviewer must approve before the merge."
    assert api.retest_too_early == "Retest now is available after the merge."
    assert api.approved_twice == "That reviewer has already approved."
    assert api.merged_twice == api.approve_after_merge == "This pull request is already merged."
    assert api.retest_twice == "Tests are still running. Wait until they have finished."
    # a refusal the view announced: the switched-off button's note is the sentence the route answers with
    assert fix_of(api.plan_changed["view"], FIX)["actions"] == {
        "buttons": [{"action": "run_proof_again", "label": "Run proof again", "primary": False, "enabled": False}], "note": RUN_FIRST}


def test_the_bodies_are_checked(api):
    for text, response in api.bad_reviewers.items():
        message = refused(response, 422)
        field = response.json()["error"]["field"]
        if text in ("{'reviewers': []}", "{'reviewers': ['you', 'you']}", "{'reviewers': ['c']}", "{'reviewers': ['You']}"):
            assert (message, field) == (PICK, "reviewers"), text  # a list of text, but not a pick from the fixed list
        else:
            assert message.startswith("The request is not valid") and (field is None or field.startswith("reviewers")), text
    for text, response in api.bad_reviewer.items():
        message = refused(response, 422)
        field = response.json()["error"]["field"]
        if text in ("{'reviewer': 'c'}", "{'reviewer': 'You'}", "{'reviewer': ''}"):
            assert (message, field) == ("That reviewer is not in the list.", "reviewer"), text
        else:
            assert message.startswith("The request is not valid") and field in (None, "reviewer"), text
    # none of them left anything behind
    assert api.counts["after_bad_reviewers"] == api.counts["ready"]
    assert api.counts["before_approvals"][0]["approvals"] == 0


def test_nothing_happens_unless_its_own_route_is_called(api):
    """No pull request, approval or merge is ever made by another route, by a refused call, or by looking."""
    def at(name):
        c = api.counts[name][0]
        return (c["connections"], c["changes"], c["proofs"], c["pull_requests"], c["approvals"], c["merges"], c["retests"])

    assert at("not_connected") == (0, 0, 0, 0, 0, 0, 0)  # reading the views and every refused call: nothing
    assert at("failed") == (1, 1, 1, 0, 0, 0, 0)         # Connect demo code: the copy, the change and its proof. No pull request.
    assert at("ready") == (1, 1, 2, 0, 0, 0, 0)          # Run proof again: one more proof. A passed proof opens nothing by itself.
    assert at("opened") == (1, 1, 2, 1, 0, 0, 0)         # Open pull request: nobody has approved
    assert at("before_approvals") == at("opened")        # wrong reviewers, an early merge, an early retest: nothing
    assert at("approved") == (1, 1, 2, 1, 2, 0, 0)       # every reviewer has approved: still not merged
    assert at("before_merge") == at("approved")          # fetching the view, Evidence Lab and the patch merges nothing
    assert at("merged") == (1, 1, 2, 1, 2, 1, 0)         # Merge pull request (sent by Confirm merge): no retest starts by itself
    assert at("after_retest") == (1, 1, 2, 1, 2, 1, 1)   # Retest now
    # the repository says the same: main moves once, at the merge, to a commit with two parents
    heads = {name: head for name, (_, head) in api.counts.items()}
    assert heads["not_connected"] is None
    base = heads["failed"]
    assert all(heads[name] == base for name in ("ready", "opened", "before_approvals", "approved", "before_merge"))
    assert heads["merged"] != base and heads["after_retest"] == heads["merged"]
    with api.lab.db() as db:
        connection = db.query(CodeConnectionRow).filter_by(plan_id=api.pid).one()
        change = db.query(ChangeRow).filter_by(plan_id=api.pid).one()
        assert db.query(MergeRow).one().merge_commit == heads["merged"] and connection.base_commit == base
    repo = GitRepo(api.lab.settings.data_dir / connection.folder)
    assert repo.read_commit(heads["merged"]).parents == (base, change.head_commit)
    assert repo.files(heads["merged"]) == {"acme_sign.py": NEW_FILE} and repo.files(base) == {"acme_sign.py": OLD_FILE}
    # the view before the merge offered it only behind a confirm box; nothing in it merges by being read
    ready_to_merge = fix_of(api.polled_before_merge[0], FIX)
    assert ready_to_merge["status"]["key"] == "ready_to_merge" and ready_to_merge["merge_dialog"]["confirm"] == "Confirm merge"


# ---------------------------------------------------------------- the patch

def apply_patch(old: bytes, patch: str) -> bytes:
    """Apply a one-file patch in the unified layout by hand: every hunk's lines must be found exactly where it says."""
    lines, out, at = old.decode("utf-8").split("\n"), [], 0
    body = patch.split("\n")
    i = next(n for n, text in enumerate(body) if text.startswith("@@ "))
    while i < len(body) and body[i].startswith("@@ "):
        start = int(re.match(r"@@ -(\d+)", body[i]).group(1)) - 1
        out += lines[at:start]
        at, i = start, i + 1
        while i < len(body) and body[i][:1] in (" ", "-", "+") and not body[i].startswith("-- "):
            mark, text = body[i][0], body[i][1:]
            if mark in " -":
                assert lines[at] == text, f"line {at + 1} of the old file is not what the patch expects"
                at += 1
            if mark in " +":
                out.append(text)
            i += 1
    return "\n".join(out + lines[at:]).encode("utf-8")


def test_the_patch_downloads_as_a_file_and_is_the_change(api):
    got = api.patch
    assert got.status_code == 200 and got.headers["content-type"] == "text/x-patch; charset=utf-8"
    # always a download, never a page of this app
    assert got.headers["content-disposition"] == 'attachment; filename="acme-sign-pull-request-1.patch"'
    assert got.headers["x-content-type-options"] == "nosniff" and got.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in got.headers["content-security-policy"] and "sandbox" in got.headers["content-security-policy"]
    view = fix_of(api.opened.json(), FIX)
    assert view["patch"] == {"url": f"/api/plans/{api.pid}/fixes/{FIX}/patch", "filename": "acme-sign-pull-request-1.patch"}
    # the same bytes every time, before and after the merge
    assert api.patch_after_merge.content == got.content == api.client.get(view["patch"]["url"]).content
    patch = got.content.decode("utf-8")
    with api.lab.db() as db:
        change = db.query(ChangeRow).filter_by(plan_id=api.pid).one()
    assert patch.startswith(f"From {change.head_commit} ") and "Subject: [PATCH] Reject signatures whose r or s is out of range" in patch
    assert "From: Evidence Lab fix template <fix-template@example.invalid>" in patch and "From a fix template: ecdsa-range-check" in patch
    assert " acme_sign.py | 4 +++-\n 1 file changed, 3 insertions(+), 1 deletion(-)" in patch
    assert patch.rstrip("\n").endswith("Isogeny Evidence Lab (demo)")
    # applied to our 1.4.2 it gives our 1.4.3, byte for byte
    assert apply_patch(OLD_FILE, patch) == NEW_FILE
    assert hashlib.sha256(apply_patch(OLD_FILE, patch)).hexdigest() == change.built["sha256"] == change.files[0]["new_sha256"]
    with pytest.raises(AssertionError):
        apply_patch(NEW_FILE, patch)  # it is a patch for the old file, and says so when it does not fit


def test_git_itself_applies_the_downloaded_patch(api, tmp_path):
    git = real_git(tmp_path)  # skipped with a message when git is not installed
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "acme_sign.py").write_bytes(OLD_FILE)
    (tmp_path / "change.patch").write_bytes(api.patch.content)
    assert git("apply", "--numstat", tmp_path / "change.patch", cwd=checkout).stdout.decode() == "3\t1\tacme_sign.py\n"
    git("apply", "--check", tmp_path / "change.patch", cwd=checkout)
    git("apply", tmp_path / "change.patch", cwd=checkout)
    assert (checkout / "acme_sign.py").read_bytes() == NEW_FILE


# ---------------------------------------------------------------- files that name no code of ours

def test_connect_is_refused_for_a_file_that_names_no_demo_component_we_hold(app_client):
    client, lab = app_client, app_client.app.state.lab
    before = counts(lab)

    def plan_for(version: str) -> int:
        data = DEMO_CBOM.read_bytes().replace(b"localhost:8443", lab.settings.demo_address.encode()).replace(b'"1.4.2"', f'"{version}"'.encode())
        imp = upload(client, "acme-pay-cbom.json", data).json()
        client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": imp["addresses"][0]["address"], "confirmed": True})
        plan = client.post(f"/api/import/{imp['id']}/plan").json()
        for test in plan["tests"]:
            if test["kind"] in ("official_vectors", "speed_size"):
                client.post(f"/api/plans/{plan['id']}/tests/{test['id']}/remove")
        client.post(f"/api/plans/{plan['id']}/run-all")
        wait(client, plan["id"])
        return plan["id"]

    unknown = plan_for("9.9.9")  # not one of ours: nothing of it runs, and there is no code to connect
    assert refused(client.post(f"/api/plans/{unknown}/fixes/connect")) == "Connecting code needs one of our demo signing components, and this file doesn't name one."
    view = client.get(f"/api/plans/{unknown}/fixes").json()
    assert problems(view, FIXES_VIEW) == [] and [f["id"] for f in view["fixes"]] == [TLS]  # the server finding still has its suggestion
    assert refused(client.post(f"/api/plans/{unknown}/fixes/{FIX}/proof"), 404) == NO_FIX
    newer = plan_for("1.4.3")  # ours, but the demo repository holds 1.4.2
    assert refused(client.post(f"/api/plans/{newer}/fixes/connect")) == "The demo repository does not hold the demo component this file names. The code was not connected."
    assert [f["id"] for f in client.get(f"/api/plans/{newer}/fixes").json()["fixes"]] == [TLS]
    after = counts(lab)
    assert {k: after[k] - before[k] for k in after} == {k: 0 for k in after}
    kept = [p.name for p in (lab.settings.data_dir / "repos").iterdir()] if (lab.settings.data_dir / "repos").exists() else []
    assert not any(name.startswith((f"plan-{unknown}", f"plan-{newer}")) for name in kept)  # the copy that was started is gone again
