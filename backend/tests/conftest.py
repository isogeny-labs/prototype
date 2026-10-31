"""Test configuration: isolated temp database/artifact dir, external worker mode (tests drive jobs synchronously)."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="iel-test-")
os.environ["IEL_DATA_DIR"] = _tmp
os.environ["IEL_DATABASE_URL"] = f"sqlite:///{_tmp}/test.sqlite3"
os.environ["IEL_ARTIFACT_DIR"] = f"{_tmp}/artifacts"
os.environ["IEL_WORKER"] = "external"
os.environ["IEL_SKIP_SEED"] = "1"
os.environ.pop("ANTHROPIC_API_KEY", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import User  # noqa: E402
from app.auth import hash_password  # noqa: E402

USERS = {"engineer": ("engineer@test.local", "pw-engineer", False), "reviewer": ("reviewer@test.local", "pw-reviewer", False),
         "admin": ("admin@test.local", "pw-admin", True), "outsider": ("outsider@test.local", "pw-outsider", False)}


@pytest.fixture(scope="session")
def client():
    init_db()
    with SessionLocal() as db:
        for email, pw, adm in USERS.values():
            if not db.query(User).filter_by(email=email).first():
                db.add(User(email=email, name=email.split("@")[0], password_hash=hash_password(pw), is_admin=adm))
        db.commit()
    with TestClient(app) as c:
        yield c


class Actor:
    def __init__(self, client, role):
        self.c = client
        email, pw, _ = USERS[role]
        r = client.post("/api/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200, r.text
        self.token = r.json()["token"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.c.get(url, headers=self.h, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self.h, **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch(url, json=json, headers=self.h, **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self.h, **kw)


@pytest.fixture(scope="session")
def engineer(client):
    return Actor(client, "engineer")


@pytest.fixture(scope="session")
def reviewer(client):
    return Actor(client, "reviewer")


@pytest.fixture(scope="session")
def admin(client):
    return Actor(client, "admin")


@pytest.fixture(scope="session")
def outsider(client):
    return Actor(client, "outsider")


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def new_project(editor, reviewer, **body):
    """Create a project as the admin (owner); add `editor` as editor and `reviewer` as reviewer so role checks are exercised."""
    adm = Actor(editor.c, "admin")
    p = ok(adm.post("/api/projects", json=body))
    ok(adm.post(f"/api/projects/{p['id']}/members", json={"email": USERS["engineer"][0], "role": "editor"}))
    ok(adm.post(f"/api/projects/{p['id']}/members", json={"email": USERS["reviewer"][0], "role": "reviewer"}))
    return p
