from __future__ import annotations
import base64
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..models import Implementation, Run, Recommendation, Artifact, Finding, InventoryItem, utcnow
from .. import audit, catalog, compat, services
from .. import artifacts as artstore
from .common import row, rows, viewer, editor, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}/implementations", tags=["implementations"])


class ManifestIn(BaseModel):
    """Structured implementation manifest. See seeds/sample_manifest_v1_0.json."""
    name: str
    version: str
    purpose: str = "signatures"
    algorithm: str = ""
    parameters: dict = {}
    library: str = ""
    library_version: str = ""
    dependencies: list = []
    configuration: dict = {}
    runtime_environment: dict = {}
    source_revision: str = ""
    build_identity: dict = {}
    intended_use: str = ""
    threat_assumptions: str = ""
    adapter_kind: str = "results_only"  # profile | module | results_only
    profile_id: str | None = None
    parent_id: str | None = None
    recommendation_id: str | None = None
    change_report: str = ""
    notes: str = ""
    manifest: dict = {}


class ImportIn(BaseModel):
    manifest: ManifestIn
    source_snapshot_b64: str | None = None   # .py or .zip, base64
    source_snapshot_filename: str | None = None
    inventory: list = []                     # [{category, name, purpose, version, parameters, provenance}]
    existing_results: dict | None = None     # optional result document (unsigned) -> imported_results run


def _present(db, i: Implementation) -> dict:
    runs = db.scalars(select(Run).where(Run.implementation_id == i.id)).all()
    latest = next((r for r in sorted(runs, key=lambda r: -r.sequence) if r.status == "completed" and not r.duplicate_of_run_id and not r.stale_reason), None)
    return {**row(i), "run_count": len([r for r in runs if not r.duplicate_of_run_id]), "latest_classification": latest.classification if latest else "not_tested",
            "profile": catalog.profile(i.profile_id) if i.profile_id else None, "snapshot": row(db.get(Artifact, i.source_snapshot_artifact_id)) if i.source_snapshot_artifact_id else None}


@router.get("")
def list_impls(ctx=Depends(viewer)):
    project, db, _ = ctx
    return [_present(db, i) for i in db.scalars(select(Implementation).where(Implementation.project_id == project.id).order_by(Implementation.imported_at)).all()]


@router.post("/import")
def import_implementation(body: ImportIn, ctx=Depends(editor)):
    """Import an implementation version. Code is checked statically; it is never executed on import."""
    project, db, user = ctx
    m = body.manifest
    if m.purpose not in ("signatures", "key_establishment", "encryption"):
        raise HTTPException(400, "purpose must be signatures | key_establishment | encryption")
    if m.adapter_kind not in ("profile", "module", "results_only"):
        raise HTTPException(400, "adapter_kind must be profile | module | results_only")
    if m.adapter_kind == "profile" and not catalog.profile(m.profile_id or ""):
        raise HTTPException(400, "profile adapters need a known catalog profile_id")
    if compat.scan_secrets(str(m.model_dump()).encode()):
        raise HTTPException(400, "manifest contains private-key or credential material; rejected")
    if db.scalar(select(Implementation).where(Implementation.project_id == project.id, Implementation.name == m.name, Implementation.version == m.version)):
        raise HTTPException(409, f"{m.name} {m.version} is already imported; import a new version instead")
    impl = Implementation(project_id=project.id, created_by=user.id, status="imported", imported_at=utcnow(),
                          **{k: v for k, v in m.model_dump().items()})
    if not impl.manifest:
        impl.manifest = m.model_dump(exclude={"manifest"})
    db.add(impl)
    db.flush()
    compat_report = {"status": "unchecked", "problems": [], "warnings": [], "report": []}
    if body.source_snapshot_b64:
        data = base64.b64decode(body.source_snapshot_b64)
        fname = body.source_snapshot_filename or "adapter.py"
        try:
            files = compat.extract_snapshot(data, fname)
            compat_report = compat.check_snapshot(files)
        except ValueError as e:
            db.rollback()
            raise HTTPException(400, f"source snapshot rejected: {e}")
        art = artstore.store(db, project.id, "source_snapshot", fname, data, "application/octet-stream", label=f"source snapshot of {impl.name} {impl.version}")
        impl.source_snapshot_artifact_id, impl.source_digest = art.id, art.sha256
        if impl.adapter_kind == "module":
            impl.compatibility = compat_report
        else:
            impl.compatibility = {**compat_report, "note": "snapshot stored for reference; adapter_kind is not 'module' so it will not execute"}
    elif impl.adapter_kind == "module":
        db.rollback()
        raise HTTPException(400, "adapter_kind 'module' requires a source snapshot")
    else:
        impl.compatibility = {"status": "compatible" if impl.adapter_kind == "profile" else "unsupported",
                              "report": ["catalog profile adapter"] if impl.adapter_kind == "profile" else ["results-only: no executable adapter; import results"], "problems": [], "warnings": []}
    if m.parent_id:
        parent = db.get(Implementation, m.parent_id)
        if parent and parent.project_id == project.id and parent.status in ("imported", "baseline", "candidate"):
            parent.status = "superseded"
    if m.recommendation_id:
        rec = db.get(Recommendation, m.recommendation_id)
        if rec and rec.project_id == project.id:
            rec.resulting_implementation_id = impl.id
            for f in db.scalars(select(Finding).where(Finding.recommendation_id == rec.id)).all():
                f.revised_implementation_id = impl.id
                if f.status in ("recommendation_proposed", "open", "external_change_reported"):
                    services.set_finding_status(db, f, "external_change_reported", user.id, f"revised implementation {impl.name} {impl.version} imported: {m.change_report[:120]}")
                    services.set_finding_status(db, f, "awaiting_retest", user.id, "awaiting retest of the revised implementation")
    for raw in body.inventory:
        prov = raw.get("provenance", "user_reported")
        if prov not in ("user_reported", "detected"):
            prov = "user_reported"
        db.add(InventoryItem(project_id=project.id, implementation_id=impl.id, category=raw.get("category", "other"), name=raw.get("name", ""),
                             purpose=raw.get("purpose"), parameters=raw.get("parameters", {}), version=raw.get("version"), notes=raw.get("notes", ""),
                             provenance=prov, provenance_detail=raw.get("provenance_detail", "from import manifest")))
    # detected facts from the manifest itself
    for cat_, name, ver in (("algorithm", impl.algorithm, None), ("library", impl.library, impl.library_version)):
        if name:
            db.add(InventoryItem(project_id=project.id, implementation_id=impl.id, category=cat_, name=name, purpose=impl.purpose, version=ver,
                                 provenance="user_reported", provenance_detail="declared in the import manifest"))
    existing_run = None
    if body.existing_results:
        from ..routers.tests import _import_results_doc
        existing_run = _import_results_doc(db, project, impl, body.existing_results, user)
    audit.record(db, user.id, "implementation.imported", "implementation", impl.id, project.id,
                 {"name": impl.name, "version": impl.version, "adapter_kind": impl.adapter_kind, "compatibility": impl.compatibility.get("status"), "source_digest": impl.source_digest}, commit=True)
    return {**_present(db, impl), "existing_results_run_id": existing_run.id if existing_run else None}


