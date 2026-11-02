"""Shared data model: projects, implementations, test definitions, experiment proposals, runs, evidence bundles,
findings, recommendations and retests.

Rules enforced here and in the services/routers:
* Runs are append-only. A correction is a NEW run that references `supersedes_run_id`.
* Inventory facts carry provenance: user_reported | detected | independently_tested.
* Runs carry an execution mode (platform_sandbox | customer_runner | imported_results) and a classification
  (not_tested | passed_defined_checks | failed | inconclusive | unsupported | awaiting_review).
* Evidence labels are separate and composable: imported, hash_checked, signature_verified, cairn_verified,
  independently_replayed. None of them means "secure" or "compliant".
* Approvals are records, never a flag flipped in place.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------- auth / access / audit
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


# ---------------------------------------------------------------- project / inventory / requirements
class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow: Mapped[str] = mapped_column(String(32), default="signature_library")  # only supported workflow in the MVP
    description: Mapped[str] = mapped_column(Text, default="")
    intended_use: Mapped[str] = mapped_column(Text, default="")
    threat_assumptions: Mapped[str] = mapped_column(Text, default="")
    runtime_environment: Mapped[dict] = mapped_column(JSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class InventoryItem(Base, TimestampMixin):
    __tablename__ = "inventory_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    implementation_id: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # algorithm | library | key_handling | dependency | platform | purpose | other
    purpose: Mapped[str | None] = mapped_column(String(64))  # signatures | key_establishment | encryption
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[str] = mapped_column(String(24), nullable=False)  # user_reported | detected | independently_tested
    provenance_detail: Mapped[str] = mapped_column(Text, default="")


class Requirement(Base, TimestampMixin):
    __tablename__ = "requirements"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(4), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    applies_to: Mapped[str] = mapped_column(String(32), default="all")  # all | measured | imported


# ---------------------------------------------------------------- implementations
class Implementation(Base, TimestampMixin):
    """A versioned import of the customer's implementation: manifest, source identity, compatibility."""
    __tablename__ = "implementations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="imported")  # imported | baseline | candidate | superseded | retired
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    purpose: Mapped[str] = mapped_column(String(32), default="signatures")  # signatures | key_establishment | encryption
    algorithm: Mapped[str] = mapped_column(String(128), default="")
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    library: Mapped[str] = mapped_column(String(128), default="")
    library_version: Mapped[str] = mapped_column(String(64), default="")
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    runtime_environment: Mapped[dict] = mapped_column(JSON, default=dict)
    source_revision: Mapped[str] = mapped_column(String(128), default="")
    source_snapshot_artifact_id: Mapped[str | None] = mapped_column(String(32))
    source_digest: Mapped[str | None] = mapped_column(String(64))
    build_identity: Mapped[dict] = mapped_column(JSON, default=dict)
    adapter_kind: Mapped[str] = mapped_column(String(24), default="results_only")  # profile | module | results_only
    profile_id: Mapped[str | None] = mapped_column(String(64))
    compatibility: Mapped[dict] = mapped_column(JSON, default=dict)  # {status: compatible|unsupported|unchecked, report: [...]}
    intended_use: Mapped[str] = mapped_column(Text, default="")
    threat_assumptions: Mapped[str] = mapped_column(Text, default="")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("implementations.id"))
    recommendation_id: Mapped[str | None] = mapped_column(String(32))
    change_report: Mapped[str] = mapped_column(Text, default="")  # customer-reported external change
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    seeded_defect: Mapped[str] = mapped_column(Text, default="")  # non-empty => clearly labelled demonstration defect
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


# ---------------------------------------------------------------- tests / runs / evidence
class TestDefinition(Base, TimestampMixin):
    __tablename__ = "test_definitions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    test_id: Mapped[str] = mapped_column(String(64), nullable=False)      # stable identifier, e.g. signature-library-core
    version: Mapped[str] = mapped_column(String(32), nullable=False)      # test definition version
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fixture: Mapped[str] = mapped_column(String(64), nullable=False)      # signature_library | malformed_input_sweep | toy_factoring | external
    definition: Mapped[dict] = mapped_column(JSON, default=dict)          # params, inputs/seeds
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    resource_limits: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")


