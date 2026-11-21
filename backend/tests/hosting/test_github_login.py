"""Hosting: log in with a GitHub App. GitHub is a stand-in transport here; no test reaches it (tests/conftest.py)."""
from __future__ import annotations

import dataclasses
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import github_login
from app.config import GitHubSettings
from app.db import GitHubUserRow, SessionRow
from app.main import create_app
from conftest import PASSWORD

WEB, API = "https://github.example.test", "https://api.github.example.test"
TOKEN = "ghu_test_only_token_value"   # a throwaway value for tests, not a real credential
OCTO = {"id": 583231, "login": "octocat", "name": "The Octocat", "avatar_url": "https://avatars.example.test/u/583231"}


def github(**changes) -> GitHubSettings:
    base = GitHubSettings(client_id="Iv1.testclient", client_secret="test-only-secret", web_url=WEB, api_url=API,
                          allow_anyone=True)
    return dataclasses.replace(base, **changes)


class FakeGitHub:
    """Answers the three requests the login makes, and keeps what was asked."""

    def __init__(self, user=OCTO, memberships=None, token=TOKEN):
        self.user, self.token = user, token
        self.memberships: dict[str, str] = dict(memberships or {})   # org -> "active" | "pending"
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.path == "/login/oauth/access_token" and request.method == "POST":
            form = parse_qs(request.content.decode())
            if form.get("code") != ["good-code"] or form.get("client_secret") != ["test-only-secret"]:
                return httpx.Response(200, json={"error": "bad_verification_code"})
            return httpx.Response(200, json={"access_token": self.token, "token_type": "bearer"})
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            return httpx.Response(401, json={"message": "Bad credentials"})
        if request.url.path == "/user":
            return httpx.Response(200, json=self.user)
        if request.url.path.startswith("/user/memberships/orgs/"):
            org = request.url.path.rsplit("/", 1)[1]
            if org not in self.memberships:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"state": self.memberships[org], "role": "member",
                                             "organization": {"login": org}})
        return httpx.Response(404)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(github_login, "_http_client", lambda: httpx.Client(transport=httpx.MockTransport(fake)))
    return fake


def app_with(settings, **changes):
    return TestClient(create_app(dataclasses.replace(settings, **changes)))


