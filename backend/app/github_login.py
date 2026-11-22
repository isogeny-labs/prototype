"""Log in with a GitHub App (hosting, 21 November 2026).

The GitHub App's "user-to-server" web flow (https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app):

1. `start`: a random one-time `state` is kept in the cache (10 minutes) and in a cookie of this browser; the browser
   goes to GitHub's authorize page.
2. GitHub sends the browser back to `/api/auth/github/callback` with `code` and `state`.
3. `finish`: the state must match the cookie and be in the cache (it is taken out, so it works once); the code is
   exchanged for a user token, GitHub is asked who the person is and, when organizations are listed, which of this
   App's installations they can reach. The token is then dropped: it is never stored, logged or returned.

Who may log in: a login or numeric GitHub id in EVIDENCE_LAB_GITHUB_ALLOWED_USERS, or an active member of an
organization in EVIDENCE_LAB_GITHUB_ALLOWED_ORGS (the App needs "Members: read-only" and to be installed on it);
every GitHub account only with EVIDENCE_LAB_GITHUB_ALLOW_ANYONE=on. At least one is required (app/config.py).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app import auth
from app.config import GitHubSettings
from app.db import GitHubUserRow, now_utc
from app.infra.cache import Cache

STATE_COOKIE = "evidence_lab_github_state"
STATE_LIFETIME_SECONDS = 600
CALLBACK_PATH = "/api/auth/github/callback"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _http_client() -> httpx.Client:
    """Looked up at the moment of a login, so tests can put a stand-in in its place (tests/conftest.py refuses GitHub)."""
    return httpx.Client(timeout=TIMEOUT)


class LoginRefused(Exception):
    """A login that did not go through, with a sentence for the person."""


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str
    name: str | None
    avatar_url: str | None


def _state_key(state: str) -> str:
    return "github-state:" + hashlib.sha256(state.encode("utf-8")).hexdigest()


def start(github: GitHubSettings, cache: Cache, redirect_uri: str) -> tuple[str, str]:
    """(the address to send the browser to, the state to put in its cookie)."""
    state = secrets.token_urlsafe(32)
    cache.set(_state_key(state), json.dumps({"redirect_uri": redirect_uri}), STATE_LIFETIME_SECONDS)
    query = urlencode(
        {"client_id": github.client_id, "redirect_uri": redirect_uri, "state": state, "allow_signup": "false"}
    )
    return f"{github.web_url}/login/oauth/authorize?{query}", state


def finish(
    github: GitHubSettings,
    cache: Cache,
    db: Session,
    *,
    code: str | None,
    state: str | None,
    cookie_state: str | None,
    client: httpx.Client | None = None,
) -> str:
    """Check the answer from GitHub, record the person and return a new session token. Raises LoginRefused."""
    if not code or not state or len(code) > 200 or len(state) > 200:
        raise LoginRefused("GitHub did not send the login back. Please try again.")
    if not cookie_state or not hmac.compare_digest(cookie_state, state):
        raise LoginRefused("This login was started in another browser or has expired. Please try again.")
    kept = cache.take(_state_key(state))
    if kept is None:
        raise LoginRefused("This login has expired or was already used. Please try again.")
    redirect_uri = json.loads(kept)["redirect_uri"]
    own_client = client is None
    http = client or _http_client()
    try:
        token = _exchange(github, http, code, redirect_uri)
        user = _who(github, http, token)
        if not _allowed(github, http, token, user):
            raise LoginRefused(
                f"The GitHub account {user.login} may not log in to this app. Ask the person who runs it to add you."
            )
    except httpx.HTTPError as exc:
        raise LoginRefused("GitHub could not be reached. Please try again in a moment.") from exc
    finally:
        if own_client:
            http.close()
    _remember(db, user)
    return auth.new_session(db, github_user_id=user.id)


def _exchange(github: GitHubSettings, http: httpx.Client, code: str, redirect_uri: str) -> str:
    reply = http.post(
        f"{github.web_url}/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": github.client_id,
            "client_secret": github.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    reply.raise_for_status()
    body = reply.json()
    token = body.get("access_token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise LoginRefused("GitHub did not accept this login. Please try again.")
    return token


def _api(github: GitHubSettings, http: httpx.Client, token: str, path: str, params: dict | None = None):
    reply = http.get(
        f"{github.api_url}{path}",
        params=params,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    reply.raise_for_status()
    return reply.json()


def _who(github: GitHubSettings, http: httpx.Client, token: str) -> GitHubUser:
    body = _api(github, http, token, "/user")
    if not isinstance(body, dict) or not isinstance(body.get("id"), int) or not isinstance(body.get("login"), str):
        raise LoginRefused("GitHub's answer about this account could not be read. Please try again.")
    name, avatar = body.get("name"), body.get("avatar_url")
    return GitHubUser(
        id=body["id"],
        login=body["login"][:100],
        name=name[:255] if isinstance(name, str) else None,
        avatar_url=avatar[:500] if isinstance(avatar, str) and avatar.startswith("https://") else None,
    )


def _allowed(github: GitHubSettings, http: httpx.Client, token: str, user: GitHubUser) -> bool:
    if github.open_to_anyone or user.login.lower() in github.allowed_users or str(user.id) in github.allowed_users:
        return True
    for org in sorted(github.allowed_orgs):
        # The person's own membership of the organization: active members only (not outside collaborators, not a
        # pending invitation). The GitHub App needs the organization permission "Members: read-only" for this.
        reply = http.get(
            f"{github.api_url}/user/memberships/orgs/{org}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if reply.status_code in (403, 404):
            continue
        reply.raise_for_status()
        body = reply.json()
        if isinstance(body, dict) and body.get("state") == "active":
            return True
    return False


def _remember(db: Session, user: GitHubUser) -> None:
    row = db.get(GitHubUserRow, user.id)
    if row is None:
        db.add(GitHubUserRow(github_id=user.id, login=user.login, name=user.name, avatar_url=user.avatar_url))
    else:
        row.login, row.name, row.avatar_url, row.last_login_at = user.login, user.name, user.avatar_url, now_utc()
    db.commit()
