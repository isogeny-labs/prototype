"""Basic authentication and project access control.

* Passwords: PBKDF2-HMAC-SHA256 (stdlib), 390k iterations, per-user salt.
* Sessions: random 256-bit bearer tokens; only the SHA-256 of the token is stored.
* Roles per project: owner > editor > reviewer > viewer. Admins bypass membership.
Secrets never appear in logs (see logging filter in main.py).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SESSION_TTL_HOURS
from .db import get_db
from .models import User, SessionToken, ProjectMember, Project, utcnow

ROLE_RANK = {"viewer": 1, "reviewer": 2, "editor": 3, "owner": 4}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 390_000)
    return f"pbkdf2_sha256$390000${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessionToken(token_hash=_token_hash(token), user_id=user.id,
                        expires_at=utcnow() + timedelta(hours=SESSION_TTL_HOURS)))
    db.commit()
    return token


def revoke_session(db: Session, token: str):
    st = db.scalar(select(SessionToken).where(SessionToken.token_hash == _token_hash(token)))
    if st:
        db.delete(st)
        db.commit()


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    st = db.scalar(select(SessionToken).where(SessionToken.token_hash == _token_hash(token)))
    if not st:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid session")
    exp = st.expires_at
    if exp.tzinfo is None:
        from datetime import timezone
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < utcnow():
        db.delete(st)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    user = db.get(User, st.user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    return user


def role_in_project(db: Session, user: User, project_id: str) -> str | None:
    if user.is_admin:
        return "owner"
    m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                              ProjectMember.user_id == user.id))
    return m.role if m else None


def require_project_role(db: Session, user: User, project_id: str, minimum: str = "viewer") -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    role = role_in_project(db, user, project_id)
    if role is None or ROLE_RANK[role] < ROLE_RANK[minimum]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires project role >= {minimum}")
    return project


def accessible_project_ids(db: Session, user: User) -> list[str]:
    if user.is_admin:
        return [p.id for p in db.scalars(select(Project)).all()]
    return [m.project_id for m in db.scalars(select(ProjectMember).where(ProjectMember.user_id == user.id)).all()]


def redact(value: str) -> str:
    """Redact anything that looks like a secret for logs."""
    if not value:
        return value
    return value[:4] + "…" + "*" * 6
