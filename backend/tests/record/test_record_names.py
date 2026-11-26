"""Who did what, through the web: the name of a press is the account that is logged in where the app has one (the
hosted app logs in with GitHub), otherwise the name typed once in Settings (Who decides), otherwise "You". It is taken
in the request that pressed the button, and a run that finishes later keeps it. GitHub is a stand-in here."""

import dataclasses

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import auth, github_login
from app.db import ActionRow, ActionRunRow, TestRunRow
from app.main import create_app
from conftest import PASSWORD
from tests.hosting.test_github_login import OCTO, FakeGitHub, github, start


def _presses(lab) -> list[ActionRow]:
    with lab.db() as db:
        return list(db.scalars(select(ActionRow).order_by(ActionRow.id)))


def _walk_to_a_run(c) -> tuple[dict, int, int]:
    """Bring the demo file in, tick its address, verify, open the test plan and run one test: all through the routes."""
    imp = c.post("/api/import/demo").json()
    address = imp["addresses"][0]["address"]
    assert c.post(f"/api/import/{imp['id']}/confirm-address", json={"address": address, "confirmed": True}).json()[
        "confirmed"
    ]
    assert c.post(f"/api/import/{imp['id']}/verify").status_code == 200
    plan = c.post(f"/api/import/{imp['id']}/plan").json()
    item = next(t["id"] for t in plan["tests"] if t["kind"] == "certificate")
    assert c.post(f"/api/plans/{plan['id']}/tests/{item}/run").status_code == 200
    c.app.state.lab.wait_until_idle(plan["id"], 60)
    return imp, plan["id"], item


def test_a_press_by_someone_logged_in_with_github_is_recorded_under_that_account(settings, monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(github_login, "_http_client", lambda: httpx.Client(transport=httpx.MockTransport(fake)))
    with TestClient(create_app(dataclasses.replace(settings, github=github()))) as c:
        lab = c.app.state.lab
        state = start(c)
        assert c.get("/api/auth/github/callback", params={"code": "good-code", "state": state}).status_code == 200
        imp, pid, item = _walk_to_a_run(c)
        rows = _presses(lab)
        assert [a.kind for a in rows] == ["file_imported", "address_confirmed", "verify", "run"]
        assert all((a.by, a.by_source, a.by_account) == ("octocat", "account", f"github:{OCTO['id']}") for a in rows)
        # the run finished later, in a job thread: it is tied to the press, and the press keeps the account
        with lab.db() as db:
            run = db.scalars(select(TestRunRow)).one()
            assert db.scalars(select(ActionRunRow).where(ActionRunRow.run_id == run.id)).one().action_id == rows[-1].id
        timeline = c.get(f"/api/plans/{pid}/timeline").json()
        said = {e["id"]: e["who"] for d in timeline["days"] for e in d["entries"]}
        assert said[f"press-{rows[-1].id}"] == {
            "name": "octocat",
            "source": "account",
            "source_label": "The account that was logged in",
            "demo": False,
            "recorded": True,
            "button": "Run",
        }
        assert {w["name"] for w in said.values()} == {"octocat"}
        history = c.get(f"/api/plans/{pid}/history", params={"key": f"test:{item}"}).json()
        assert history["lines"][0]["said"] == "started by octocat, with Run"
        assert history["lines"][0]["decided_by"] == "decided by the separate reviewer"

        # Another browser, logged in with the password: no account, so the typed name, or "You" until one is typed.
        other = TestClient(c.app)
        assert other.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        assert other.post(f"/api/plans/{pid}/tests/{item}/run").status_code == 200
        lab.wait_until_idle(pid, 60)
        assert other.post("/api/otto/name", json={"name": "Kevin Bacon"}).status_code == 200
        assert other.post(f"/api/plans/{pid}/tests/{item}/run").status_code == 200
        lab.wait_until_idle(pid, 60)
        # ... and the account still comes first for the browser that is logged in with GitHub
        assert c.post(f"/api/plans/{pid}/tests/{item}/run").status_code == 200
        lab.wait_until_idle(pid, 60)
        last = _presses(lab)[-3:]
        assert [(a.by, a.by_source, a.by_account) for a in last] == [
            ("You", "default", None),
            ("Kevin Bacon", "typed", None),
            ("octocat", "account", f"github:{OCTO['id']}"),
        ]

        # Logged out: the button is refused, and nothing is recorded. The session's token is in no row.
        token = c.cookies.get(auth.COOKIE_NAME)
        assert token and c.post("/api/logout").status_code == 200
        assert c.post(f"/api/plans/{pid}/tests/{item}/run").status_code == 401
        rows = _presses(lab)
        assert len(rows) == 7 and token not in repr([(a.by, a.by_account, a.item, a.detail) for a in rows])


def test_with_the_password_login_alone_every_press_reads_you_until_a_name_is_typed(client):
    lab = client.app.state.lab
    imp, pid, item = _walk_to_a_run(client)
    assert {(a.by, a.by_source) for a in _presses(lab)} == {("You", "default")}
    made = client.post(f"/api/plans/{pid}/evidence").json()
    assert client.post("/api/otto/name", json={"name": "Kevin"}).status_code == 200
    assert client.post(f"/api/plans/{pid}/evidence").status_code == 200
    files = client.get(f"/api/plans/{pid}/evidence-files").json()
    assert [(f["who"]["name"], f["who"]["source"], f["who"]["button"]) for f in files["files"]] == [
        ("Kevin", "typed", "Download evidence"),
        ("You", "default", "Download evidence"),
    ]
    assert files["files"][1]["id"] == made["id"] and files["files"][1]["json"] == made["json"]
    # a call that comes from no request (a script, the accuracy check) has no account either
    assert lab.actor() == {"name": "Kevin", "source": "typed", "account": None}
