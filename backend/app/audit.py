from __future__ import annotations
from sqlalchemy.orm import Session
from .models import AuditEvent

SENSITIVE_KEYS = {"password", "token", "authorization", "secret", "api_key", "private_key"}


def scrub(d):
    if isinstance(d, dict):
        return {k: ("[REDACTED]" if k.lower() in SENSITIVE_KEYS else scrub(v)) for k, v in d.items()}
    if isinstance(d, list):
        return [scrub(x) for x in d]
    return d


def record(db: Session, actor_id: str | None, action: str, subject_type: str, subject_id: str | None,
           project_id: str | None = None, detail: dict | None = None, commit: bool = False):
    ev = AuditEvent(actor_id=actor_id, project_id=project_id, action=action, subject_type=subject_type,
                    subject_id=subject_id, detail=scrub(detail or {}))
    db.add(ev)
    if commit:
        db.commit()
    return ev
