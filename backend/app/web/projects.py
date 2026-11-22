"""Phase 5a: the organization, folders, projects and assessments, Load demo projects, and the closed guard."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from app.projects.demo import load_demo_projects
from app.web import models
from app.web.common import shows


class NameBody(BaseModel):
    name: StrictStr = Field(max_length=200)


class FolderBody(BaseModel):
    name: StrictStr = Field(max_length=200)
    parent_id: StrictInt | None = None


class ProjectBody(BaseModel):
    name: StrictStr = Field(max_length=200)
    folder_id: StrictInt | None = None


class FolderChangeBody(BaseModel):
    """Rename, move or archive. Only the fields sent change (move to the top level with parent_id null)."""

    name: StrictStr | None = Field(default=None, max_length=200)
    parent_id: StrictInt | None = None
    move: StrictBool = False
    archived: StrictBool | None = None


class ProjectChangeBody(BaseModel):
    name: StrictStr | None = Field(default=None, max_length=200)
    folder_id: StrictInt | None = None
    move: StrictBool = False
    archived: StrictBool | None = None


class AssessmentChangeBody(BaseModel):
    name: StrictStr | None = Field(default=None, max_length=200)
    project_id: StrictInt | None = None
    archived: StrictBool | None = None
    close: StrictBool = False
    signed_off_by: StrictStr | None = Field(default=None, max_length=200)  # phase 5b: required to close
    note: StrictStr | None = Field(default=None, max_length=1000)
    purpose: StrictStr | None = Field(default=None, max_length=40)
    reference: StrictStr | None = Field(default=None, max_length=400)


class NewAssessmentBody(BaseModel):
    """Phase 5b: the New assessment box (and Rerun as new assessment). Every field may be left out."""

    name: StrictStr | None = Field(default=None, max_length=200)
    purpose: StrictStr | None = Field(default=None, max_length=40)
    reference: StrictStr | None = Field(default=None, max_length=400)


OPTIONAL_BODY = Body(None)  # the box's fields may all be left out, and so may the body


def _changes(body: BaseModel, move_field: str | None) -> dict:
    changes: dict = {}
    data = body.model_dump()
    if data.get("name") is not None:
        changes["name"] = data["name"]
    if move_field and data.get("move"):
        changes[move_field] = data.get(move_field)
    if data.get("archived") is not None:
        changes["archived"] = data["archived"]
    return changes


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()
    login = [Depends(require_login)]

    @router.get("/api/workspace", dependencies=login, responses=shows(models.Workspace))
    def workspace():
        return lab.workspace_view()

    @router.post("/api/organization", dependencies=login, responses=shows(models.Workspace))
    def organization(body: NameBody):
        lab.set_organization_name(body.name)
        return lab.workspace_view()

    @router.post("/api/folders", dependencies=login, responses=shows(models.Created))
    def create_folder(body: FolderBody):
        return lab.create_folder(body.name, body.parent_id)

    @router.post("/api/folders/{folder_id}", dependencies=login, responses=shows(models.Created))
    def change_folder(folder_id: int, body: FolderChangeBody):
        return lab.update_folder(folder_id, _changes(body, "parent_id"))

    @router.post("/api/projects", dependencies=login, responses=shows(models.Created))
    def create_project(body: ProjectBody):
        return lab.create_project(body.name, body.folder_id)

    @router.get("/api/projects/{project_id}", dependencies=login, responses=shows(models.ProjectView))
    def project(project_id: int):
        return lab.project_view(project_id)

    @router.get("/api/projects/{project_id}/overview", dependencies=login, responses=shows(models.ProjectOverview))
    def project_overview(project_id: int, from_id: int | None = None, to_id: int | None = None, archived: bool = False):
        return lab.project_overview(project_id, from_id, to_id, archived)

    @router.post("/api/projects/{project_id}", dependencies=login, responses=shows(models.Created))
    def change_project(project_id: int, body: ProjectChangeBody):
        return lab.update_project(project_id, _changes(body, "folder_id"))

    @router.post("/api/projects/{project_id}/assessments", dependencies=login, responses=shows(models.Created))
    def new_assessment(project_id: int, body: NewAssessmentBody = OPTIONAL_BODY):
        b = body or NewAssessmentBody()
        return lab.new_assessment(project_id, b.name, b.purpose, b.reference)

    @router.post("/api/assessments/{assessment_id}/rerun", dependencies=login, responses=shows(models.Created))
    def rerun_assessment(assessment_id: int, body: NewAssessmentBody = OPTIONAL_BODY):
        b = body or NewAssessmentBody()
        return lab.rerun_assessment(assessment_id, b.name, b.purpose, b.reference)

    @router.get("/api/assessments/{assessment_id}", dependencies=login, responses=shows(models.AssessmentView))
    def assessment(assessment_id: int):
        return lab.assessment_view(assessment_id)

    @router.post("/api/assessments/{assessment_id}", dependencies=login, responses=shows(models.AssessmentView))
    def change_assessment(assessment_id: int, body: AssessmentChangeBody):
        changes = _changes(body, None)
        if body.project_id is not None:
            changes["project_id"] = body.project_id
        if body.close:
            changes.update(close=True, signed_off_by=body.signed_off_by, note=body.note)
        if body.purpose is not None:
            changes["purpose"] = body.purpose
        if body.reference is not None:
            changes["reference"] = body.reference
        lab.update_assessment(assessment_id, changes)
        return lab.assessment_view(assessment_id)

    @router.post("/api/demo-projects", dependencies=login, responses=shows(models.DemoProjectsLoaded))
    def demo_projects():
        return load_demo_projects(lab)

    return router


# Changing requests that stay allowed on a closed assessment: they change nothing in it.
ALLOWED_WHEN_CLOSED = (
    ("/api/plans/", "/evidence"),  # Download evidence builds and signs the file
    ("/api/import/", "/plan"),  # opening Tests makes the suggested list; it decides nothing
)


def closed_guard(lab, require_login):
    """A dependency for the step routers: a changing request on an import, plan or run of a closed assessment is
    refused with one plain sentence. The login check comes first, so a stranger still gets "Please log in"."""

    def guard(request: Request, _login: None = Depends(require_login)) -> None:
        if request.method != "POST":
            return
        path = request.url.path
        if any(path.startswith(a) and path.endswith(b) for a, b in ALLOWED_WHEN_CLOSED):
            return
        params = request.path_params

        def number(key: str) -> int | None:
            value = params.get(key)
            return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None

        lab.refuse_if_closed(import_id=number("import_id"), plan_id=number("plan_id"), run_id=number("run_id"))

    return guard
