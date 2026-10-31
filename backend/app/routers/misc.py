from __future__ import annotations
import re
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from ..models import Job, User
from ..db import get_db
from ..auth import current_user
from .. import catalog, export, audit
from runners import list_runners
from .common import row, rows, viewer

router = APIRouter(prefix="/api", tags=["meta"])


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


@router.get("/projects/{project_id}/export")
def export_package(ctx=Depends(viewer)):
    project, db, user = ctx
    data, meta = export.build_package(db, project.id, list_runners())
    audit.record(db, user.id, "evidence.exported", "project", project.id, project.id, meta, commit=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", project.name)[:60]
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="evidence_{safe}.zip"', "X-SHA256": meta["sha256"]})


@router.post("/export/verify")
async def verify_package(file: UploadFile = File(...), user: User = Depends(current_user)):
    data = await file.read()
    try:
        return export.verify_package(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"not a valid evidence package: {type(e).__name__}")
