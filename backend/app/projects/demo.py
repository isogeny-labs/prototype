"""Load demo projects (phase 5a): a "Demo" folder with one project per demo file, each with its first assessment and
the file already imported, exactly as Import does it today (its notices, its Demo data label, and the local test
servers that file starts). Running it again adds nothing: each project is added once (by its key), even if archived.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.config import DEMO_DIR
from app.db import AssessmentRow, FolderRow, ProjectRow
from app.lab import actions
from app.servers import extra_servers, migration_servers

# (key, project name, demo file)
DEMO_PROJECTS: tuple[tuple[str, str, str], ...] = (
    ("acme-pay", "Acme Pay", "acme-pay-cbom.json"),
    ("migration", "Migration demo", "migration-demo.csv"),
    ("multi-target", "Multi-target", "multi-target-demo.csv"),
    ("lab-nginx", "Lab nginx (isolated mode)", "lab-nginx.csv"),
    ("real-libraries", "Real libraries (isolated mode)", "real-libraries.csv"),
    ("real-servers", "Real public servers (needs internet)", "migration-real-servers.csv"),
)


def demo_file_bytes(lab: Any, filename: str) -> bytes:
    """The bundled demo file as this app imports it (also used by Rerun for a demo file brought in before phase 5b)."""
    return _file(lab, filename)


def _file(lab: Any, filename: str) -> bytes:
    """The demo file with this app's own ports written in (the same files the e2e walks and the buttons use)."""
    s = lab.settings
    if filename == "migration-demo.csv":
        return migration_servers.file_for(s.migration_ports)
    if filename == "multi-target-demo.csv":
        return extra_servers.file_for(s.demo_tls_port, s.extra_ports)
    if filename == "lab-nginx.csv":
        return lab._lab_nginx_file()
    return (DEMO_DIR / filename).read_bytes()


def load_demo_projects(lab: Any) -> dict:
    added: list[str] = []
    notices: list[str] = []
    with lab.db() as db:
        folder = db.scalars(select(FolderRow).where(FolderRow.system_key == "demo")).first()
        if folder is None:
            folder = FolderRow(name="Demo", parent_id=None, system_key="demo")
            db.add(folder)
            db.commit()
        folder_id = folder.id
        have = set(db.scalars(select(ProjectRow.demo_key).where(ProjectRow.demo_key.is_not(None))).all())
    # (who did what: each assessment and file made here is recorded as made with this one button)
    with actions.through(actions.LOAD_DEMO_PROJECTS):
        for key, name, filename in DEMO_PROJECTS:
            if key in have:
                continue
            made = lab.create_project(name, folder_id, demo_key=key)
            if key == "acme-pay":
                imported = lab.import_demo(assessment_id=made["assessment_id"])
            else:
                imported = lab.import_file(filename, _file(lab, filename), assessment_id=made["assessment_id"])
            added.append(name)
            notices.extend(f"{name}: {n}" for n in imported.get("notices") or [])
    with lab.db() as db:
        first = db.scalars(
            select(AssessmentRow)
            .join(ProjectRow, ProjectRow.id == AssessmentRow.project_id)
            .where(ProjectRow.demo_key == "acme-pay")
            .order_by(AssessmentRow.id.desc())
            .limit(1)
        ).first()
    summary = (
        f"Added {len(added)} demo projects in the Demo folder: {', '.join(added)}."
        if added
        else "The demo projects are already here. Nothing was added."
    )
    return {"added": added, "summary": summary, "notices": notices, "open_assessment_id": first.id if first else None}
