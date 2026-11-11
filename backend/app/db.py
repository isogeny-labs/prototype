"""SQLite storage (SQLAlchemy). No secrets are stored here except the password hash."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, create_engine
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


def make_session_factory(db_path: Path) -> sessionmaker:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
