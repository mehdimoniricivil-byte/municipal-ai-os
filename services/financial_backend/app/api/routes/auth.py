from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, hash_password, token_digest, verify_password
from app.db.models import LoginAudit, RefreshToken, User
from app.db.session import get_db
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenResponse, UserOut

router = APIRouter()


def audit(db: Session, request: Request, username: str, success: bool, user_id: int | None = None, reason: str | None = None) -> None:
    db.add(LoginAudit(user_id=user_id, username=username, success=success,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:300], failure_reason=reason))


def issue_tokens(db: Session, user: User) -> TokenResponse:
    access, expires_in = create_access_token(user.id, user.role)
    refresh = create_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_digest(refresh),
        expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_days)))
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=expires_in, user=user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        audit(db, request, payload.username, False, user.id if user else None, "invalid_credentials")
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نام کاربری یا رمز عبور اشتباه است")
    user.last_login_at = datetime.utcnow()
    audit(db, request, user.username, True, user.id)
    result = issue_tokens(db, user)
    db.commit()
    return result


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_digest(payload.refresh_token)))
    if record is None or record.revoked_at is not None or record.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=401, detail="توکن تمدید معتبر نیست")
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="کاربر نامعتبر است")
    record.revoked_at = datetime.utcnow()
    result = issue_tokens(db, user)
    db.commit()
    return result


@router.post("/logout", status_code=204)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> None:
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_digest(payload.refresh_token)))
    if record and record.revoked_at is None:
        record.revoked_at = datetime.utcnow()
        db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password", status_code=204)
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="رمز عبور فعلی صحیح نیست")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    for token in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))):
        token.revoked_at = datetime.utcnow()
    db.commit()
