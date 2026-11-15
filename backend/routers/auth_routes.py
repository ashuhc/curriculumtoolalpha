"""Sign-in and user management."""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import create_token, hash_password, require_admin, require_user, user_public, verify_password
from database import get_db
from models import Faculty, User
from schemas import LoginIn, PasswordChange, UserIn, UserUpdate

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    user.last_login = datetime.utcnow()
    db.commit()
    return {"token": create_token(user), "user": user_public(user)}


@router.get("/auth/me")
def me(user: User = Depends(require_user)):
    return user_public(user)


@router.post("/auth/password")
def change_password(body: PasswordChange, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ user admin ---
@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> List[dict]:
    return [{**user_public(u), "last_login": u.last_login, "created_at": u.created_at}
            for u in db.query(User).order_by(User.role, User.name).all()]


def _check_faculty(db: Session, faculty_id):
    if faculty_id is not None and not db.get(Faculty, faculty_id):
        raise HTTPException(404, "Linked faculty member not found")


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, "A user with that email already exists")
    _check_faculty(db, body.faculty_id)
    u = User(email=body.email, name=body.name.strip(), role=body.role,
             password_hash=hash_password(body.password), faculty_id=body.faculty_id)
    db.add(u)
    db.commit()
    return user_public(u)


@router.put("/users/{uid}")
def update_user(uid: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and (body.role == "faculty" or body.active is False):
        raise HTTPException(400, "You cannot demote or deactivate your own account")
    if body.name is not None:
        u.name = body.name.strip()
    if body.role is not None:
        u.role = body.role
    if body.password:
        u.password_hash = hash_password(body.password)
    if body.unlink_faculty:
        u.faculty_id = None
    elif body.faculty_id is not None:
        _check_faculty(db, body.faculty_id)
        u.faculty_id = body.faculty_id
    if body.active is not None:
        u.active = body.active
    db.commit()
    return user_public(u)


@router.delete("/users/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot delete your own account")
    db.delete(u)
    db.commit()
