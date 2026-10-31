from __future__ import annotations
import hashlib
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..models import ResearchSource, Finding, Run, Recommendation, Implementation, FINDING_STATUSES
from .. import audit, jobs, services, ai_adapter
from .common import row, rows, viewer, editor, reviewer, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}", tags=["research"])
MAX_FETCH = 2_000_000


class SourceIn(BaseModel):
    title: str = ""
    url: str | None = None
    content: str | None = None
    source_type: str = "document"
    is_demo: bool = False
    review_now: bool = True
    wait: bool = False


def _fetch_url(url: str) -> str:
    """Fetch a URL as untrusted text. Strips HTML tags. Any failure is reported, never retried silently."""
    import httpx
    if not re.match(r"^https?://", url):
        raise HTTPException(400, "only http(s) URLs are accepted")
    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": "IsogenyEvidenceLab/0.1"}) as c:
            r = c.get(url)
            r.raise_for_status()
            text = r.text[:MAX_FETCH]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"could not fetch URL ({type(e).__name__}); paste the document text instead")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@router.get("/research/sources")
def list_sources(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(ResearchSource).where(ResearchSource.project_id == project.id).order_by(ResearchSource.created_at.desc())).all())


@router.get("/research/status")
def research_status(ctx=Depends(viewer)):
    return {"ai_adapter_available": ai_adapter.available(), "extraction_method": "ai_adapter" if ai_adapter.available() else "rule_based",
            "note": ("AI adapter configured (ANTHROPIC_API_KEY set): extraction via model, validated by schema and re-matched by rules."
                     if ai_adapter.available() else "No AI provider configured: rule-based keyword extraction. Findings require human triage either way.")}


@router.post("/research/sources")
def submit_source(body: SourceIn, ctx=Depends(editor)):
    """Submit a URL or document for review. The content is stored as untrusted data and never executed."""
    project, db, user = ctx
    content = body.content or ""
    if body.url and not content:
        content = _fetch_url(body.url)
    if not content.strip():
        raise HTTPException(400, "provide content or a fetchable url")
    src = ResearchSource(project_id=project.id, title=body.title or (body.url or "Untitled document")[:200], url=body.url, content=content,
                         content_sha256=hashlib.sha256(content.encode()).hexdigest(), source_type="url" if body.url else body.source_type,
                         is_demo=body.is_demo, submitted_by=user.id)
    db.add(src)
    db.flush()
    audit.record(db, user.id, "research.source_submitted", "research_source", src.id, project.id, {"sha256": src.content_sha256, "is_demo": src.is_demo})
    job = None
    if body.review_now:
        job = jobs.enqueue(db, "research_review", {"source_id": src.id, "actor_id": user.id})
    db.commit()
    if job and body.wait:
        jobs.process_pending()
        db.expire_all()
        src = db.get(ResearchSource, src.id)
    return {**row(src), "job_id": job.id if job else None}


@router.post("/research/sources/{source_id}/review")
def trigger_review(source_id: str, wait: bool = False, ctx=Depends(editor)):
    project, db, user = ctx
    src = get_or_404(db, ResearchSource, source_id, project.id)
    job = jobs.enqueue(db, "research_review", {"source_id": src.id, "actor_id": user.id})
    db.commit()
    if wait:
        jobs.process_pending()
    return {"job_id": job.id}


# ---------------------------------------------------------------- findings
class FindingIn(BaseModel):
    title: str
    summary: str = ""
    claims: list = []
    affected: dict = {}
    affected_implementation_ids: list = []
    relevance: str = ""
    uncertainty: str = ""
    proposed_followup: dict = {}
    is_demo: bool = False


@router.get("/findings")
def list_findings(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(Finding).where(Finding.project_id == project.id).order_by(Finding.created_at.desc())).all())


@router.post("/findings")
def create_finding(body: FindingIn, ctx=Depends(editor)):
    project, db, user = ctx
    f = Finding(project_id=project.id, origin="manual", status="new", extraction_method="manual",
                status_history=[{"status": "new", "by": user.id, "note": "manual"}], **body.model_dump())
    db.add(f)
    db.flush()
    audit.record(db, user.id, "finding.created", "finding", f.id, project.id, {"title": f.title}, commit=True)
    return row(f)


