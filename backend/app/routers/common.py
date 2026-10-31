from __future__ import annotations
from datetime import datetime
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..auth import current_user, require_project_role
from ..models import User


def row(obj) -> dict:
    if obj is None:
        return None
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        out[c.name] = v
    out.pop("password_hash", None)
    out.pop("token_hash", None)
    return out


def rows(objs) -> list[dict]:
    return [row(o) for o in objs]


class ProjectCtx:
    def __init__(self, minimum: str):
        self.minimum = minimum

    def __call__(self, project_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        project = require_project_role(db, user, project_id, self.minimum)
        return project, db, user


viewer = ProjectCtx("viewer")
reviewer = ProjectCtx("reviewer")
editor = ProjectCtx("editor")
owner = ProjectCtx("owner")


def get_or_404(db, model, id_, project_id=None):
    obj = db.get(model, id_)
    if not obj or (project_id and getattr(obj, "project_id", project_id) != project_id):
        raise HTTPException(404, f"{model.__name__} not found")
    return obj
