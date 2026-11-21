"""Hosting: the cache, the file store, the database by URL and the health check."""
from __future__ import annotations

import dataclasses
import os
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import load_settings
from app.db import ImportFileRow, make_session_factory
from app.infra import cache as cache_mod
from app.infra.cache import MemoryCache, make_cache
from app.infra.database import normalise_url, redacted
from app.infra.storage import LocalStore, check_key, make_store, safe_name
from app.main import create_app



# ---------------------------------------------------------------- cache

def test_memory_cache_takes_a_value_once_and_forgets_it_when_it_expires(monkeypatch):
    c = MemoryCache()
    c.set("a", "one", 60)
    assert c.get("a") == b"one"
    assert c.take("a") == b"one" and c.take("a") is None
    now = [1000.0]
    monkeypatch.setattr(cache_mod.time, "monotonic", lambda: now[0])
    c.set("b", b"two", 5)
    now[0] += 6
    assert c.get("b") is None


def test_make_cache():
    assert make_cache(None).kind == "memory"
    with pytest.raises(SystemExit):
        make_cache("http://not-redis")


@pytest.mark.skipif(not os.environ.get("EVIDENCE_LAB_TEST_REDIS_URL"), reason="EVIDENCE_LAB_TEST_REDIS_URL is not set")
def test_redis_cache():
    c = make_cache(os.environ["EVIDENCE_LAB_TEST_REDIS_URL"])
    c.ping()
    key = f"test-{time.time_ns()}"
    c.set(key, "value", 30)
    assert c.get(key) == b"value"
    assert c.take(key) == b"value" and c.get(key) is None


# ---------------------------------------------------------------- file store

def test_keys_stay_inside_the_store(tmp_path):
    for bad in ("../x", "a/../../x", "/abs", "a//b", "", "a\\b"):
        with pytest.raises(ValueError):
            check_key(bad)
    assert safe_name("../../etc/passwd") == "etc_passwd"
    store = LocalStore(tmp_path / "files")
    store.put("imports/abc/file.json", b"{}")
    assert store.get("imports/abc/file.json") == b"{}" and store.exists("imports/abc/file.json")
    assert store.get("imports/missing") is None
    store.ping()


def test_make_store(tmp_path):
    assert make_store(None) is None    # the default: nothing is copied anywhere
    assert make_store(str(tmp_path / "x")).kind == "local"
    assert make_store(f"file://{tmp_path}/y").kind == "local"
    for bad in ("s3://", "gs://", "ftp://host/x"):
        with pytest.raises(SystemExit):
            make_store(bad)


def test_s3_store_against_a_stand_in(monkeypatch):
    moto = pytest.importorskip("moto", reason="moto (a stand-in for S3) is not installed")
    import boto3
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-only")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-only")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("EVIDENCE_LAB_S3_ENDPOINT_URL", raising=False)
    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="evidence-lab")
        store = make_store("s3://evidence-lab/prefix")
        store.ping()
        store.put("evidence/1/abc.json", b'{"a":1}', "application/json")
        assert store.get("evidence/1/abc.json") == b'{"a":1}'
        assert store.exists("evidence/1/abc.json") and not store.exists("evidence/1/none.json")
        assert store.get("evidence/1/none.json") is None
        keys = [o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket="evidence-lab")["Contents"]]
        assert keys == ["prefix/evidence/1/abc.json"]


def test_by_default_nothing_is_copied(client, settings):
    assert client.app.state.lab.store is None
    client.post("/api/import/demo")
    assert not (settings.data_dir / "files").exists()


@pytest.fixture
def stored_client(settings, tmp_path):
    s = dataclasses.replace(settings, storage_url=str(tmp_path / "store"))
    with TestClient(create_app(s)) as c:
        assert c.post("/api/setup", json={"password": "test-only-passphrase"}).status_code == 200
        yield c


def test_the_scanner_file_of_an_import_is_copied_to_the_store(stored_client):
    client = stored_client
    imp = client.post("/api/import/demo").json()
    store = client.app.state.lab.store
    with client.app.state.lab.db() as db:
        row = db.scalars(select(ImportFileRow).where(ImportFileRow.import_id == imp["id"])).one()
        assert store.get(f"imports/{row.sha256}/{safe_name(row.filename)}") == row.data


def test_a_store_that_fails_changes_no_answer(stored_client, monkeypatch):
    def broken(*_a, **_k):
        raise OSError("the store is down")
    monkeypatch.setattr(stored_client.app.state.lab.store, "put", broken)
    assert stored_client.post("/api/import/demo").status_code == 200


# ---------------------------------------------------------------- database

def test_urls():
    assert normalise_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_url("postgresql://u@h/db") == "postgresql+psycopg://u@h/db"
    assert "p@" not in redacted("postgresql+psycopg://u:p@h/db")


