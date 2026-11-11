"""The single local login: a password the owner creates on first start.

Only a scrypt hash and a random salt are stored. The password is never logged, printed or returned.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from .db import AuthRow, SessionRow, now_utc

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024
SESSION_LIFETIME = timedelta(hours=12)
COOKIE_NAME = "evidence_lab_session"


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1, dklen=32, maxmem=2 ** 27)


def setup_required(db: Session) -> bool:
    return db.get(AuthRow, 1) is None


def create_password(db: Session, password: str) -> None:
    salt = secrets.token_bytes(16)
    db.add(AuthRow(id=1, salt=salt, password_hash=_hash(password, salt)))
    db.commit()


def password_matches(db: Session, password: str) -> bool:
    row = db.get(AuthRow, 1)
    if row is None or not isinstance(password, str) or len(password) > MAX_PASSWORD_LENGTH:
        return False
    return hmac.compare_digest(_hash(password, row.salt), row.password_hash)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session(db: Session) -> str:
    """Create a login session and return its random token (goes only into the HttpOnly cookie)."""
    token = secrets.token_urlsafe(32)
    cutoff = now_utc() - SESSION_LIFETIME
    for old in db.query(SessionRow).all():
        created = old.created_at if old.created_at.tzinfo else old.created_at.replace(tzinfo=cutoff.tzinfo)
        if created < cutoff:
            db.delete(old)
    db.add(SessionRow(token_hash=_token_hash(token)))
    db.commit()
    return token


def session_valid(db: Session, token: str | None) -> bool:
    if not token or len(token) > 200:
        return False
    wanted = _token_hash(token)
    cutoff = now_utc() - SESSION_LIFETIME
    ok = False
    for row in db.query(SessionRow).all():  # compare every stored hash in constant time
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=cutoff.tzinfo)
        if hmac.compare_digest(row.token_hash, wanted) and created >= cutoff:
            ok = True
    return ok
