from __future__ import annotations
import json
import re
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from ..db import get_db
from ..auth import current_user
from ..models import EvidenceBundle, TrustedKey, Run, Artifact, Job, User, utcnow
from .. import audit, catalog, export, signing
from .. import artifacts as artstore
from iel_tools import attest
from runners import list_runners
from .common import row, rows, viewer, editor, owner, get_or_404

router = APIRouter(prefix="/api", tags=["evidence"])


@router.get("/projects/{project_id}/bundles")
def list_bundles(ctx=Depends(viewer)):
    project, db, _ = ctx
    out = []
    for b in db.scalars(select(EvidenceBundle).where(EvidenceBundle.project_id == project.id).order_by(EvidenceBundle.created_at)).all():
        r = db.get(Run, b.run_id)
        out.append({**row(b), "envelope": None, "statement": None, "run_sequence": r.sequence if r else None, "labels": [l["label"] for l in r.evidence_labels] if r else [],
                    "classification": r.classification if r else None})
    return out


@router.get("/projects/{project_id}/bundles/{bid}")
def get_bundle(bid: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    b = get_or_404(db, EvidenceBundle, bid, project.id)
    r = db.get(Run, b.run_id)
    trusted = signing.trusted_keys_for(db, project.id, "customer_runner" if b.kind == "customer_runner" else "platform")
    arts = {}
    if r and r.raw_output_artifact_id:
        arts["raw_output.json"] = artstore.read(db.get(Artifact, r.raw_output_artifact_id))
    live = attest.verify_envelope(b.envelope, trusted, arts if arts else None)
    return {**row(b), "run": row(r), "labels": r.evidence_labels if r else [],
            "live_verification": {"ok": live.ok, "signature_verified": live.signature_verified, "signer_trusted": live.signer_trusted, "signer": live.signer_name,
                                  "digests": live.digests_checked, "problems": live.problems, "verified": live.verified, "unverified": live.unverified},
            "bundle_artifact": row(db.get(Artifact, b.bundle_artifact_id)) if b.bundle_artifact_id else None,
            "cairn": {"configured": False, "note": "Cairn checker not configured in this deployment; results are locally recorded or imported. No Cairn label is ever applied."}}


# ---------------------------------------------------------------- trusted keys (trust policy)
class KeyIn(BaseModel):
    name: str
    public_key_pem: str
    purpose: str = "customer_runner"
    note: str = ""


@router.get("/projects/{project_id}/trusted-keys")
def list_keys(ctx=Depends(viewer)):
    project, db, _ = ctx
    ks = [k for k in db.scalars(select(TrustedKey)).all() if k.project_id in (None, project.id)]
    return [{**row(k), "scope": "platform-wide" if k.project_id is None else "project"} for k in ks]


@router.post("/projects/{project_id}/trusted-keys")
def add_key(body: KeyIn, ctx=Depends(owner)):
    project, db, user = ctx
    if body.purpose != "customer_runner":
        raise HTTPException(400, "projects may only register customer_runner keys")
    try:
        pub = attest.public_key_from_pem(body.public_key_pem)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"not a valid Ed25519 public key PEM: {type(e).__name__}")
    if "PRIVATE" in body.public_key_pem:
        raise HTTPException(400, "that is a private key; register the PUBLIC key only")
    kid = attest.key_id(pub)
    if db.scalar(select(TrustedKey).where(TrustedKey.key_id == kid, TrustedKey.project_id == project.id)):
        raise HTTPException(409, "key already registered")
    k = TrustedKey(project_id=project.id, key_id=kid, name=body.name, public_key_pem=body.public_key_pem, purpose="customer_runner", status="active", note=body.note, added_by=user.id)
    db.add(k)
    db.flush()
    audit.record(db, user.id, "trusted_key.added", "trusted_key", k.id, project.id, {"key_id": kid, "name": body.name}, commit=True)
    return row(k)


