"""Reproducible evidence package export (zip): manifest with SHA-256 of every member."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select

from . import artifacts as artstore
from .models import (Project, InventoryItem, Requirement, Implementation, Experiment, Run, Artifact, Recommendation,
                     Approval, Finding, ResearchSource, AttackAssessment, SandboxExperiment, AuditEvent, Task)


def _row(obj) -> dict:
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        out[c.name] = v
    return out


def build_package(db, project_id: str, runner_descriptions: list[dict]) -> tuple[bytes, dict]:
    project = db.get(Project, project_id)
    buf = io.BytesIO()
    members: dict[str, str] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def add(name: str, data: bytes):
            z.writestr(name, data)
            members[name] = hashlib.sha256(data).hexdigest()

        def add_json(name: str, obj):
            add(name, json.dumps(obj, indent=1, sort_keys=True, default=str).encode())

        tables = {
            "project": [_row(project)],
            "inventory": [_row(x) for x in db.scalars(select(InventoryItem).where(InventoryItem.project_id == project_id))],
            "requirements": [_row(x) for x in db.scalars(select(Requirement).where(Requirement.project_id == project_id))],
            "implementations": [_row(x) for x in db.scalars(select(Implementation).where(Implementation.project_id == project_id))],
            "experiments": [_row(x) for x in db.scalars(select(Experiment).where(Experiment.project_id == project_id))],
            "runs": [_row(x) for x in db.scalars(select(Run).where(Run.project_id == project_id).order_by(Run.sequence))],
            "recommendations": [_row(x) for x in db.scalars(select(Recommendation).where(Recommendation.project_id == project_id))],
            "approvals": [_row(x) for x in db.scalars(select(Approval).where(Approval.project_id == project_id))],
            "findings": [_row(x) for x in db.scalars(select(Finding).where(Finding.project_id == project_id))],
            "research_sources": [_row(x) for x in db.scalars(select(ResearchSource).where(ResearchSource.project_id == project_id))],
            "attack_assessments": [_row(x) for x in db.scalars(select(AttackAssessment).where(AttackAssessment.project_id == project_id))],
            "sandbox_experiments": [_row(x) for x in db.scalars(select(SandboxExperiment).where(SandboxExperiment.project_id == project_id))],
            "tasks": [_row(x) for x in db.scalars(select(Task).where(Task.project_id == project_id))],
            "audit": [_row(x) for x in db.scalars(select(AuditEvent).where(AuditEvent.project_id == project_id))],
        }
        for name, rows in tables.items():
            add_json(f"records/{name}.json", rows)
        arts = db.scalars(select(Artifact).where(Artifact.project_id == project_id)).all()
        art_index = []
        for a in arts:
            data = artstore.read(a)
            ok = hashlib.sha256(data).hexdigest() == a.sha256
            add(f"artifacts/{a.sha256[:12]}_{a.filename}", data)
            art_index.append({**_row(a), "integrity_ok": ok})
        add_json("records/artifacts.json", art_index)
        add_json("runners.json", runner_descriptions)
        readme = f"""Isogeny Evidence Lab — evidence package
Project: {project.name} ({project.kind})
Exported: {datetime.now(timezone.utc).isoformat()}

Contents
  records/*.json   append-only database records (runs are never edited; corrections reference supersedes_run_id)
  artifacts/       raw fixture outputs, imports, patches — file names carry the first 12 hex of the SHA-256
  runners.json     runner descriptions at export time (implemented / tested flags)
  manifest.json    SHA-256 of every member of this archive

Provenance labels: measured (fixture executed by this platform), imported (external measurement, schema+hash verified only),
illustrative (demonstration data, not a measurement).
Hashes support integrity checking of this package. They do not establish scientific validity, and passing tests is not proof of security.
"""
        add("README.txt", readme.encode())
        manifest = {"format": "iel-evidence-package/1", "project_id": project_id, "exported_at": datetime.now(timezone.utc).isoformat(),
                    "members": members}
        z.writestr("manifest.json", json.dumps(manifest, indent=1, sort_keys=True))
    data = buf.getvalue()
    return data, {"sha256": hashlib.sha256(data).hexdigest(), "members": len(members), "size": len(data)}


def verify_package(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("manifest.json"))
        bad = [n for n, h in manifest["members"].items() if hashlib.sha256(z.read(n)).hexdigest() != h]
    return {"ok": not bad, "bad_members": bad, "members": len(manifest["members"])}