@router.get("/findings/{finding_id}")
def get_finding(finding_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    f = get_or_404(db, Finding, finding_id, project.id)
    runs = [db.get(Run, rid) for rid in (f.evidence_run_ids or [])]
    impls = [db.get(Implementation, iid) for iid in (f.affected_implementation_ids or [])]
    return {**row(f), "source": row(db.get(ResearchSource, f.source_id)) if f.source_id else None,
            "recommendation": row(db.get(Recommendation, f.recommendation_id)) if f.recommendation_id else None,
            "evidence_runs": rows([r for r in runs if r]), "affected_implementations": rows([i for i in impls if i])}


class StatusIn(BaseModel):
    status: str
    note: str = ""


TRANSITIONS = {
    "new": {"triage", "not_relevant"},
    "triage": {"relevant", "not_relevant", "experiment_proposed"},
    "relevant": {"experiment_proposed", "reviewed", "not_relevant"},
    "experiment_proposed": {"reviewed", "relevant"},
    "reviewed": {"action_approved", "closed", "relevant"},
    "action_approved": {"retested"},
    "retested": {"closed", "action_approved", "reviewed"},
    "closed": {"relevant"},  # reopen
    "not_relevant": {"triage"},
}


@router.post("/findings/{finding_id}/status")
def set_status(finding_id: str, body: StatusIn, ctx=Depends(reviewer)):
    """Human-driven status changes. action_approved requires an approved recommendation; retested requires new evidence."""
    project, db, user = ctx
    f = get_or_404(db, Finding, finding_id, project.id)
    if body.status not in FINDING_STATUSES:
        raise HTTPException(400, "unknown status")
    if body.status not in TRANSITIONS.get(f.status, set()):
        raise HTTPException(409, f"cannot move finding from {f.status} to {body.status}")
    if body.status == "action_approved":
        rec = db.get(Recommendation, f.recommendation_id) if f.recommendation_id else None
        if not rec or rec.status not in ("approved", "implemented"):
            raise HTTPException(409, "a human-approved recommendation is required before action_approved")
    if body.status == "closed" and f.status == "retested":
        # a failed retest keeps the finding open
        latest = _latest_retest_run(db, f)
        if latest is None:
            raise HTTPException(409, "no retest evidence linked to this finding")
        if latest.overall_pass is not True:
            raise HTTPException(409, f"latest retest (run #{latest.sequence}) did not pass; the finding stays open")
    services.set_finding_status(db, f, body.status, user.id, body.note)
    db.commit()
    return row(f)


def _latest_retest_run(db, f: Finding):
    rec = db.get(Recommendation, f.recommendation_id) if f.recommendation_id else None
    impl_ids = set(f.affected_implementation_ids or [])
    if rec and rec.resulting_implementation_id:
        impl_ids = {rec.resulting_implementation_id}
    runs = [db.get(Run, rid) for rid in (f.evidence_run_ids or [])]
    runs = [r for r in runs if r and r.implementation_id in impl_ids and r.status == "completed"]
    return max(runs, key=lambda r: r.sequence, default=None)


class RetestIn(BaseModel):
    run_id: str


@router.post("/findings/{finding_id}/retest")
def record_retest(finding_id: str, body: RetestIn, ctx=Depends(editor)):
    """Link a new run as retest evidence. If it passes the finding moves to `retested`; if it fails it stays `action_approved` (open)."""
    project, db, user = ctx
    f = get_or_404(db, Finding, finding_id, project.id)
    run = get_or_404(db, Run, body.run_id, project.id)
    if run.id not in f.evidence_run_ids:
        f.evidence_run_ids = f.evidence_run_ids + [run.id]
    if f.status != "action_approved":
        raise HTTPException(409, f"finding must be action_approved to record a retest (is {f.status})")
    if run.status != "completed":
        raise HTTPException(409, "run has not completed")
    if run.overall_pass:
        services.set_finding_status(db, f, "retested", user.id, f"retest run #{run.sequence} passed")
    else:
        services.set_finding_status(db, f, "action_approved", user.id, f"retest run #{run.sequence} FAILED; finding remains open")
    db.commit()
    return {**row(f), "retest_passed": bool(run.overall_pass)}


class ResolveIn(BaseModel):
    baseline_run_id: str | None = None
    candidate_run_id: str
    decision: str  # close | reopen
    note: str = ""


@router.post("/findings/{finding_id}/resolve")
def resolve(finding_id: str, body: ResolveIn, ctx=Depends(reviewer)):
    """Compare evidence and close or reopen. Closing is refused when the candidate run did not pass."""
    project, db, user = ctx
    f = get_or_404(db, Finding, finding_id, project.id)
    cand = get_or_404(db, Run, body.candidate_run_id, project.id)
    if cand.id not in f.evidence_run_ids:
        f.evidence_run_ids = f.evidence_run_ids + [cand.id]
    if body.decision == "close":
        if cand.overall_pass is not True:
            raise HTTPException(409, f"candidate run #{cand.sequence} did not pass all requirements/scenarios; finding cannot be closed")
        if f.status not in ("retested", "reviewed"):
            raise HTTPException(409, f"finding must be retested/reviewed before closing (is {f.status})")
        services.set_finding_status(db, f, "closed", user.id, body.note or f"closed on evidence run #{cand.sequence}")
    elif body.decision == "reopen":
        services.set_finding_status(db, f, "relevant", user.id, body.note or f"reopened after run #{cand.sequence}")
    else:
        raise HTTPException(400, "decision must be close|reopen")
    db.commit()
    return row(f)
