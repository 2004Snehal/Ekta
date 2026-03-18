"""
Authentication routes: register, login, /me, and admin user management.

Roles:    user  (default for all new sign-ups)
          admin (granted manually via admin panel or auto-assigned to first user)

Profiles: team_member (default), founder, editor, manager, analyst
"""

from datetime import datetime, timedelta
from typing import Optional
import os

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from api.deps import get_conn

router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Config ────────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "frammer-analytics-change-this-secret-in-production-32ch",
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

USER_PROFILES = ["team_member", "founder", "editor", "manager", "analyst"]

# ── Schemas ───────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserUpdate(BaseModel):
    role: Optional[str] = None
    profile: Optional[str] = None
    name: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _row_to_user(row) -> dict:
    return {
        "id": str(row[0]),
        "email": row[1],
        "name": row[2],
        "role": row[3],
        "profile": row[4],
    }


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise ValueError("no sub")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, name, role, profile FROM internal.users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()

    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return _row_to_user(row)


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/register")
def register(req: RegisterRequest):
    if len(req.password) < 6:
        raise HTTPException(
            status_code=400, detail="Password must be at least 6 characters"
        )

    with get_conn() as conn:
        cur = conn.cursor()

        # Check duplicate
        cur.execute(
            "SELECT id FROM internal.users WHERE email = %s", (req.email.lower(),)
        )
        if cur.fetchone():
            cur.close()
            raise HTTPException(status_code=400, detail="Email already registered")

        # First user ever → admin; everyone else → user
        cur.execute("SELECT COUNT(*) FROM internal.users")
        count = cur.fetchone()[0]
        role = "admin" if count == 0 else "user"

        cur.execute(
            """
            INSERT INTO internal.users (email, name, password_hash, role, profile)
            VALUES (%s, %s, %s, %s, 'team_member')
            RETURNING id, email, name, role, profile
            """,
            (req.email.lower(), req.name, _hash_password(req.password), role),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()

    user = _row_to_user(row)
    return {
        "access_token": _create_token(user["id"]),
        "token_type": "bearer",
        "user": user,
    }


@router.post("/login")
def login(req: LoginRequest):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, email, name, role, profile, password_hash
            FROM internal.users WHERE email = %s
            """,
            (req.email.lower(),),
        )
        row = cur.fetchone()
        cur.close()

    if not row or not _verify_password(req.password, row[5]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = _row_to_user(row)
    return {
        "access_token": _create_token(user["id"]),
        "token_type": "bearer",
        "user": user,
    }


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user


# ── Admin: list & update users ────────────────────────────────────────────────


@router.get("/users")
def list_users(_admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, email, name, role, profile, created_at
            FROM internal.users
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()
        cur.close()

    return [
        {
            "id": str(r[0]),
            "email": r[1],
            "name": r[2],
            "role": r[3],
            "profile": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


@router.put("/users/{user_id}")
def update_user(
    user_id: str, update: UserUpdate, _admin: dict = Depends(require_admin)
):
    fields, values = [], []

    if update.role is not None:
        if update.role not in ("user", "admin"):
            raise HTTPException(
                status_code=400, detail="Role must be 'user' or 'admin'"
            )
        fields.append("role = %s")
        values.append(update.role)

    if update.profile is not None:
        if update.profile not in USER_PROFILES:
            raise HTTPException(
                status_code=400,
                detail=f"Profile must be one of: {', '.join(USER_PROFILES)}",
            )
        fields.append("profile = %s")
        values.append(update.profile)

    if update.name is not None:
        fields.append("name = %s")
        values.append(update.name)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(user_id)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE internal.users
            SET {', '.join(fields)}
            WHERE id = %s
            RETURNING id, email, name, role, profile
            """,
            values,
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _row_to_user(row)
