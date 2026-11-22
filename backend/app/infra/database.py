"""The database by URL: SQLite (the default, a file in the data folder) or PostgreSQL.

PostgreSQL 14 or newer (CREATE OR REPLACE TRIGGER). The rules the database itself enforces are the same on both: the append-only tables refuse UPDATE and DELETE, and
folders, projects and assessments refuse DELETE, whatever code asks (SQLite and PostgreSQL triggers).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, String, create_engine, inspect, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.engine import make_url

SQLITE_PREFIX = "sqlite"
POSTGRES_PREFIX = "postgresql"
SCHEMA_LOCK_KEY = 0x45564C42   # "EVLB": one app process at a time creates tables and triggers on PostgreSQL


@compiles(String, "postgresql")
def _unbounded_string(element, compiler, **kw):
    """SQLite never enforced the lengths written in db.py (String(255) and so on), and the app was built and checked
    on it: on PostgreSQL the same columns are VARCHAR without a length, so what SQLite keeps, PostgreSQL keeps too."""
    return "VARCHAR"


def normalise_url(url: str | Path) -> str:
    """A path becomes a SQLite URL; postgres:// and postgresql:// use the psycopg 3 driver."""
    if isinstance(url, Path):
        return f"sqlite:///{url}"
    url = url.strip()
    for old in ("postgres://", "postgresql://"):
        if url.startswith(old):
            return "postgresql+psycopg://" + url[len(old):]
    return url


def dialect_of(url: str) -> str:
    return make_url(url).get_backend_name()


def redacted(url: str) -> str:
    """The URL with any password hidden, for logs and the health check."""
    return make_url(url).render_as_string(hide_password=True)


def make_engine(url: str | Path) -> Engine:
    url = normalise_url(url)
    if dialect_of(url) == SQLITE_PREFIX:
        database = make_url(url).database
        if database and database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    if dialect_of(url) == POSTGRES_PREFIX:
        return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
    raise SystemExit(f"EVIDENCE_LAB_DATABASE_URL: only sqlite and postgresql are supported, not {dialect_of(url)}")


def prepare_schema(engine: Engine, metadata, added_columns, append_only: tuple[str, ...],
                   no_delete: tuple[str, ...]) -> None:
    """Create missing tables and columns and the triggers. Safe to run on every start, by several processes at once."""
    if engine.dialect.name == POSTGRES_PREFIX:
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SCHEMA_LOCK_KEY})
            metadata.create_all(conn)
            _add_missing_columns(conn, added_columns)
            _postgres_triggers(conn, append_only, no_delete)
        return
    metadata.create_all(engine)
    with engine.begin() as conn:
        _add_missing_columns(conn, added_columns)
        _sqlite_triggers(conn, append_only, no_delete)


def _add_missing_columns(conn, added_columns) -> None:
    inspector = inspect(conn)
    for table, column, kind in added_columns:
        if not inspector.has_table(table):
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        if column not in have:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {kind}'))


def _sqlite_triggers(conn, append_only, no_delete) -> None:
    for table in append_only:
        for verb in ("UPDATE", "DELETE"):
            conn.execute(text(
                f"CREATE TRIGGER IF NOT EXISTS {table}_no_{verb.lower()} BEFORE {verb} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"))
    for table in no_delete:   # phase 5a: folders, projects and assessments can be renamed, moved, archived; never removed
        conn.execute(text(f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} "
                          f"BEGIN SELECT RAISE(ABORT, '{table} are never deleted'); END;"))


def _postgres_triggers(conn, append_only, no_delete) -> None:
    conn.execute(text(
        "CREATE OR REPLACE FUNCTION evidence_lab_refuse() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION '%', TG_ARGV[0] USING ERRCODE = 'restrict_violation'; END $$"))
    for table in append_only:
        for verb in ("UPDATE", "DELETE"):
            conn.execute(text(
                f'CREATE OR REPLACE TRIGGER {table}_no_{verb.lower()} BEFORE {verb} ON "{table}" '
                f"FOR EACH ROW EXECUTE FUNCTION evidence_lab_refuse('{table} is append-only')"))
        # TRUNCATE skips row triggers; refuse it too.
        conn.execute(text(
            f'CREATE OR REPLACE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON "{table}" '
            f"FOR EACH STATEMENT EXECUTE FUNCTION evidence_lab_refuse('{table} is append-only')"))
    for table in no_delete:
        conn.execute(text(
            f'CREATE OR REPLACE TRIGGER {table}_no_delete BEFORE DELETE ON "{table}" '
            f"FOR EACH ROW EXECUTE FUNCTION evidence_lab_refuse('{table} are never deleted')"))
        conn.execute(text(
            f'CREATE OR REPLACE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON "{table}" '
            f"FOR EACH STATEMENT EXECUTE FUNCTION evidence_lab_refuse('{table} are never deleted')"))


def ping(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
