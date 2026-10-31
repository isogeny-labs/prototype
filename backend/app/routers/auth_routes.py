from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..auth import verify_password, create_session, revoke_session, current_user, hash_password
from ..models import User
from .. import audit
from .common import row, rows

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        audit.record(db, None, "auth.login_failed", "user", None, None, {"email": body.email}, commit=True)
        raise HTTPException(401, "invalid credentials")
    token = create_session(db, user)
    audit.record(db, user.id, "auth.login", "user", user.id, None, {}, commit=True)
    return {"token": token, "user": row(user)}


@router.post("/logout")
def logout(authorization: str = Header(default=""), db: Session = Depends(get_db), user: User = Depends(current_user)):
    revoke_session(db, authorization.split(" ", 1)[1])
    audit.record(db, user.id, "auth.logout", "user", user.id, None, {}, commit=True)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return row(user)


class UserIn(BaseModel):
    email: str
    name: str
    password: str
    is_admin: bool = False


@router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return rows(db.scalars(select(User)).all())


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, "admin only")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "email exists")
    u = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), is_admin=body.is_admin)
    db.add(u)
    db.flush()
    audit.record(db, user.id, "user.created", "user", u.id, None, {"email": u.email}, commit=True)
    return row(u)
