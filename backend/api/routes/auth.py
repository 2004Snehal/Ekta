"""
Auth routes — signup and login.

POST /auth/signup  — register a new user (role='user', profile='basic')
POST /auth/login   — email+password login, returns JWT access token
GET  /auth/me      — return current user info from JWT
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from api.deps import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Crypto config ─────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("JWT_SECRET", "frammer-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def _hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def _create_token(user_id: str, email: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── Shared dependency: decode token ──────────────────────────────────────────

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """
    Decode JWT and return user dict.
    Raises 401 if token is missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "user_id": payload["sub"],
            "email": payload["email"],
            "role": payload["role"],
        }
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Raises 403 if the current user is not an admin."""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


# ── Request / Response models ─────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/signup", status_code=201)
def signup(body: SignupRequest):
    """
    Register a new user. All new users get role='user' and profile='basic'.
    Returns a JWT so the user is immediately logged in after signup.
    """
    email = body.email.strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    password_hash = _hash_password(body.password)

    with get_conn() as conn:
        cur = conn.cursor()

        # Check duplicate email
        cur.execute(
            "SELECT id FROM internal.users WHERE email = %s",
            (email,),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Email already registered.")

        cur.execute(
            """
            INSERT INTO internal.users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id, role, profile
            """,
            (email, password_hash),
        )
        row = cur.fetchone()
        conn.commit()

    user_id, role, user_profile = str(row[0]), row[1], row[2]
    token = _create_token(user_id, email, role)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user_id,
            "email": email,
            "role": role,
            "user_profile": user_profile,
        },
    }


@router.post("/login")
def login(body: LoginRequest):
    """Email + password login. Returns a JWT access token."""
    email = body.email.strip().lower()

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, password_hash, role, profile FROM internal.users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()

    if not row or not _verify_password(body.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user_id, _, role, user_profile = str(row[0]), row[1], row[2], row[3]
    token = _create_token(user_id, email, role)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user_id,
            "email": email,
            "role": role,
            "user_profile": user_profile,
        },
    }


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return the current user's info decoded from the JWT."""
    # Fetch fresh profile from DB
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT profile, role FROM internal.users WHERE id = %s",
            (current_user["user_id"],),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found.")

    return {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "role": row[1],
        "user_profile": row[0],
    }