class Run(Base, TimestampMixin):
    """Append-only evidence record."""
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    test_definition_id: Mapped[str] = mapped_column(ForeignKey("test_definitions.id"), nullable=False)
    implementation_id: Mapped[str] = mapped_column(ForeignKey("implementations.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | completed | failed
    execution_mode: Mapped[str] = mapped_column(String(24), nullable=False)  # platform_sandbox | customer_runner | imported_results
    provenance: Mapped[str] = mapped_column(String(16), nullable=False)  # measured | imported | illustrative
    classification: Mapped[str] = mapped_column(String(24), default="not_tested")
    # not_tested | passed_defined_checks | failed | inconclusive | unsupported | awaiting_review
    runner_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    runner_version: Mapped[str] = mapped_column(String(64), default="")
    fixture_version: Mapped[str] = mapped_column(String(64), default="")
    environment: Mapped[dict] = mapped_column(JSON, default=dict)
    commands: Mapped[list] = mapped_column(JSON, default=list)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    resource_limits: Mapped[dict] = mapped_column(JSON, default=dict)
    repeat_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    metric_definitions: Mapped[dict] = mapped_column(JSON, default=dict)
    scenarios: Mapped[list] = mapped_column(JSON, default=list)
    raw_output_artifact_id: Mapped[str | None] = mapped_column(String(32))
    failures: Mapped[list] = mapped_column(JSON, default=list)
    exclusions: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    artifact_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    requirement_results: Mapped[list] = mapped_column(JSON, default=list)
    overall_pass: Mapped[bool | None] = mapped_column(Boolean)
    evidence_labels: Mapped[list] = mapped_column(JSON, default=list)  # [{label, claim, by, at, ref}]
    bundle_id: Mapped[str | None] = mapped_column(String(32))
    external_run_id: Mapped[str | None] = mapped_column(String(128))
    runner_reported_executed_at: Mapped[str | None] = mapped_column(String(40))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duplicate_of_run_id: Mapped[str | None] = mapped_column(String(32))
    stale_reason: Mapped[str] = mapped_column(Text, default="")
    supersedes_run_id: Mapped[str | None] = mapped_column(String(32))
    correction_note: Mapped[str] = mapped_column(Text, default="")
    experiment_proposal_id: Mapped[str | None] = mapped_column(String(32))
    protocol_version: Mapped[int | None] = mapped_column(Integer)
    job_id: Mapped[str | None] = mapped_column(String(32))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # raw_output | source_snapshot | import | bundle | export
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str] = mapped_column(String(255), default="")


class EvidenceBundle(Base, TimestampMixin):
    """A signed evidence bundle (DSSE envelope around an in-toto Statement). The original envelope is preserved."""
    __tablename__ = "evidence_bundles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # platform | customer_runner
    format: Mapped[str] = mapped_column(String(64), default="dsse+in-toto-statement/v1")
    envelope: Mapped[dict] = mapped_column(JSON, default=dict)        # original, never modified
    statement: Mapped[dict] = mapped_column(JSON, default=dict)       # decoded payload for display
    envelope_sha256: Mapped[str] = mapped_column(String(64), default="")
    signer_keyid: Mapped[str | None] = mapped_column(String(64))
    signer_name: Mapped[str | None] = mapped_column(String(255))
    verification: Mapped[dict] = mapped_column(JSON, default=dict)    # {signature_verified, signer_trusted, digests_ok, binding_ok, problems}
    countersignature: Mapped[dict | None] = mapped_column(JSON)       # platform ingestion receipt (NOT an endorsement)
    artifact_ids: Mapped[list] = mapped_column(JSON, default=list)
    bundle_artifact_id: Mapped[str | None] = mapped_column(String(32))  # stored original bundle file


class TrustedKey(Base, TimestampMixin):
    """Trust policy: which signing identities are accepted. project_id NULL => platform-wide."""
    __tablename__ = "trusted_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(String(32), index=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)  # customer_runner | platform
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | revoked
    note: Mapped[str] = mapped_column(Text, default="")
    added_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- findings / recommendations / approvals
FINDING_STATUSES = ["open", "recommendation_proposed", "external_change_reported", "awaiting_retest",
                    "resolved_within_tested_scope", "still_failing", "inconclusive", "not_relevant"]


class Finding(Base, TimestampMixin):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # implementation_defect | requirement_failure | research_claim | manual
    origin: Mapped[str] = mapped_column(String(32), nullable=False)  # test_run | research | manual
    reproduction_status: Mapped[str] = mapped_column(String(24), default="literature_claim")  # literature_claim | proposal | reproduced
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    claims: Mapped[list] = mapped_column(JSON, default=list)
    affected: Mapped[dict] = mapped_column(JSON, default=dict)  # algorithms, libraries, versions, scenarios, metric
    matched_inventory_ids: Mapped[list] = mapped_column(JSON, default=list)
    affected_implementation_ids: Mapped[list] = mapped_column(JSON, default=list)
    failing_scenarios: Mapped[list] = mapped_column(JSON, default=list)
    failing_requirements: Mapped[list] = mapped_column(JSON, default=list)
    relevance: Mapped[str] = mapped_column(Text, default="")
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="open")
    status_history: Mapped[list] = mapped_column(JSON, default=list)
    source_id: Mapped[str | None] = mapped_column(String(32))
    recommendation_id: Mapped[str | None] = mapped_column(String(32))
    revised_implementation_id: Mapped[str | None] = mapped_column(String(32))
    evidence_run_ids: Mapped[list] = mapped_column(JSON, default=list)
    experiment_proposal_ids: Mapped[list] = mapped_column(JSON, default=list)
    requirement_id: Mapped[str | None] = mapped_column(String(32))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_method: Mapped[str] = mapped_column(String(32), default="manual")


