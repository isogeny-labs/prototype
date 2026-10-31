"""Relational data model shared by both workflows (IoT firmware signing, containerised application).

Design rules enforced here and in the routers:
* Runs are append-only. A correction is a NEW run that references `supersedes_run_id`.
* Every inventory fact and every run carries a provenance label:
  user_reported | imported | verified   (inventory)
  measured | imported | illustrative     (runs / evidence)
* Approvals are separate records, never a boolean flipped in place, so the history survives.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------- auth / access control / audit
class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class SessionToken(Base, TimestampMixin):
    __tablename__ = "session_tokens"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectMember(Base, TimestampMixin):
    __tablename__ = "project_members"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # owner | editor | reviewer | viewer


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[str | None] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


# ---------------------------------------------------------------- project + inventory
class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # iot | application
    business_purpose: Mapped[str] = mapped_column(Text, default="")
    deployment_environment: Mapped[str] = mapped_column(Text, default="")
    support_period_end: Mapped[str | None] = mapped_column(String(32))
    data_protection_requirements: Mapped[str] = mapped_column(Text, default="")
    update_process: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[dict] = mapped_column(JSON, default=dict)  # hardware / os / software versions
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class InventoryItem(Base, TimestampMixin):
    """One cryptographic fact. Provenance is mandatory. Identification != assurance."""
    __tablename__ = "inventory_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # algorithm | library | key_storage | trust_dependency | purpose | platform | process | other
    purpose: Mapped[str | None] = mapped_column(String(64))  # firmware_signing | transport_security | authentication | ...
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[str] = mapped_column(String(16), nullable=False)  # user_reported | imported | verified
    provenance_detail: Mapped[str] = mapped_column(Text, default="")


class Requirement(Base, TimestampMixin):
    """Customer-defined operational limit used as acceptance criterion for runs."""
    __tablename__ = "requirements"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)  # key into run.metrics
    operator: Mapped[str] = mapped_column(String(4), nullable=False)  # <= >= == 
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    applies_to: Mapped[str] = mapped_column(String(32), default="all")  # all | measured | imported


# ---------------------------------------------------------------- implementation workspace
class Implementation(Base, TimestampMixin):
    """A versioned candidate (or the baseline) tied to exact source revision, config and target."""
    __tablename__ = "implementations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # baseline | candidate
    status: Mapped[str] = mapped_column(String(24), default="draft")
    # draft | proposed | approved | rejected | superseded | retired
    profile_id: Mapped[str | None] = mapped_column(String(64))  # catalog implementation profile
    algorithm: Mapped[str] = mapped_column(String(128), default="")
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    library: Mapped[str] = mapped_column(String(128), default="")
    library_version: Mapped[str] = mapped_column(String(64), default="")
    source_revision: Mapped[str] = mapped_column(String(128), default="")
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    target_environment: Mapped[dict] = mapped_column(JSON, default=dict)
    build_identity: Mapped[dict] = mapped_column(JSON, default=dict)  # dependencies, image digest, etc.
    delivery_mode: Mapped[str | None] = mapped_column(String(24))  # remote | customer_lab | isogeny_lab | onsite | container
    compatibility_warnings: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("implementations.id"))
    recommendation_id: Mapped[str | None] = mapped_column(String(32))
    change_artifact_id: Mapped[str | None] = mapped_column(String(32))  # proposed change record / patch
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    implementation_id: Mapped[str | None] = mapped_column(ForeignKey("implementations.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | in_progress | done | blocked
    notes: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------- experiments / runs / evidence
class Experiment(Base, TimestampMixin):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fixture: Mapped[str] = mapped_column(String(64), nullable=False)  # firmware_signing | app_service_crypto | toy_factoring | external
    definition: Mapped[dict] = mapped_column(JSON, default=dict)  # scenarios, repeat counts, params
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)  # requirement ids + fixture checks
    description: Mapped[str] = mapped_column(Text, default="")


class Run(Base, TimestampMixin):
    """Append-only evidence record."""
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False)
    implementation_id: Mapped[str] = mapped_column(ForeignKey("implementations.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | completed | failed
    provenance: Mapped[str] = mapped_column(String(16), nullable=False)  # measured | imported | illustrative
    runner_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    runner_version: Mapped[str] = mapped_column(String(64), default="")
    fixture_version: Mapped[str] = mapped_column(String(64), default="")
    environment: Mapped[dict] = mapped_column(JSON, default=dict)
    commands: Mapped[list] = mapped_column(JSON, default=list)
    repeat_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    metric_definitions: Mapped[dict] = mapped_column(JSON, default=dict)
    scenarios: Mapped[list] = mapped_column(JSON, default=list)  # functional / rejection checks with pass/fail
    raw_output_artifact_id: Mapped[str | None] = mapped_column(String(32))
    failures: Mapped[list] = mapped_column(JSON, default=list)
    exclusions: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    artifact_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    requirement_results: Mapped[list] = mapped_column(JSON, default=list)
    overall_pass: Mapped[bool | None] = mapped_column(Boolean)
    supersedes_run_id: Mapped[str | None] = mapped_column(String(32))
    correction_note: Mapped[str] = mapped_column(Text, default="")
    job_id: Mapped[str | None] = mapped_column(String(32))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # raw_output | import | patch | document | package
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str] = mapped_column(String(255), default="")


# ---------------------------------------------------------------- recommendations / approvals / findings
class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # migration | configuration | no_migration | remediation
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft | under_review | approved | rejected | superseded | implemented
    catalog_profile_id: Mapped[str | None] = mapped_column(String(64))
    purpose: Mapped[str | None] = mapped_column(String(64))
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    # what_changes, why, threat_model, references, compatibility, tradeoffs, integration, evidence_needed,
    # limitations, retest_plan, operational_requirements
    finding_id: Mapped[str | None] = mapped_column(String(32))
    target_implementation_id: Mapped[str | None] = mapped_column(String(32))
    resulting_implementation_id: Mapped[str | None] = mapped_column(String(32))
    generated_by: Mapped[str] = mapped_column(String(32), default="catalog")  # catalog | researcher | user
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)  # recommendation | implementation | run | finding | sandbox_experiment
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # approved | rejected | needs_changes | reviewed
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")


class ResearchSource(Base, TimestampMixin):
    __tablename__ = "research_sources"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text, default="")  # untrusted data, never executed
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="document")  # url | document | internal_measurement
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | reviewed | failed
    extraction_method: Mapped[str] = mapped_column(String(32), default="")  # rule_based | ai_adapter | manual
    submitted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


FINDING_STATUSES = ["new", "triage", "relevant", "experiment_proposed", "reviewed",
                    "action_approved", "retested", "closed", "not_relevant"]


class Finding(Base, TimestampMixin):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(32))
    origin: Mapped[str] = mapped_column(String(32), nullable=False)  # research | measurement | manual
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    claims: Mapped[list] = mapped_column(JSON, default=list)  # [{text, quote, reproduced: published|independently_reproduced|internal_measurement}]
    affected: Mapped[dict] = mapped_column(JSON, default=dict)  # algorithms, libraries, versions, platforms
    matched_inventory_ids: Mapped[list] = mapped_column(JSON, default=list)
    affected_implementation_ids: Mapped[list] = mapped_column(JSON, default=list)
    relevance: Mapped[str] = mapped_column(Text, default="")
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    proposed_followup: Mapped[dict] = mapped_column(JSON, default=dict)  # {type: experiment|implementation_review, description}
    status: Mapped[str] = mapped_column(String(24), default="new")
    status_history: Mapped[list] = mapped_column(JSON, default=list)
    recommendation_id: Mapped[str | None] = mapped_column(String(32))
    evidence_run_ids: Mapped[list] = mapped_column(JSON, default=list)
    requirement_id: Mapped[str | None] = mapped_column(String(32))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_method: Mapped[str] = mapped_column(String(32), default="manual")


# ---------------------------------------------------------------- attack-cost research
class AttackAssessment(Base, TimestampMixin):
    __tablename__ = "attack_assessments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(1), nullable=False)
    # A measured experiment | B estimated from measured components | C published estimate | D unknown/unsupported
    attack_model: Mapped[str] = mapped_column(String(16), nullable=False)  # classical | quantum
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    target_parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    objective: Mapped[str] = mapped_column(Text, default="")
    attacker_capabilities: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    hardware_assumptions: Mapped[str] = mapped_column(Text, default="")
    measured_throughput: Mapped[dict | None] = mapped_column(JSON)  # {value, unit, run_id}
    expected_work: Mapped[dict | None] = mapped_column(JSON)  # {value, unit, log2, estimation_method}
    probability_model: Mapped[str] = mapped_column(Text, default="")
    parallelization: Mapped[str] = mapped_column(Text, default="")
    overhead_assumptions: Mapped[str] = mapped_column(Text, default="")
    compute_price: Mapped[dict | None] = mapped_column(JSON)  # user supplied {unit, price_usd}
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    applicability_limits: Mapped[str] = mapped_column(Text, default="")
    run_id: Mapped[str | None] = mapped_column(String(32))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class SandboxExperiment(Base, TimestampMixin):
    """Research-only proposals. Only allowlisted kinds can execute, and only after approval."""
    __tablename__ = "sandbox_experiments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # reproduction | attack_improvement | hypothesis | weakness_harness
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(Text, default="")
    allowlisted_fixture: Mapped[str | None] = mapped_column(String(64))  # e.g. toy_factoring; None => cannot execute
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    target_class: Mapped[str] = mapped_column(String(32), default="synthetic")  # synthetic | owned | authorized
    resource_limits: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed | approved | rejected | executed | verified
    run_id: Mapped[str | None] = mapped_column(String(32))
    assessment_id: Mapped[str | None] = mapped_column(String(32))
    proposed_by: Mapped[str] = mapped_column(String(32), default="user")
    finding_id: Mapped[str | None] = mapped_column(String(32))


# ---------------------------------------------------------------- job queue
class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # run_fixture | research_review | export_package
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
