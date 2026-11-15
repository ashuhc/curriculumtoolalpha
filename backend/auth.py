"""
Role-based authentication.

* Passwords: PBKDF2-SHA256 (stdlib, 200k iterations, per-user salt).
* Sessions: stateless HMAC-SHA256 signed tokens (JWT-like, 12h expiry), so the
  API can run several workers / containers behind a load balancer.
* Roles:  admin   — schedulers: overrides, locks, publishing, catalog/faculty/user management
          faculty — submit their own teaching preferences, comment on sections

Set AUTH_SECRET in production. Without it a random secret is generated once and
stored in backend/.auth_secret so local tokens survive `--reload` restarts.

This module is the single seam for an external IdP (e.g. Auth0): replace
`decode_token()` with JWKS verification of the IdP's access token and map its
role claim onto User.role — every endpoint depends only on `current_user`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import BACKEND_DIR, get_db
from models import User

ROLES = ("admin", "faculty")


def login_required() -> bool:
    """REQUIRE_LOGIN=true: every page and API read needs a signed-in user (recommended for public hosting)."""
    return os.environ.get("REQUIRE_LOGIN", "false").strip().lower() in ("1", "true", "yes")
TOKEN_TTL_SECONDS = 12 * 3600
_PBKDF2_ITERATIONS = 200_000


def _load_secret() -> bytes:
    env = os.environ.get("AUTH_SECRET")
    if env:
        return env.encode()
    path = os.path.join(BACKEND_DIR, ".auth_secret")
    try:
        with open(path) as f:
            return f.read().strip().encode()
    except OSError:
        s = secrets.token_hex(32)
        try:
            with open(path, "w") as f:
                f.write(s)
        except OSError:
            pass
        return s.encode()


SECRET = _load_secret()


# ---------------------------------------------------------------- passwords ---
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(check, digest)


# ------------------------------------------------------------------- tokens ---
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user: User) -> str:
    payload = _b64(json.dumps({"sub": user.id, "role": user.role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}).encode())
    sig = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def decode_token(token: str) -> Optional[dict]:
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        return data if data.get("exp", 0) > time.time() else None
    except (ValueError, json.JSONDecodeError):
        return None


def user_from_token(db: Session, token: Optional[str]) -> Optional[User]:
    data = decode_token(token) if token else None
    if not data:
        return None
    user = db.get(User, data["sub"])
    return user if user and user.active else None


# ------------------------------------------------------------- dependencies ---
def current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> Optional[User]:
    """The signed-in user, or None for anonymous requests."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return user_from_token(db, authorization.split(" ", 1)[1].strip())


def require_user(user: Optional[User] = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in required")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Scheduler (admin) role required")
    return user


def user_public(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "faculty_id": u.faculty_id,
            "faculty_name": u.faculty.name if u.faculty else None, "active": u.active}