def test_settings_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("EVIDENCE_LAB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EVIDENCE_LAB_DATABASE_URL", "postgresql://u@db/evidence")
    monkeypatch.setenv("EVIDENCE_LAB_GITHUB_CLIENT_ID", "Iv1.x")
    monkeypatch.setenv("EVIDENCE_LAB_GITHUB_CLIENT_SECRET", "test-only")
    monkeypatch.setenv("EVIDENCE_LAB_GITHUB_ALLOWED_ORGS", "Isogeny-Labs, other")
    s = load_settings()
    assert s.database == "postgresql://u@db/evidence"
    assert s.github and s.github.allowed_orgs == frozenset({"isogeny-labs", "other"}) and not s.github.open_to_anyone
    assert not s.password_login    # with the GitHub login set up, the password login is off unless asked for
    monkeypatch.setenv("EVIDENCE_LAB_PASSWORD_LOGIN", "on")
    assert load_settings().password_login
    monkeypatch.delenv("EVIDENCE_LAB_GITHUB_ALLOWED_ORGS")
    with pytest.raises(SystemExit, match="ALLOW_ANYONE"):   # who may log in is never left open by accident
        load_settings()
    monkeypatch.setenv("EVIDENCE_LAB_GITHUB_ALLOW_ANYONE", "on")
    assert load_settings().github.open_to_anyone
    monkeypatch.setenv("EVIDENCE_LAB_PASSWORD_LOGIN", "off")
    monkeypatch.delenv("EVIDENCE_LAB_GITHUB_CLIENT_SECRET")
    with pytest.raises(SystemExit):
        load_settings()
    monkeypatch.delenv("EVIDENCE_LAB_GITHUB_CLIENT_ID")
    with pytest.raises(SystemExit):   # password off with no GitHub login: nobody could log in
        load_settings()


def test_a_sqlite_file_from_before_gets_the_new_session_column(tmp_path):
    path = tmp_path / "old.sqlite3"
    factory = make_session_factory(path)
    with factory() as db:
        db.execute(text("DROP TABLE sessions"))
        db.execute(text("CREATE TABLE sessions (token_hash VARCHAR(64) PRIMARY KEY, created_at DATETIME)"))
        db.commit()
    factory = make_session_factory(path)
    with factory() as db:
        cols = [r[1] for r in db.execute(text("PRAGMA table_info(sessions)"))]
        assert "github_user_id" in cols


@pytest.mark.skipif(not os.environ.get("EVIDENCE_LAB_TEST_DATABASE_URL"),
                    reason="EVIDENCE_LAB_TEST_DATABASE_URL (a PostgreSQL server) is not set")
def test_postgres_keeps_the_append_only_rules(client):
    lab = client.app.state.lab
    assert lab.db_engine.dialect.name == "postgresql"
    client.post("/api/import/demo")
    with lab.db() as db:
        for sql in ("UPDATE import_files SET filename = 'x'", "DELETE FROM import_files", "TRUNCATE import_files",
                    "DELETE FROM projects", "TRUNCATE projects CASCADE"):
            with pytest.raises(DBAPIError, match="append-only|never deleted"):
                db.execute(text(sql))
            db.rollback()


@pytest.mark.skipif(not os.environ.get("EVIDENCE_LAB_TEST_DATABASE_URL"),
                    reason="EVIDENCE_LAB_TEST_DATABASE_URL (a PostgreSQL server) is not set")
def test_postgres_keeps_text_as_long_as_sqlite_does(client):
    """SQLite never enforced String(255); on PostgreSQL the columns have no length either."""
    from app.config import DEMO_CBOM
    from conftest import upload
    long_name = "a" * 290 + ".json"
    assert upload(client, long_name, DEMO_CBOM.read_bytes()).status_code == 200


# ---------------------------------------------------------------- health

def test_health(anon_client):
    r = anon_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["cache"] == {"kind": "memory", "ok": True}
    assert body["storage"] == {"kind": "none", "ok": True} and body["database"]["ok"] is True


def test_health_answers_a_load_balancers_probe_by_address_and_nothing_else_does(settings):
    with TestClient(create_app(settings), base_url="http://10.1.2.3:8000") as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/session").status_code == 400


def test_health_says_when_a_part_does_not_answer(anon_client, monkeypatch):
    def down():
        raise ConnectionError("down")
    monkeypatch.setattr(anon_client.app.state.lab.cache, "ping", down)
    r = anon_client.get("/api/health")
    assert r.status_code == 503 and r.json()["cache"] == {"kind": "memory", "ok": False}


def test_allowed_hosts_from_the_public_url(settings):
    s = dataclasses.replace(settings, public_url="https://lab.example.test", allowed_hosts=("internal.example",))
    with TestClient(create_app(s), base_url="https://lab.example.test") as c:
        assert c.get("/api/session").status_code == 200
    with TestClient(create_app(s), base_url="http://internal.example") as c:
        assert c.get("/api/session").status_code == 200
    with TestClient(create_app(s), base_url="http://elsewhere.example") as c:
        assert c.get("/api/session").status_code == 400

