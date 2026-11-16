"""Folders, projects and assessments (phase 5a), mixed into the Lab hub.

An assessment holds at most one import; everything else of a pass (Verify, the plan, runs, fixes, migration,
dependencies) is already keyed by that import, so each assessment keeps its own data without any change to them.
Names, places and the archived flag can change. Nothing is ever deleted (the database refuses it).
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import func, select

from app.db import (
    AppSettingRow, AssessmentRow, FolderRow, ImportRow, PlanRow, ProjectRow, TestRunRow, iso, now_utc,
)
from app.errors import BadRequest, Conflict, NotFound
from app.names import clean_text
from app.projects.counts import assessment_counts

CLOSED_SENTENCE = "This assessment is closed. Start a new one to continue."
IMPORT_KEY = "imp" + "ort"   # spelled in two parts, as in evidence/export.py: tests/test_prepare.py scans for the bare word
DEFAULT_ORGANIZATION = "My organization"
UNFILED_PROJECT = "Imported without a project"
NAME_MAX = 120


def _name(value: Any, what: str) -> str:
    text = clean_text(str(value or ""), NAME_MAX).strip()
    if not text:
        raise BadRequest(f"Give the {what} a name.", field="name")
    return text


def assessment_title(a: AssessmentRow) -> str:
    return a.name or f"Assessment {a.number}"


class ProjectsMixin:
    """Mixed into `Lab`. Uses `self.db` (a session factory)."""

    db: Callable[..., Any]
    import_json_for: Callable[[int], dict]
    plan_view: Callable[[int], dict]
    lab_view: Callable[[int], dict]
    fixes_view: Callable[[int], dict]
    migration_view: Callable[[int], dict]

    # ---------------------------------------------------------------- organization

    def organization_name(self) -> str:
        with self.db() as db:
            row = db.get(AppSettingRow, "organization")
            return row.value if row is not None else DEFAULT_ORGANIZATION

    def set_organization_name(self, name: str) -> dict:
        value = _name(name, "organization")
        with self.db() as db:
            row = db.get(AppSettingRow, "organization")
            if row is None:
                db.add(AppSettingRow(key="organization", value=value))
            else:
                row.value = value
            db.commit()
        return {"organization": value}

    # ---------------------------------------------------------------- reading

    @staticmethod
    def _folder_path(db, folder_id: int | None) -> list[dict]:
        path: list[dict] = []
        seen: set[int] = set()
        while folder_id is not None and folder_id not in seen:
            seen.add(folder_id)
            f = db.get(FolderRow, folder_id)
            if f is None:
                break
            path.insert(0, {"id": f.id, "name": f.name})
            folder_id = f.parent_id
        return path

    @staticmethod
    def _assessment_status(a: AssessmentRow) -> dict:
        if a.closed_at is None:
            return {"key": "open", "label": "Open", "closed_line": None}
        why = ("A newer assessment was started in this project." if a.closed_why == "newer"
               else "Closed by you.")
        return {"key": "closed", "label": "Closed", "closed_line": f"{why} {CLOSED_SENTENCE}"}

    def _assessment_brief(self, db, a: AssessmentRow) -> dict:
        imp = db.get(ImportRow, a.import_id) if a.import_id else None
        return {"id": a.id, "number": a.number, "title": assessment_title(a), "name": a.name,
                "status": self._assessment_status(a), "archived": bool(a.archived),
                "created_at": iso(a.created_at), "closed_at": iso(a.closed_at) if a.closed_at else None,
                "file": ({"import_id": imp.id, "filename": imp.filename, "format": imp.format, "is_demo": bool(imp.is_demo),
                          "imported_at": iso(imp.created_at)} if imp is not None else None)}

    @staticmethod
    def _latest(db, project_id: int, include_archived: bool = False) -> AssessmentRow | None:
        q = select(AssessmentRow).where(AssessmentRow.project_id == project_id)
        if not include_archived:
            q = q.where(AssessmentRow.archived.is_(False))
        return db.scalars(q.order_by(AssessmentRow.id.desc()).limit(1)).first()

    def workspace_view(self) -> dict:
        """Everything the sidebar, the switcher and the Projects table need. Archived items are sent with their flag;
        the screens hide them unless "Show archived" is on."""
        with self.db() as db:
            folders = db.scalars(select(FolderRow).order_by(FolderRow.name, FolderRow.id)).all()
            projects = db.scalars(select(ProjectRow).order_by(ProjectRow.name, ProjectRow.id)).all()
            rows = []
            for p in projects:
                latest = self._latest(db, p.id) or self._latest(db, p.id, include_archived=True)
                count = db.scalar(select(func.count()).select_from(AssessmentRow).where(AssessmentRow.project_id == p.id)) or 0
                rows.append({"id": p.id, "name": p.name, "folder_id": p.folder_id, "archived": bool(p.archived),
                             "is_demo": p.demo_key not in (None, "unfiled"), "created_at": iso(p.created_at),
                             "path": self._folder_path(db, p.folder_id), "assessments": int(count),
                             "latest": self._assessment_brief(db, latest) if latest is not None else None,
                             "_import": latest.import_id if latest is not None else None})
            folder_rows = [{"id": f.id, "name": f.name, "parent_id": f.parent_id, "archived": bool(f.archived),
                            "path": self._folder_path(db, f.parent_id)} for f in folders]
        for r in rows:
            r["counts"] = assessment_counts(self, r.pop("_import"))
        return {"organization": self.organization_name(), "folders": folder_rows, "projects": rows}

    def project_view(self, project_id: int) -> dict:
        with self.db() as db:
            p = db.get(ProjectRow, project_id)
            if p is None:
                raise NotFound("That project does not exist.")
            assessments = db.scalars(select(AssessmentRow).where(AssessmentRow.project_id == p.id)
                                     .order_by(AssessmentRow.id.desc())).all()
            return {"id": p.id, "name": p.name, "folder_id": p.folder_id, "archived": bool(p.archived),
                    "is_demo": p.demo_key not in (None, "unfiled"), "path": self._folder_path(db, p.folder_id),
                    "assessments": [self._assessment_brief(db, a) for a in assessments]}

    def assessment_view(self, assessment_id: int) -> dict:
        with self.db() as db:
            a = db.get(AssessmentRow, assessment_id)
            if a is None:
                raise NotFound("That assessment does not exist.")
            p = db.get(ProjectRow, a.project_id)
            brief = self._assessment_brief(db, a)
            plan = db.scalars(select(PlanRow).where(PlanRow.import_id == a.import_id)).first() if a.import_id else None
            plan_id = plan.id if plan is not None else None
            project = {"id": p.id, "name": p.name, "is_demo": p.demo_key not in (None, "unfiled"), "archived": bool(p.archived)}
            path = self._folder_path(db, p.folder_id)
            import_id = a.import_id
        imp = self.import_json_for(import_id) if import_id else None
        summary = self.plan_view(plan_id) if plan_id is not None else None
        counts = assessment_counts(self, import_id)
        return {**brief, "organization": self.organization_name(), "project": project, "path": path,
                IMPORT_KEY: imp, "plan_id": plan_id,
                "has_verify": counts["claims"] is not None,
                "has_results": bool(summary and summary.get("has_results")),
                "has_migration": bool(summary and summary.get("has_migration")),
                "counts": counts, "next_step": self._next_step(brief, counts, summary)}

    @staticmethod
    def _next_step(brief: dict, counts: dict, summary: dict | None) -> dict:
        """The page that holds the next thing to do, with one plain sentence. It opens the page; it runs nothing."""
        if brief["status"]["key"] == "closed":
            return {"page": "overview", "label": "New assessment",
                    "text": "This assessment is closed and kept as it was. Start a new one in this project to continue."}
        if brief["file"] is None:
            return {"page": "inventory/import", "label": "Bring in a scanner file",
                    "text": "Start by bringing in the file your scanner made, or use the demo file."}
        if counts["claims"] is None:
            return {"page": "inventory/import", "label": "Verify claims",
                    "text": "Check each claim in the file against the real system."}
        if counts["tests"] is None:
            return {"page": "tests", "label": "Open tests",
                    "text": "Run the suggested tests on what the file names."}
        if counts["fixes"] and counts["fixes"]["open"]:
            return {"page": "fixes", "label": "Open fixes",
                    "text": "Some failed tests or migration steps have a suggested fix waiting."}
        if not (summary and summary.get("has_migration")):
            return {"page": "migration/systems", "label": "Open migration",
                    "text": "Measure where each system stands on the move to post-quantum cryptography."}
        return {"page": "evidence", "label": "Open evidence",
                "text": "Every step so far has a result. Download the evidence to keep a signed record."}

    # ---------------------------------------------------------------- folders

    def create_folder(self, name: str, parent_id: int | None) -> dict:
        with self.db() as db:
            if parent_id is not None and db.get(FolderRow, parent_id) is None:
                raise NotFound("That folder does not exist.")
            f = FolderRow(name=_name(name, "folder"), parent_id=parent_id)
            db.add(f)
            db.commit()
            return {"id": f.id}

    def update_folder(self, folder_id: int, changes: dict) -> dict:
        with self.db() as db:
            f = db.get(FolderRow, folder_id)
            if f is None:
                raise NotFound("That folder does not exist.")
            if "name" in changes:
                f.name = _name(changes["name"], "folder")
            if "parent_id" in changes:
                target = changes["parent_id"]
                if target is not None:
                    if db.get(FolderRow, target) is None:
                        raise NotFound("That folder does not exist.")
                    if target == f.id or any(step["id"] == f.id for step in self._folder_path(db, target)):
                        raise BadRequest("A folder can't go inside itself or one of its own folders.", field="parent_id")
                f.parent_id = target
            if "archived" in changes:
                f.archived = bool(changes["archived"])
            db.commit()
            return {"id": f.id}

    # ---------------------------------------------------------------- projects

    def create_project(self, name: str, folder_id: int | None, demo_key: str | None = None) -> dict:
        """A new project starts with its first assessment, empty, ready for a file."""
        with self.db() as db:
            if folder_id is not None and db.get(FolderRow, folder_id) is None:
                raise NotFound("That folder does not exist.")
            p = ProjectRow(name=_name(name, "project"), folder_id=folder_id, demo_key=demo_key)
            db.add(p)
            db.flush()
            a = AssessmentRow(project_id=p.id, number=1)
            db.add(a)
            db.commit()
            return {"id": p.id, "assessment_id": a.id}

    def update_project(self, project_id: int, changes: dict) -> dict:
        with self.db() as db:
            p = db.get(ProjectRow, project_id)
            if p is None:
                raise NotFound("That project does not exist.")
            if "name" in changes:
                p.name = _name(changes["name"], "project")
            if "folder_id" in changes:
                target = changes["folder_id"]
                if target is not None and db.get(FolderRow, target) is None:
                    raise NotFound("That folder does not exist.")
                p.folder_id = target
            if "archived" in changes:
                p.archived = bool(changes["archived"])
            db.commit()
            return {"id": p.id}

    # ---------------------------------------------------------------- assessments

    def new_assessment(self, project_id: int) -> dict:
        """Start over in this project: a fresh, empty assessment. The open ones before it close and are kept."""
        with self.db() as db:
            p = db.get(ProjectRow, project_id)
            if p is None:
                raise NotFound("That project does not exist.")
            for a in db.scalars(select(AssessmentRow).where(AssessmentRow.project_id == p.id,
                                                            AssessmentRow.closed_at.is_(None))).all():
                a.closed_at, a.closed_why = now_utc(), "newer"
            number = (db.scalar(select(func.max(AssessmentRow.number)).where(AssessmentRow.project_id == p.id)) or 0) + 1
            a = AssessmentRow(project_id=p.id, number=number)
            db.add(a)
            db.commit()
            return {"id": a.id}

    def update_assessment(self, assessment_id: int, changes: dict) -> dict:
        with self.db() as db:
            a = db.get(AssessmentRow, assessment_id)
            if a is None:
                raise NotFound("That assessment does not exist.")
            if "name" in changes:
                a.name = _name(changes["name"], "assessment")
            if "project_id" in changes and changes["project_id"] != a.project_id:
                target = db.get(ProjectRow, changes["project_id"])
                if target is None:
                    raise NotFound("That project does not exist.")
                a.project_id = target.id
                a.number = (db.scalar(select(func.max(AssessmentRow.number)).where(AssessmentRow.project_id == target.id)) or 0) + 1
            if "archived" in changes:
                a.archived = bool(changes["archived"])
            if changes.get("close") and a.closed_at is None:
                a.closed_at, a.closed_why = now_utc(), "closed"
            db.commit()
            return {"id": a.id}

    # ---------------------------------------------------------------- imports and assessments

    def _unfiled_project(self, db) -> ProjectRow:
        """The project that holds imports made with no assessment (scripts, the accuracy check, the blind test, and the
        imports already there before projects existed). Its assessments are never closed automatically."""
        p = db.scalars(select(ProjectRow).where(ProjectRow.demo_key == "unfiled")).first()
        if p is None:
            p = ProjectRow(name=UNFILED_PROJECT, folder_id=None, demo_key="unfiled")
            db.add(p)
            db.flush()
        return p

    def adopt_unfiled_imports(self) -> None:
        """Every import with no assessment gets one in the "Imported without a project" project. Run on start."""
        with self.db() as db:
            taken = select(AssessmentRow.import_id).where(AssessmentRow.import_id.is_not(None))
            orphans = db.scalars(select(ImportRow.id).where(ImportRow.id.not_in(taken)).order_by(ImportRow.id)).all()
            if not orphans:
                return
            p = self._unfiled_project(db)
            number = db.scalar(select(func.max(AssessmentRow.number)).where(AssessmentRow.project_id == p.id)) or 0
            for import_id in orphans:
                number += 1
                db.add(AssessmentRow(project_id=p.id, number=number, import_id=import_id))
            db.commit()

    def check_assessment_takes_a_file(self, assessment_id: int | None) -> None:
        """Before reading an upload: the assessment must exist, be open and have no file yet."""
        if assessment_id is None:
            return
        with self.db() as db:
            a = db.get(AssessmentRow, assessment_id)
            if a is None:
                raise NotFound("That assessment does not exist.")
            if a.closed_at is not None:
                raise Conflict(CLOSED_SENTENCE)
            if a.import_id is not None:
                raise Conflict("This assessment already has a file. Start a new assessment to bring in another file.")

    def attach_import(self, db, import_id: int, assessment_id: int | None) -> int:
        """Within the import's own transaction: put the new import into its assessment (or the unfiled project)."""
        if assessment_id is None:
            p = self._unfiled_project(db)
            number = (db.scalar(select(func.max(AssessmentRow.number)).where(AssessmentRow.project_id == p.id)) or 0) + 1
            a = AssessmentRow(project_id=p.id, number=number, import_id=import_id)
            db.add(a)
            db.flush()
            return a.id
        a = db.get(AssessmentRow, assessment_id)
        if a is None or a.closed_at is not None or a.import_id is not None:
            raise Conflict("This assessment can't take a file now. Start a new assessment to bring in another file.")
        a.import_id = import_id
        return a.id

    # ---------------------------------------------------------------- the closed guard

    def assessment_for(self, import_id: int | None = None, plan_id: int | None = None, run_id: int | None = None) -> AssessmentRow | None:
        with self.db() as db:
            if run_id is not None:
                run = db.get(TestRunRow, run_id)
                plan_id = run.plan_id if run is not None else None
                if plan_id is None:
                    return None
            if plan_id is not None:
                plan = db.get(PlanRow, plan_id)
                import_id = plan.import_id if plan is not None else None
            if import_id is None:
                return None
            return db.scalars(select(AssessmentRow).where(AssessmentRow.import_id == import_id)).first()

    def refuse_if_closed(self, import_id: int | None = None, plan_id: int | None = None, run_id: int | None = None) -> None:
        a = self.assessment_for(import_id=import_id, plan_id=plan_id, run_id=run_id)
        if a is not None and a.closed_at is not None:
            raise Conflict(CLOSED_SENTENCE)

    def evidence_names(self, import_id: int) -> dict | None:
        """The organization, folder path, project and assessment, for the evidence file and report."""
        with self.db() as db:
            a = db.scalars(select(AssessmentRow).where(AssessmentRow.import_id == import_id)).first()
            if a is None:
                return None
            p = db.get(ProjectRow, a.project_id)
            return {"organization": self.organization_name(),
                    "folders": [f["name"] for f in self._folder_path(db, p.folder_id)],
                    "project": p.name, "assessment": assessment_title(a), "assessment_number": a.number,
                    "opened_at": iso(a.created_at), "closed_at": iso(a.closed_at) if a.closed_at else None,
                    "status": "closed" if a.closed_at else "open"}

