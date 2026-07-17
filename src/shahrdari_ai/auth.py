from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy import and_, insert, select, text
from sqlalchemy.engine import Engine

from .etl.engine import make_engine
from .etl.models import users


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    REGION_MANAGER = "REGION_MANAGER"
    DISTRICT_MANAGER = "DISTRICT_MANAGER"
    ACCOUNTANT = "ACCOUNTANT"
    FIELD_AGENT = "FIELD_AGENT"


class UserCreate(BaseModel):
    name: str = Field(min_length=1)
    username: str = Field(min_length=3)
    password: str = Field(min_length=8)
    role: UserRole
    region: str | None = None
    district: str | None = None
    is_active: bool = True


class UserLogin(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    id: int
    name: str
    username: str
    role: UserRole
    region: str | None
    district: str | None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390_000)
    return "pbkdf2_sha256$390000$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_secret() -> bytes:
    return os.environ.get("AUTH_SECRET_KEY", "municipal-ai-os-dev-secret-change-me").encode("utf-8")


def _b64_json(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_b64_json(value: str) -> dict[str, Any]:
    padding = "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode((value + padding).encode("ascii")))


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
    payload = _b64_json({"sub": user_id, "exp": int(expires_at.timestamp())})
    signature = base64.urlsafe_b64encode(hmac.new(_token_secret(), payload.encode("ascii"), hashlib.sha256).digest()).decode("ascii").rstrip("=")
    return f"{payload}.{signature}"


def _user_to_read(row: dict[str, Any]) -> UserRead:
    return UserRead(**{key: row[key] for key in UserRead.model_fields})


def _get_user_by_username(engine: Engine, username: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(select(users).where(users.c.username == username)).mappings().first()
        return dict(row) if row else None


def _get_user_by_id(engine: Engine, user_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(select(users).where(users.c.id == user_id)).mappings().first()
        return dict(row) if row else None


def create_user_record(payload: UserCreate, engine: Engine | None = None) -> UserRead:
    engine = engine or make_engine()
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        existing = conn.execute(select(users.c.id).where(users.c.username == payload.username)).first()
        if existing:
            raise HTTPException(status_code=409, detail="نام کاربری قبلاً ثبت شده است")
        result = conn.execute(
            insert(users).values(
                name=payload.name,
                username=payload.username,
                password_hash=hash_password(payload.password),
                role=payload.role.value,
                region=payload.region,
                district=payload.district,
                is_active=payload.is_active,
                created_at=now,
            )
        )
        user_id = result.inserted_primary_key[0]
        row = conn.execute(select(users).where(users.c.id == user_id)).mappings().one()
        return _user_to_read(dict(row))


def authenticate_user(payload: UserLogin, engine: Engine | None = None) -> TokenResponse:
    engine = engine or make_engine()
    row = _get_user_by_username(engine, payload.username)
    if not row or not row["is_active"] or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نام کاربری یا رمز عبور نادرست است")
    user = _user_to_read(row)
    return TokenResponse(access_token=create_access_token(user.id), user=user)


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserRead:
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="توکن نامعتبر است", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload, signature = token.split(".", 1)
        expected = base64.urlsafe_b64encode(hmac.new(_token_secret(), payload.encode("ascii"), hashlib.sha256).digest()).decode("ascii").rstrip("=")
        if not hmac.compare_digest(signature, expected):
            raise credentials_error
        data = _decode_b64_json(payload)
        if int(data["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            raise credentials_error
        row = _get_user_by_id(make_engine(), int(data["sub"]))
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise credentials_error from exc
    if not row or not row["is_active"]:
        raise credentials_error
    return _user_to_read(row)


def require_financial_access(current_user: Annotated[UserRead, Depends(get_current_user)]) -> UserRead:
    if current_user.role not in {UserRole.ADMIN, UserRole.ACCOUNTANT}:
        raise HTTPException(status_code=403, detail="دسترسی مالی مجاز نیست")
    return current_user


def scoped_region_filter(current_user: UserRead, region_column, district_column=None):
    if current_user.role == UserRole.ADMIN:
        return text("1=1")
    if current_user.role == UserRole.REGION_MANAGER:
        return region_column == current_user.region
    if current_user.role == UserRole.DISTRICT_MANAGER:
        clauses = [region_column == current_user.region] if current_user.region else []
        if district_column is not None:
            clauses.append(district_column == current_user.district)
        return and_(*clauses) if clauses else text("1=0")
    return text("1=0")
