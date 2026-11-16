"""SQLite storage (SQLAlchemy). No secrets are stored here except the password hash."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, create_engine, text,
)
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


class RetestProgramRow(Base):
    """Phase 4c: which program a retest swaps to another version, when it is not the plan's own program (for example
    openjdk in a file that names several libraries). Its own table, so an older database still opens. Append-only."""
    __tablename__ = "retest_programs"
    retest_id: Mapped[int] = mapped_column(ForeignKey("retests.id"), primary_key=True)
    component_name: Mapped[str] = mapped_column(String(100))


class TestRunRow(Base):
    """One run of one locked test. Inserted once, when the job finishes. Append-only.
    `phase` is "first", "retest" or "proof". For a retest run `retest_id` holds the retest's id; for a proof run
    (phase 3a) the same column holds the proof's id (`proofs.id`). No column was added for it, so a database
    file made by an earlier version still opens."""
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


# ---------------------------------------------------------------- phase 3a: code, changes, proofs, pull requests
# Every table below is append-only. Nothing stores a status word: where a fix stands is worked out from these
# rows each time it is shown.

class CodeConnectionRow(Base):
    """The source code connected for one imported file: the app's own working copy of a demo repository."""
    __tablename__ = "code_connections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), unique=True)
    repository: Mapped[str] = mapped_column(String(100))        # its name, for example "acme-sign"
    folder: Mapped[str] = mapped_column(String(300))            # where the copy is, relative to the data folder
    branch: Mapped[str] = mapped_column(String(100))            # the branch changes are merged into ("main")
    base_commit: Mapped[str] = mapped_column(String(40))        # where that branch stood when it was connected
    component_name: Mapped[str] = mapped_column(String(100))
    component_version: Mapped[str] = mapped_column(String(50))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ChangeRow(Base):
    """A code change: a branch plus the commit it starts from, whoever made it.
    `source`: {"runs": [{"run_id", "item_id", "kind"}]}, the failed results it answers.
    `files`: [{"name", "added", "removed", "old_blob", "new_blob", "old_sha256", "new_sha256", "parts": [...]}].
    `built`: {"file", "sha256", "matches": {"name", "version"} or null}: the byte-for-byte check against our
    registered demo components. Only a change that matches one can be proved, and then that component runs."""
    __tablename__ = "changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    connection_id: Mapped[int] = mapped_column(ForeignKey("code_connections.id"))
    fix_key: Mapped[str] = mapped_column(String(48))
    source_kind: Mapped[str] = mapped_column(String(32))        # "failed_tests"
    source: Mapped[dict] = mapped_column(JSON)
    written_by: Mapped[str] = mapped_column(String(32))         # "fix_template"
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_by: Mapped[str] = mapped_column(String(64))        # the engine's id
    title: Mapped[str] = mapped_column(String(200))
    branch: Mapped[str] = mapped_column(String(100))
    base_commit: Mapped[str] = mapped_column(String(40))
    head_commit: Mapped[str] = mapped_column(String(40))
    files: Mapped[list] = mapped_column(JSON)
    built: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProofRow(Base):
    """One proof of a change: every test of the plan, rerun on the registered component the change is identical to.
    `items`: [{"item_id", "spec_hash", "kind", "first_run_id"}] in plan order, as the plan stood when the proof
    started. Its runs are `test_runs` rows with phase "proof" and this row's id in `retest_id`."""
    __tablename__ = "proofs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    change_id: Mapped[int] = mapped_column(ForeignKey("changes.id"))
    baseline_version: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(50))            # the registered version that runs
    items: Mapped[list] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProofReviewRow(Base):
    """The reviewer's answer to "may this change be offered?", written once, when the proof's last run is reviewed.
    It is believed only while reviewing the stored records again gives exactly this row."""
    __tablename__ = "proof_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proof_id: Mapped[int] = mapped_column(ForeignKey("proofs.id"), unique=True)
    reviewer: Mapped[str] = mapped_column(String(64))
    record_sha256: Mapped[str] = mapped_column(String(64))
    offered: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PullRequestRow(Base):
    """A pull request inside the app, for one change, opened on one passed proof."""
    __tablename__ = "pull_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    change_id: Mapped[int] = mapped_column(ForeignKey("changes.id"), unique=True)
    proof_id: Mapped[int] = mapped_column(ForeignKey("proofs.id"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    reviewers: Mapped[list] = mapped_column(JSON)               # the picked reviewer ids, for example ["you", "a"]
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ApprovalRow(Base):
    """One reviewer's approval of a pull request, with the name and the time."""
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("pull_request_id", "reviewer"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"))
    reviewer: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MergeRow(Base):
    """The merge of a pull request: a person's confirmed action, never the app's own."""
    __tablename__ = "merges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), unique=True)
    merge_commit: Mapped[str] = mapped_column(String(40))
    merged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RunCodeRow(Base):
    """Which code one run ran on. Kept beside the run, not inside its fingerprinted record.
    `source` is "bundled" (our registered demo component, as shipped) or "repository" (the connected
    repository holds exactly that component at `branch` / `commit`). Server tests have no row."""
    __tablename__ = "run_code"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), unique=True)
    source: Mapped[str] = mapped_column(String(16))
    component_name: Mapped[str] = mapped_column(String(100))
    component_version: Mapped[str] = mapped_column(String(50))
    file_sha256: Mapped[str] = mapped_column(String(64))        # of the registered file that ran
    repository: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    change_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pull_request_number: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SystemSettingRow(Base):
    """Phase 4a. One setting of one system in an import, as it was given: by the imported file (`source` "file") or
    by the user ("user"). Rows are only ever added; the newest row of a system's field is the one in force. A
    field with no row uses the default, which the screens label "assumed"."""
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    system_key: Mapped[str] = mapped_column(String(600))        # "server:<address>" or "software:<claim ref>"
    field: Mapped[str] = mapped_column(String(16))              # lifespan | exposure | can_change
    value: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MigrationChoiceRow(Base):
    """Phase 4a. The user's own choice of an option for one system, with why and when. Rows are only ever added: a
    new choice is a new row, and nothing the app works out (a recommendation, a new measurement) ever writes here."""
    __tablename__ = "migration_choices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    system_key: Mapped[str] = mapped_column(String(600))
    option: Mapped[str] = mapped_column(String(16))             # keep | hybrid | full_pq | wrap
    reason: Mapped[str] = mapped_column(Text)
    review_date: Mapped[str | None] = mapped_column(String(10), nullable=True)   # YYYY-MM-DD, for "keep"
    basis: Mapped[dict] = mapped_column(JSON)                   # what was on screen then: status, recommendation, settings
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ChangeTryRow(Base):
    """Phase 4b. One "Try on a test copy" of one change: the change exactly as it was tried (with its fingerprint), the
    measurement it is compared with, and which copies were tried (or why one was not). The copies' runs are ordinary
    runs of the system's locked measurement (test_runs, phase "try" or "try_nginx", retest_id = this id)."""
    __tablename__ = "change_tries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    change_key: Mapped[str] = mapped_column(String(700))
    change_fp: Mapped[str] = mapped_column(String(64))
    change: Mapped[dict] = mapped_column(JSON)
    item_id: Mapped[int] = mapped_column(Integer)                  # the plan item whose locked measurement runs on the copies
    before_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    copies: Mapped[list] = mapped_column(JSON)                     # [{"label", "phase", "skipped": reason | None}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ApplyRequestRow(Base):
    """Phase 4b. "Ask for approval" of one change (by its fingerprint), with the reviewers who must approve it."""
    __tablename__ = "apply_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    change_key: Mapped[str] = mapped_column(String(700))
    change_fp: Mapped[str] = mapped_column(String(64))
    reviewers: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ApplyApprovalRow(Base):
    """Phase 4b. One reviewer's approval of an apply request, with the name and the time."""
    __tablename__ = "apply_approvals"
    __table_args__ = (UniqueConstraint("request_id", "reviewer"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("apply_requests.id"))
    reviewer: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ApplyRow(Base):
    """Phase 4b. One Apply, pressed by a person, of one tried and approved change to a lab or demo server: the settings
    before and after, whether the server took them (and its own words), and the newest run id at that moment, so the
    measurement made right after can be found."""
    __tablename__ = "applies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    change_key: Mapped[str] = mapped_column(String(700))
    change_fp: Mapped[str] = mapped_column(String(64))
    address: Mapped[str] = mapped_column(String(300))
    target: Mapped[str] = mapped_column(String(32))                # demo_test_server | lab_nginx | demo_server
    try_id: Mapped[int] = mapped_column(ForeignKey("change_tries.id"))
    request_id: Mapped[int] = mapped_column(ForeignKey("apply_requests.id"))
    settings_before: Mapped[dict] = mapped_column(JSON)
    settings_after: Mapped[dict] = mapped_column(JSON)
    accepted: Mapped[bool] = mapped_column(Boolean)
    words: Mapped[str] = mapped_column(Text)
    runs_before: Mapped[int] = mapped_column(Integer)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RollbackRow(Base):
    """Phase 4b. One Roll back of one Apply: the earlier settings put back, whether the server took them, its words."""
    __tablename__ = "rollbacks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apply_id: Mapped[int] = mapped_column(ForeignKey("applies.id"), unique=True)
    accepted: Mapped[bool] = mapped_column(Boolean)
    words: Mapped[str] = mapped_column(Text)
    runs_before: Mapped[int] = mapped_column(Integer)
    rolled_back_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DependencyListRow(Base):
    """Phase 4d. One dependency list (CycloneDX or SPDX) added to an import, as it was read: the libraries, what
    depends on what, and the fingerprint of the exact file. The file is data: nothing in it is ever run. Rows are only
    ever added; the newest list of an import is the one in force."""
    __tablename__ = "dependency_lists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(32))             # "CycloneDX 1.6", "SPDX 2.3", ...
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    parsed: Mapped[dict] = mapped_column(JSON)                  # {"described", "components": [...], "edges": {...}}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DependencyTieRow(Base):
    """Phase 4d. A person's own answer to "Part of": which system of the imported file one top entry of a list belongs
    to ("" = none of these). Rows are only ever added; the newest row for a top entry is the one in force."""
    __tablename__ = "dependency_ties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("dependency_lists.id"))
    top_key: Mapped[str] = mapped_column(String(300))
    system_key: Mapped[str] = mapped_column(String(600))        # "server:<address>", "software:<claim ref>", or ""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# ---- Phase 5a: folders, projects and assessments. Names, places and the archived flag can change; nothing is ever
# deleted (a trigger refuses it). An assessment holds at most one import: everything else of a pass is keyed by it. ----

class FolderRow(Base):
    __tablename__ = "folders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    system_key: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)   # "demo", "unfiled": the app's own
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_key: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)     # Load demo projects adds each once
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AssessmentRow(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    number: Mapped[int] = mapped_column(Integer)                  # 1, 2, 3... within its project (kept when moved)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)   # set by the person; else "Assessment <number>"
    import_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id"), nullable=True, unique=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_why: Mapped[str | None] = mapped_column(String(20), nullable=True)   # "closed" (by the person) | "newer"
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AppSettingRow(Base):
    """Small settings of this installation, for example the organization's name."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


NO_DELETE_TABLES = ("folders", "projects", "assessments")


APPEND_ONLY_TABLES = ("test_specs", "test_runs", "reviews", "code_connections", "changes", "proofs", "proof_reviews",
                      "pull_requests", "approvals", "merges", "run_code", "system_settings", "migration_choices",
                      "change_tries", "apply_requests", "apply_approvals", "applies", "rollbacks",
                      "dependency_lists", "dependency_ties")


def create_append_only_triggers(engine) -> None:
    """Locked tests, runs, reviews and the records of a fix can be added but never changed or removed, whatever code asks."""
    with engine.begin() as conn:
        for table in APPEND_ONLY_TABLES:
            for verb in ("UPDATE", "DELETE"):
                conn.execute(text(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_no_{verb.lower()} BEFORE {verb} ON {table} "
                    f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"))
        for table in NO_DELETE_TABLES:   # phase 5a: folders, projects and assessments can be renamed, moved, archived; never removed
            conn.execute(text(f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} "
                              f"BEGIN SELECT RAISE(ABORT, '{table} are never deleted'); END;"))


def make_session_factory(db_path: Path) -> sessionmaker:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(engine)
    create_append_only_triggers(engine)
    return sessionmaker(engine, expire_on_commit=False)