@router.get("/{impl_id}")
def get_impl(impl_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    i = get_or_404(db, Implementation, impl_id, project.id)
    runs = db.scalars(select(Run).where(Run.implementation_id == i.id).order_by(Run.sequence)).all()
    children = db.scalars(select(Implementation).where(Implementation.parent_id == i.id)).all()
    inv = db.scalars(select(InventoryItem).where(InventoryItem.implementation_id == i.id)).all()
    findings = [f for f in db.scalars(select(Finding).where(Finding.project_id == project.id)).all() if i.id in (f.affected_implementation_ids or []) or f.revised_implementation_id == i.id]
    return {**_present(db, i), "runs": rows(runs), "children": rows(children), "parent": row(db.get(Implementation, i.parent_id)) if i.parent_id else None,
            "inventory": rows(inv), "findings": [{"id": f.id, "title": f.title, "status": f.status, "role": "affected" if i.id in (f.affected_implementation_ids or []) else "revised"} for f in findings],
            "recommendation": row(db.get(Recommendation, i.recommendation_id)) if i.recommendation_id else None}


class StatusIn(BaseModel):
    status: str
    note: str = ""


@router.post("/{impl_id}/status")
def set_status(impl_id: str, body: StatusIn, ctx=Depends(editor)):
    project, db, user = ctx
    i = get_or_404(db, Implementation, impl_id, project.id)
    if body.status not in ("imported", "baseline", "candidate", "superseded", "retired"):
        raise HTTPException(400, "bad status")
    i.status = body.status
    audit.record(db, user.id, "implementation.status", "implementation", i.id, project.id, {"status": body.status, "note": body.note}, commit=True)
    return row(i)


@router.get("/{impl_id}/snapshot")
def get_snapshot(impl_id: str, ctx=Depends(viewer)):
    """Source snapshot listing and the adapter source (read-only display)."""
    project, db, _ = ctx
    i = get_or_404(db, Implementation, impl_id, project.id)
    if not i.source_snapshot_artifact_id:
        raise HTTPException(404, "no snapshot")
    art = db.get(Artifact, i.source_snapshot_artifact_id)
    files = compat.extract_snapshot(artstore.read(art), art.filename)
    return {"artifact": row(art), "files": {n: {"size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()},
            "adapter_source": files.get("adapter.py", b"").decode("utf-8", errors="replace")[:20000]}