def start(client) -> str:
    r = client.get("/api/auth/github/start", follow_redirects=False)
    assert r.status_code == 302
    target = urlparse(r.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{WEB}/login/oauth/authorize"
    query = parse_qs(target.query)
    assert query["client_id"] == ["Iv1.testclient"]
    assert query["redirect_uri"] == ["http://testserver/api/auth/github/callback"]
    return query["state"][0]


def test_session_says_which_logins_are_on(settings):
    with app_with(settings, github=github(app_slug="evidence-lab")) as c:
        s = c.get("/api/session").json()
        assert s["login"] == {"password": True, "github": True,
                              "github_install_url": f"{WEB}/apps/evidence-lab/installations/new"}
        assert s["user"] is None and s["logged_in"] is False


def test_github_login_from_start_to_a_session(settings, fake):
    with app_with(settings, github=github()) as c:
        state = start(c)
        r = c.get("/api/auth/github/callback", params={"code": "good-code", "state": state})
        assert r.status_code == 200 and 'http-equiv="refresh"' in r.text
        s = c.get("/api/session").json()
        assert s["logged_in"] is True
        assert s["user"] == {"login": "octocat", "name": "The Octocat", "avatar_url": OCTO["avatar_url"]}
        assert c.get("/api/workspace").status_code == 200
        # The GitHub token is used for the login and dropped: it is in no table.
        with c.app.state.lab.db() as db:
            users = db.scalars(select(GitHubUserRow)).all()
            assert [(u.github_id, u.login) for u in users] == [(583231, "octocat")]
            assert TOKEN not in repr([(u.__dict__) for u in users])
            assert all(row.github_user_id == 583231 for row in db.scalars(select(SessionRow)))
        # Log out ends the session.
        assert c.post("/api/logout").status_code == 200
        assert c.get("/api/session").json()["logged_in"] is False


def test_a_state_works_once_and_only_in_the_browser_that_started_it(settings, fake):
    with app_with(settings, github=github()) as c:
        state = start(c)
        other = TestClient(c.app)   # another browser: no state cookie
        refused = other.get("/api/auth/github/callback", params={"code": "good-code", "state": state})
        assert refused.status_code == 403 and "another browser" in refused.text
        assert c.get("/api/auth/github/callback", params={"code": "good-code", "state": state}).status_code == 200
        c.cookies.set(github_login.STATE_COOKIE, state, path="/api/auth/github/callback")
        again = c.get("/api/auth/github/callback", params={"code": "good-code", "state": state})
        assert again.status_code == 403 and "already used" in again.text


def test_a_code_github_does_not_accept_logs_nobody_in(settings, fake):
    with app_with(settings, github=github()) as c:
        state = start(c)
        r = c.get("/api/auth/github/callback", params={"code": "bad-code", "state": state})
        assert r.status_code == 403
        assert c.get("/api/session").json()["logged_in"] is False


def test_cancel_on_github(settings, fake):
    with app_with(settings, github=github()) as c:
        start(c)
        r = c.get("/api/auth/github/callback", params={"error": "access_denied"})
        assert r.status_code == 400 and "cancelled" in r.text
        assert fake.seen == []


def test_allowed_users_by_login_or_numeric_id(settings, fake):
    with app_with(settings, github=github(allow_anyone=False, allowed_users=frozenset({"someone-else"}))) as c:
        r = c.get("/api/auth/github/callback", params={"code": "good-code", "state": start(c)})
        assert r.status_code == 403 and "octocat may not log in" in r.text
        assert c.get("/api/session").json()["logged_in"] is False
    for entry in ("octocat", "583231"):
        with app_with(settings, github=github(allow_anyone=False, allowed_users=frozenset({entry}))) as c:
            assert c.get("/api/auth/github/callback", params={"code": "good-code", "state": start(c)}).status_code == 200


def test_allowed_orgs_count_only_active_members(settings, fake):
    orgs = github(allow_anyone=False, allowed_orgs=frozenset({"isogeny-labs"}))
    fake.memberships = {"some-other-org": "active", "isogeny-labs": "active"}
    with app_with(settings, github=orgs) as c:
        assert c.get("/api/auth/github/callback", params={"code": "good-code", "state": start(c)}).status_code == 200
        assert c.get("/api/session").json()["logged_in"] is True
    for memberships in ({"isogeny-labs": "pending"}, {"some-other-org": "active"}):   # an invitation; another org
        fake.memberships = memberships
        with app_with(settings, github=orgs) as c:
            assert c.get("/api/auth/github/callback", params={"code": "good-code", "state": start(c)}).status_code == 403


def test_a_session_of_a_login_that_was_switched_off_no_longer_counts(settings, fake):
    with app_with(settings, github=github(), password_login=True) as c:
        assert c.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        assert c.get("/api/workspace").status_code == 200
        cookie = c.cookies.get("evidence_lab_session")
    with app_with(settings, github=github(), password_login=False) as c:   # the same data folder, password now off
        c.cookies.set("evidence_lab_session", cookie)
        assert c.get("/api/workspace").status_code == 401
        assert c.get("/api/session").json()["logged_in"] is False


def test_github_only(settings, fake):
    with app_with(settings, github=github(), password_login=False) as c:
        s = c.get("/api/session").json()
        assert s["setup_required"] is False and s["login"]["password"] is False
        assert c.post("/api/setup", json={"password": PASSWORD}).status_code == 404
        assert c.post("/api/login", json={"password": PASSWORD}).status_code == 404
        assert c.get("/api/auth/github/callback", params={"code": "good-code", "state": start(c)}).status_code == 200


def test_without_github_the_routes_say_so(settings):
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/auth/github/start", follow_redirects=False).status_code == 404
        assert c.get("/api/auth/github/callback").status_code == 404


def test_public_url_sets_the_callback_and_secure_cookies(settings, fake):
    with app_with(settings, github=github(), public_url="https://lab.example.test") as c:
        c.base_url = "https://lab.example.test"
        r = c.get("/api/auth/github/start", follow_redirects=False)
        assert parse_qs(urlparse(r.headers["location"]).query)["redirect_uri"] == [
            "https://lab.example.test/api/auth/github/callback"]
        assert "secure" in r.headers["set-cookie"].lower()