@router.post("/projects/{project_id}/trusted-keys/{kid}/revoke")
def revoke_key(kid: str, ctx=Depends(owner)):
    project, db, user = ctx
    k = db.get(TrustedKey, kid)
    if not k or k.project_id != project.id:
        raise HTTPException(404, "key not found in this project")
    k.status, k.revoked_at = "revoked", utcnow()
    audit.record(db, user.id, "trusted_key.revoked", "trusted_key", k.id, project.id, {"key_id": k.key_id}, commit=True)
    return row(k)


@router.get("/platform-key")
def platform_key(user: User = Depends(current_user)):
    """Platform public key for the standalone verifier (distribute out-of-band; never trust a key found inside a bundle)."""
    return {"key_id": signing.platform_key_id(), "public_key_pem": signing.platform_public_pem(), "algorithm": "Ed25519",
            "distribution": "Copy this PEM into your verifier trust file. Rotation and revocation: see docs/ATTESTATION.md."}


# ---------------------------------------------------------------- exports
def _fname(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:60]


@router.get("/projects/{project_id}/export/package")
def export_package(ctx=Depends(viewer)):
    project, db, user = ctx
    data, meta = export.build_package(db, project.id, list_runners())
    audit.record(db, user.id, "evidence.exported", "project", project.id, project.id, meta, commit=True)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="evidence_{_fname(project.name)}.zip"', "X-SHA256": meta["sha256"]})


@router.get("/projects/{project_id}/export/handoff")
def export_handoff(format: str = "json", ctx=Depends(viewer)):
    project, db, user = ctx
    doc = export.build_handoff(db, project.id)
    audit.record(db, user.id, "handoff.exported", "project", project.id, project.id, {"format": format}, commit=True)
    if format == "html":
        return HTMLResponse(export.handoff_html(doc), headers={"Content-Disposition": f'inline; filename="handoff_{_fname(project.name)}.html"'})
    return doc


class ComplianceIn(BaseModel):
    applicability: dict = {}
    format: str = "json"


@router.post("/projects/{project_id}/export/compliance")
def export_compliance(body: ComplianceIn, ctx=Depends(viewer)):
    project, db, user = ctx
    doc = export.build_compliance(db, project.id, body.applicability)
    audit.record(db, user.id, "compliance.exported", "project", project.id, project.id, {"format": body.format}, commit=True)
    if body.format == "html":
        return HTMLResponse(export.compliance_html(doc))
    return doc


@router.post("/export/verify-package")
async def verify_package(file: UploadFile = File(...), user: User = Depends(current_user)):
    data = await file.read()
    try:
        return export.verify_package(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"not a valid evidence package: {type(e).__name__}")


class VerifyIn(BaseModel):
    bundle: dict
    trusted_keys_pem: list[str] = []


@router.post("/verify-bundle")
def verify_bundle(body: VerifyIn, user: User = Depends(current_user)):
    """Same checks as the standalone verifier, for convenience. Trust comes only from the supplied PEMs."""
    trusted = {}
    for pem in body.trusted_keys_pem:
        try:
            pub = attest.public_key_from_pem(pem)
            trusted[attest.key_id(pub)] = (f"supplied key {attest.key_id(pub)[:12]}…", pub)
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "a supplied key is not a valid Ed25519 public key PEM")
    try:
        env, arts = attest.load_bundle(body.bundle)
    except ValueError as e:
        raise HTTPException(400, str(e))
    r = attest.verify_envelope(env, trusted, arts)
    return {"ok": r.ok, "signature_verified": r.signature_verified, "signer_trusted": r.signer_trusted, "keyid": r.keyid, "digests": r.digests_checked,
            "problems": r.problems, "verified": r.verified, "unverified": r.unverified}


# ---------------------------------------------------------------- system
@router.get("/catalog")
def get_catalog(user: User = Depends(current_user)):
    return catalog.catalog_summary()


@router.get("/runners")
def runners(user: User = Depends(current_user)):
    return list_runners()


@router.get("/jobs")
def jobs_list(db=Depends(get_db), user: User = Depends(current_user)):
    return rows(db.scalars(select(Job).order_by(Job.created_at.desc()).limit(50)).all())


@router.get("/jobs/{job_id}")
def job(job_id: str, db=Depends(get_db), user: User = Depends(current_user)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return row(j)
