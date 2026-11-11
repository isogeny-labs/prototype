"""SQLite storage (SQLAlchemy). No secrets are stored here except the password hash."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Base(DeclarativeBase):
    pass


class AuthRow(Base):
    """The single local login. Only a scrypt hash and its salt are kept."""
    __tablename__ = "auth"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    salt: Mapped[bytes] = mapped_column(LargeBinary)
    password_hash: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SessionRow(Base):
    """Server-side login sessions. Only a SHA-256 of the random token is kept."""
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ImportRow(Base):
    __tablename__ = "imports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(32))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    claims: Mapped[list["ClaimRow"]] = relationship(order_by="ClaimRow.id", cascade="all, delete-orphan")
    addresses: Mapped[list["AddressRow"]] = relationship(order_by="AddressRow.id", cascade="all, delete-orphan")
    skipped: Mapped[list["SkippedRow"]] = relationship(order_by="SkippedRow.id", cascade="all, delete-orphan")


class ClaimRow(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    ref: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(300))
    location_kind: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32))
    claimed_value: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    # Internal, structured copy of the claim used by Verify (never a path, never executed).
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class SkippedRow(Base):
    """An item in the imported file that this version does not check (shown under the claims)."""
    __tablename__ = "skipped_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    name: Mapped[str] = mapped_column(Text)
    what: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)


class ImportClearedRow(Base):
    """A failed upload: imports up to and including `after_import_id` are no longer the current import."""
    __tablename__ = "import_cleared"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    after_import_id: Mapped[int] = mapped_column(Integer)


class AddressRow(Base):
    __tablename__ = "addresses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    address: Mapped[str] = mapped_column(String(300))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    resolved_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_loopback: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class VerifyRunRow(Base):
    __tablename__ = "verify_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    results: Mapped[list] = mapped_column(JSON)


# ---------------------------------------------------------------- phase 2: tests, runs, reviews

class TestSpecRow(Base):
    """A locked test. The key is the SHA-256 of `canonical`. Append-only (see the triggers below)."""
    __test__ = False  # not a pytest class
    __tablename__ = "test_specs"
    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    canonical: Mapped[str] = mapped_column(Text)
    proposed_by: Mapped[str] = mapped_column(String(64))
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PlanRow(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"), unique=True)
    component_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    component_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PlanItemRow(Base):
    """The user's arrangement of the plan (order, removed or not). This is the only mutable part."""
    __tablename__ = "plan_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    spec_hash: Mapped[str] = mapped_column(ForeignKey("test_specs.hash"))
    position: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(16))
    removed: Mapped[bool] = mapped_column(Boolean, default=False)


class RetestRow(Base):
    __tablename__ = "retests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    baseline_version: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TestRunRow(Base):
    """One run of one locked test. Inserted once, when the job finishes. Append-only."""
    __test__ = False  # not a pytest class
    __tablename__ = "test_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    plan_item_id: Mapped[int] = mapped_column(ForeignKey("plan_items.id"))
    spec_hash: Mapped[str] = mapped_column(String(64))
    phase: Mapped[str] = mapped_column(String(16))
    retest_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    component_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    component_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    baseline_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mode: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[str] = mapped_column(String(40))   # ISO text, exactly as hashed
    finished_at: Mapped[str] = mapped_column(String(40))
    duration_ms: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict] = mapped_column(JSON)
    logs: Mapped[str] = mapped_column(Text, default="")
    runner: Mapped[str] = mapped_column(String(64))


class ReviewRow(Base):
    """The separate review of one run. Nothing is shown with a result label without one. Append-only."""
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), unique=True)
    reviewer: Mapped[str] = mapped_column(String(64))
    proposed_by: Mapped[str] = mapped_column(String(64))
    spec_hash: Mapped[str] = mapped_column(String(64))
    spec_hash_ok: Mapped[bool] = mapped_column(Boolean)
    run_sha256: Mapped[str] = mapped_column(String(64))
    control_outcome: Mapped[str] = mapped_column(String(32))
    control_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    code: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReviewMarkRow(Base):
    """The user's own "Mark reviewed" on a result."""
    __tablename__ = "review_marks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ResearchRequestRow(Base):
    """A "Dig deeper" request, waiting for a research engine. No answer is ever made up for it."""
    __tablename__ = "research_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), unique=True)
    finding: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EvidenceExportRow(Base):
    """One "Download evidence": the exact bytes of the signed JSON file and of its readable HTML copy."""
    __tablename__ = "evidence_exports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    fingerprint: Mapped[str] = mapped_column(String(64))
    json_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    html_bytes: Mapped[bytes] = mapped_column(LargeBinary)


APPEND_ONLY_TABLES = ("test_specs", "test_runs", "reviews")


def create_append_only_triggers(engine) -> None:
    """Locked tests, runs and reviews can be added but never changed or removed, whatever code asks."""
    with engine.begin() as conn:
        for table in APPEND_ONLY_TABLES:
            for verb in ("UPDATE", "DELETE"):
                conn.execute(text(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_no_{verb.lower()} BEFORE {verb} ON {table} "
                    f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"))


def make_session_factory(db_path: Path) -> sessionmaker:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(engine)
    create_append_only_triggers(engine)
    return sessionmaker(engine, expire_on_commit=False)
