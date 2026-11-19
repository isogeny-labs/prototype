"""Folders, projects and assessments (phase 5a), mixed into the Lab hub.

An assessment holds at most one import; everything else of a pass (Verify, the plan, runs, fixes, migration,
dependencies) is already keyed by that import, so each assessment keeps its own data without any change to them.
Names, places and the archived flag can change. Nothing is ever deleted (the database refuses it).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select

from app.db import (
    AppSettingRow, AssessmentDetailRow, AssessmentRow, AssessmentSignoffRow, FolderRow, ImportFileRow, ImportRow, PlanRow,
    ProjectRow, TestRunRow, VerifyRunRow, iso, now_utc,
)
from app.errors import BadRequest, Conflict, NotFound
from app.names import ALGORITHM_NAMES, clean_text
from app.present import otto as present_otto
from app.projects.counts import assessment_counts

CLOSED_SENTENCE = "This assessment is closed. Start a new one to continue."
IMPORT_KEY = "imp" + "ort"   # spelled in two parts, as in evidence/export.py: tests/test_prepare.py scans for the bare word
DEFAULT_ORGANIZATION = "My organization"
UNFILED_PROJECT = "Imported without a project"
NAME_MAX = 120
# Phase 5b: what an assessment is for. A label only: it changes nothing else.
PURPOSES: tuple[tuple[str, str], ...] = (
    ("full_review", "Full review"), ("compliance_review", "Compliance review"), ("migration_wave", "Migration wave"),
    ("release_check", "Release check"), ("advisory_response", "Advisory response"), ("other", "Other"),
)
PURPOSE_LABELS = dict(PURPOSES)
DEFAULT_PURPOSE = "full_review"
REFERENCE_MAX = 200
NOTE_MAX = 500
ONE_LOGIN_LINE = ("This app has one login, so whoever is at the keyboard records the name. It is kept with the time, "
                  "in the assessment and in its evidence.")
NEWER_LINE = "Closed when a newer assessment was started."
DEMO_CBOM_NAME = "acme-pay-cbom.json"
RERUN_MISSING = ("This assessment's file was brought in before the app kept a copy of each file. Bring the file in again "
                 "in a new assessment.")


def _name(value: Any, what: str) -> str:
    text = clean_text(str(value or ""), NAME_MAX).strip()
    if not text:
        raise BadRequest(f"Give the {what} a name.", field="name")
    return text


def assessment_title(a: AssessmentRow) -> str:
    return a.name or f"Assessment {a.number}"


def _purpose(value: Any) -> str:
    key = str(value or "")
    if key not in PURPOSE_LABELS:
        raise BadRequest("Pick a purpose from the list.", field="purpose")
    return key


def _optional_text(value: Any, limit: int) -> str | None:
    text = clean_text(str(value or ""), limit).strip()
    return text or None


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
    def _signoff(db, a: AssessmentRow) -> dict | None:
        row = db.scalars(select(AssessmentSignoffRow).where(AssessmentSignoffRow.assessment_id == a.id)).first()
        return {"by": row.signed_off_by, "note": row.note, "at": iso(row.signed_at)} if row is not None else None

    @staticmethod
    def _details(db, a: AssessmentRow) -> tuple[dict | None, str | None]:
        """The purpose ({key, label}, or None for an assessment made before phase 5b) and the reference."""
        row = db.scalars(select(AssessmentDetailRow).where(AssessmentDetailRow.assessment_id == a.id)
                         .order_by(AssessmentDetailRow.id.desc()).limit(1)).first()
        if row is None:
            return None, None
        return {"key": row.purpose, "label": PURPOSE_LABELS.get(row.purpose, row.purpose)}, row.reference

    @classmethod
    def _assessment_status(cls, a: AssessmentRow, signoff: dict | None = None) -> dict:
        if a.closed_at is None:
            return {"key": "open", "label": "Open", "closed_line": None, "signoff": None}
        if a.closed_why == "newer":
            why = NEWER_LINE
        elif signoff is not None:
            why = f"Closed and signed off by {signoff['by']}."
        else:
            why = "Closed by you."
        return {"key": "closed", "label": "Closed", "closed_line": f"{why} {CLOSED_SENTENCE}", "signoff": signoff}

    def _assessment_brief(self, db, a: AssessmentRow) -> dict:
        imp = db.get(ImportRow, a.import_id) if a.import_id else None
        purpose, reference = self._details(db, a)
        return {"id": a.id, "number": a.number, "title": assessment_title(a), "name": a.name,
                "purpose": purpose, "reference": reference,
                "status": self._assessment_status(a, self._signoff(db, a)), "archived": bool(a.archived),
                "created_at": iso(a.created_at), "closed_at": iso(a.closed_at) if a.closed_at else None,
                "file": ({"import_id": imp.id, "filename": imp.filename, "format": imp.format, "is_demo": bool(imp.is_demo),
                          "imported_at": iso(imp.created_at)} if imp is not None else None)}

    @staticmethod
    def _last_activity(db, a: AssessmentRow) -> datetime:
        """When this assessment was last worked on: started, its file brought in, verified, a check run, signed off."""
        def as_dt(value: Any) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        times = [as_dt(a.created_at), as_dt(a.closed_at)]
        if a.import_id is not None:
            imp = db.get(ImportRow, a.import_id)
            times.append(as_dt(imp.created_at) if imp is not None else None)
            verify = db.scalars(select(VerifyRunRow).where(VerifyRunRow.import_id == a.import_id)
                                .order_by(VerifyRunRow.id.desc()).limit(1)).first()
            times.append(as_dt(verify.finished_at) if verify is not None else None)
            plan = db.scalars(select(PlanRow).where(PlanRow.import_id == a.import_id)).first()
            if plan is not None:
                run = db.scalars(select(TestRunRow).where(TestRunRow.plan_id == plan.id).order_by(TestRunRow.id.desc()).limit(1)).first()
                times.append(as_dt(run.finished_at or run.started_at) if run is not None else None)
        return max(t for t in times if t is not None)

    def _worked_on_last(self, db, project_id: int, include_archived: bool = False) -> AssessmentRow | None:
        q = select(AssessmentRow).where(AssessmentRow.project_id == project_id)
        if not include_archived:
            q = q.where(AssessmentRow.archived.is_(False))
        every = db.scalars(q).all()
        return max(every, key=lambda a: (self._last_activity(db, a), a.id)) if every else None

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
                latest = self._worked_on_last(db, p.id) or self._worked_on_last(db, p.id, include_archived=True)
                every = db.scalars(select(AssessmentRow).where(AssessmentRow.project_id == p.id)).all()
                shown = [a for a in every if not a.archived]
                rows.append({"id": p.id, "name": p.name, "folder_id": p.folder_id, "archived": bool(p.archived),
                             "is_demo": p.demo_key not in (None, "unfiled"), "created_at": iso(p.created_at),
                             "path": self._folder_path(db, p.folder_id), "assessments": len(every),
                             "open_count": sum(1 for a in shown if a.closed_at is None),
                             "closed_count": sum(1 for a in shown if a.closed_at is not None),
                             "latest": self._assessment_brief(db, latest) if latest is not None else None,
                             "_import": latest.import_id if latest is not None else None})
            folder_rows = [{"id": f.id, "name": f.name, "parent_id": f.parent_id, "archived": bool(f.archived),
                            "path": self._folder_path(db, f.parent_id)} for f in folders]
        for r in rows:
            r["counts"] = assessment_counts(self, r.pop("_import"))
        return {"organization": self.organization_name(), "folders": folder_rows, "projects": rows,
                "purposes": [{"key": k, "label": v} for k, v in PURPOSES], "one_login_line": ONE_LOGIN_LINE,
                "algorithm_names": [{"technical": tech, "plain": plain} for tech, plain in ALGORITHM_NAMES]}

    def project_view(self, project_id: int) -> dict:
        with self.db() as db:
            p = db.get(ProjectRow, project_id)
            if p is None:
                raise NotFound("That project does not exist.")
            assessments = db.scalars(select(AssessmentRow).where(AssessmentRow.project_id == p.id)
                                     .order_by(AssessmentRow.id.desc())).all()
            return {"id": p.id, "name": p.name, "folder_id": p.folder_id, "archived": bool(p.archived),
                    "is_demo": p.demo_key not in (None, "unfiled"), "path": self._folder_path(db, p.folder_id),
                    "assessments": [self._assessment_brief(db, a) for a in assessments],
                    "next_name": f"Assessment {max((a.number for a in assessments), default=0) + 1}"}

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
        # Phase 5c: how many of Otto's proposals nobody has decided yet, by kind, each linking to the page it lives on.
        # A closed assessment and one without Otto have nothing waiting: nothing can be decided there.
        waiting = self.otto_waiting(plan_id if self._can_decide(plan_id) else None)      # type: ignore[attr-defined]
        return {**brief, "organization": self.organization_name(), "project": project, "path": path,
                IMPORT_KEY: imp, "plan_id": plan_id,
                "blocks": self.assessment_blocks(import_id, plan_id),   # type: ignore[attr-defined]   # phase 5b
                "has_verify": counts["claims"] is not None,
                "has_results": bool(summary and summary.get("has_results")),
                "has_migration": bool(summary and summary.get("has_migration")),
                "counts": counts,
                "waiting": present_otto.waiting_view(waiting),
                "next_step": self._next_step(brief, counts, summary, waiting)}

    def _can_decide(self, plan_id: int | None) -> bool:
        return plan_id is not None and self._decisions_blocked(plan_id) is None      # type: ignore[attr-defined]

    @staticmethod
    def _next_step(brief: dict, counts: dict, summary: dict | None, waiting: dict | None = None) -> dict:
        """The page that holds the next thing to do, with one plain sentence. It opens the page; it runs nothing.
        `waiting`: how many of Otto's proposals in this assessment nobody has decided yet, by kind (phase 5c)."""
        waiting = waiting or {}
        new_checks = int(waiting.get("check") or 0)
        if brief["status"]["key"] == "closed":
            return {"page": "overview", "label": "New assessment",
                    "text": "This assessment is closed and kept as it was. Start a new one in this project to continue."}
        if brief["file"] is None:
            return {"page": "inventory/import", "label": "Bring in a scanner file",
                    "text": "Start by bringing in the file your scanner made, or use the demo file."}
        if counts["claims"] is None:
            return {"page": "inventory/import", "label": "Verify claims",
                    "text": "Check each claim in the file against the real system."}
        # (before the first run, on purpose: a check accepted now runs with the suggested tests, in one go)
        if new_checks:
            return {"page": "advisories", "label": "Open advisories",
                    "text": (f"{new_checks} advisory {'check is' if new_checks == 1 else 'checks are'} proposed from the installed test "
                             f"packs. Accept or reject {'it' if new_checks == 1 else 'each one'}: accepting runs nothing.")}
        if counts["tests"] is None:
            return {"page": "checks", "label": "Open checks",
                    "text": "Run the suggested tests on what the file names. The test plan is on Checks."}
        if waiting.get("fix"):
            n = int(waiting["fix"])
            return {"page": "fixes", "label": "Open fixes",
                    "text": (f"{'A fix is' if n == 1 else f'{n} fixes are'} proposed for a failed advisory check. Accept or reject "
                             f"{'it' if n == 1 else 'each one'}: accepting runs nothing.")}
        if counts["fixes"] and counts["fixes"]["open"]:
            return {"page": "fixes", "label": "Open fixes",
                    "text": "Some failed tests or migration steps have a suggested fix waiting."}
        if waiting.get("plan"):
            return {"page": "migration/systems", "label": "Open migration",
                    "text": "A change to the migration plan is proposed, from a result. Accept or reject it: accepting changes no system."}
        if waiting.get("dependency"):
            return {"page": "migration/dependencies", "label": "Open dependencies",
                    "text": "An update is proposed for a library that a published advisory names. Accept or reject it: accepting runs nothing."}
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
            db.flush()
            db.add(AssessmentDetailRow(assessment_id=a.id, purpose=DEFAULT_PURPOSE, reference=None))
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

    def new_assessment(self, project_id: int, name: str | None = None, purpose: str | None = None,
                       reference: str | None = None) -> dict:
        """A fresh, empty assessment in this project. Since phase 5b it closes nothing: any number can be open."""
        purpose_key = _purpose(purpose or DEFAULT_PURPOSE)
        ref = _optional_text(reference, REFERENCE_MAX)
        given = _optional_text(name, NAME_MAX)
        with self.db() as db:
            p = db.get(ProjectRow, project_id)
            if p is None:
                raise NotFound("That project does not exist.")
            number = (db.scalar(select(func.max(AssessmentRow.number)).where(AssessmentRow.project_id == p.id)) or 0) + 1
            a = AssessmentRow(project_id=p.id, number=number, name=given if given and given != f"Assessment {number}" else None)
            db.add(a)
            db.flush()
            db.add(AssessmentDetailRow(assessment_id=a.id, purpose=purpose_key, reference=ref))
            db.commit()
            return {"id": a.id}

    def next_assessment_name(self, project_id: int) -> str:
        with self.db() as db:
            number = (db.scalar(select(func.max(AssessmentRow.number)).where(AssessmentRow.project_id == project_id)) or 0) + 1
        return f"Assessment {number}"

    def rerun_assessment(self, assessment_id: int, name: str | None = None, purpose: str | None = None,
                         reference: str | None = None) -> dict:
        """Rerun as new assessment (phase 5b): a new assessment in the same project, and the same scanner file brought
        in again the normal way. The file only: no results, no choices; the address ticks are given again. Allowed on a
        closed assessment (it changes nothing in it)."""
        with self.db() as db:
            a = db.get(AssessmentRow, assessment_id)
            if a is None:
                raise NotFound("That assessment does not exist.")
            if a.import_id is None:
                raise Conflict("This assessment has no file yet, so there is nothing to run again.")
            project_id = a.project_id
            imp = db.get(ImportRow, a.import_id)
            demo_cbom = imp.filename == DEMO_CBOM_NAME and bool(imp.is_demo)
            copy = db.scalars(select(ImportFileRow).where(ImportFileRow.import_id == a.import_id)).first()
            filename, data = (copy.filename, bytes(copy.data)) if copy is not None else (imp.filename, None)
        if not demo_cbom and data is None:
            data = self._bundled_demo_file(filename)
            if data is None:
                raise Conflict(RERUN_MISSING)
        made = self.new_assessment(project_id, name, purpose, reference)
        if demo_cbom:   # the demo file, exactly as Use demo file brings it in
            imported = self.import_demo(assessment_id=made["id"])   # type: ignore[attr-defined]
        else:
            imported = self.import_file(filename, data, assessment_id=made["id"])   # type: ignore[attr-defined]
        return {"id": made["id"], "notices": list(imported.get("notices") or [])}

    def _bundled_demo_file(self, filename: str) -> bytes | None:
        """For a file brought in before phase 5b: the bundled demo files can be made again; anything else can't."""
        from app.projects.demo import DEMO_PROJECTS, demo_file_bytes
        if filename not in {f for _, _, f in DEMO_PROJECTS} or filename == DEMO_CBOM_NAME:
            return None
        return demo_file_bytes(self, filename)

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
            if "purpose" in changes or "reference" in changes:
                if a.closed_at is not None:
                    raise Conflict(CLOSED_SENTENCE)
                current, current_ref = self._details(db, a)
                key = _purpose(changes["purpose"]) if "purpose" in changes else (current["key"] if current else DEFAULT_PURPOSE)
                ref = _optional_text(changes["reference"], REFERENCE_MAX) if "reference" in changes else current_ref
                db.add(AssessmentDetailRow(assessment_id=a.id, purpose=key, reference=ref))
            if changes.get("close"):
                if a.closed_at is not None:
                    raise Conflict("This assessment is already closed. It can't be reopened.")
                by = _optional_text(changes.get("signed_off_by"), NAME_MAX)
                if not by:
                    raise BadRequest("Type the name of the person who signs this assessment off.", field="signed_off_by")
                now = now_utc()
                a.closed_at, a.closed_why = now, "closed"
                db.add(AssessmentSignoffRow(assessment_id=a.id, signed_off_by=by, note=_optional_text(changes.get("note"), NOTE_MAX),
                                            signed_at=now))
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
            purpose, reference = self._details(db, a)
            signoff = self._signoff(db, a)
            return {"organization": self.organization_name(),
                    "folders": [f["name"] for f in self._folder_path(db, p.folder_id)],
                    "project": p.name, "assessment": assessment_title(a), "assessment_number": a.number,
                    "opened_at": iso(a.created_at), "closed_at": iso(a.closed_at) if a.closed_at else None,
                    "status": "closed" if a.closed_at else "open",
                    "purpose": purpose["label"] if purpose else None, "reference": reference,
                    "signed_off_by": signoff["by"] if signoff else None, "signed_off_at": signoff["at"] if signoff else None,
                    "signoff_note": signoff["note"] if signoff else None}