class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="other")
    # parameter_selection | library_upgrade | input_validation | key_handling | error_handling | other
    guidance_kind: Mapped[str] = mapped_column(String(24), default="hypothesis")  # best_practice | hypothesis | project_specific
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft | under_review | approved | rejected | superseded
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    # observed_issue, supporting_evidence, proposed_change, authoritative_guidance, expected_benefit, tradeoffs,
    # applicability_limits, required_retest
    finding_id: Mapped[str | None] = mapped_column(String(32))
    target_implementation_id: Mapped[str | None] = mapped_column(String(32))
    resulting_implementation_id: Mapped[str | None] = mapped_column(String(32))
    generated_by: Mapped[str] = mapped_column(String(32), default="platform")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)  # recommendation | experiment_proposal | run | finding | key
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # approved | rejected | needs_changes | reviewed
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------- research / experiments / attack assessments
class ResearchSource(Base, TimestampMixin):
    __tablename__ = "research_sources"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text, default="")  # untrusted data; never executed or followed
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="document")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    extraction_method: Mapped[str] = mapped_column(String(32), default="")
    submitted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class ExperimentProposal(Base, TimestampMixin):
    """Autoresearcher output. Proposals are separate from executions; execution needs an approved protocol version."""
    __tablename__ = "experiment_proposals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    finding_id: Mapped[str | None] = mapped_column(String(32))
    affected_implementation_id: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    research_question: Mapped[str] = mapped_column(Text, default="")
    motivation: Mapped[str] = mapped_column(Text, default="")
    source_references: Mapped[list] = mapped_column(JSON, default=list)
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    baseline_controls: Mapped[str] = mapped_column(Text, default="")
    procedure: Mapped[str] = mapped_column(Text, default="")
    required_tools: Mapped[list] = mapped_column(JSON, default=list)
    outcomes: Mapped[dict] = mapped_column(JSON, default=dict)  # {success, failure, inconclusive}
    budget: Mapped[dict] = mapped_column(JSON, default=dict)    # {compute, time}
    required_artifacts: Mapped[list] = mapped_column(JSON, default=list)
    safety_boundaries: Mapped[str] = mapped_column(Text, default="")
    can_establish: Mapped[str] = mapped_column(Text, default="")
    cannot_establish: Mapped[str] = mapped_column(Text, default="")
    allowlisted_fixture: Mapped[str | None] = mapped_column(String(64))  # None => proposal only, cannot execute
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    target_class: Mapped[str] = mapped_column(String(24), default="synthetic")  # synthetic | owned | authorized
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed | approved | rejected | executed | reviewed
    claim_status: Mapped[str] = mapped_column(String(24), default="proposal")  # literature_claim | proposal | reproduced
    proposed_by: Mapped[str] = mapped_column(String(64), default="autoresearcher (rule-based)")
    current_protocol_version: Mapped[int] = mapped_column(Integer, default=0)
    run_ids: Mapped[list] = mapped_column(JSON, default=list)
    result_summary: Mapped[str] = mapped_column(Text, default="")


class ProtocolVersion(Base, TimestampMixin):
    """Frozen, approved snapshot of an experiment proposal. Amendments create new versions; nothing is overwritten."""
    __tablename__ = "protocol_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("experiment_proposals.id"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[dict] = mapped_column(JSON, default=dict)
    protocol_sha256: Mapped[str] = mapped_column(String(64), default="")
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    supersedes_version: Mapped[int | None] = mapped_column(Integer)


class AttackAssessment(Base, TimestampMixin):
    __tablename__ = "attack_assessments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    implementation_id: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # reproduced_weakness | measured_experiment | estimated_effort | published_estimate | unknown
    attack_model: Mapped[str] = mapped_column(String(16), nullable=False)  # classical | quantum
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    target_parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    target_version: Mapped[str] = mapped_column(String(64), default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    attacker_capabilities: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    hardware_assumptions: Mapped[str] = mapped_column(Text, default="")
    measured_components: Mapped[dict | None] = mapped_column(JSON)
    expected_work: Mapped[dict | None] = mapped_column(JSON)
    probability_model: Mapped[str] = mapped_column(Text, default="")
    parallelization: Mapped[str] = mapped_column(Text, default="")
    overhead_assumptions: Mapped[str] = mapped_column(Text, default="")
    compute_price: Mapped[dict | None] = mapped_column(JSON)
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    applicability_limits: Mapped[str] = mapped_column(Text, default="")
    review_date: Mapped[str | None] = mapped_column(String(32))
    run_id: Mapped[str | None] = mapped_column(String(32))
    finding_id: Mapped[str | None] = mapped_column(String(32))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------- job queue
class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
