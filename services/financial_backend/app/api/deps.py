from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ورود به سامانه الزامی است")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نشست کاربری معتبر نیست")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="کاربر غیرفعال یا نامعتبر است")
    return user


def require_roles(*roles: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="دسترسی کافی ندارید")
        return user
    return dependency


def require_permissions(*permissions: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not all(has_permission(user.role, permission) for permission in permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="دسترسی کافی ندارید")
        return user
    return dependency
