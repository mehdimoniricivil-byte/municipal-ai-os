from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.models import AuditLog
from app.db.session import get_db
from app.schemas.audit import AuditLogRead

router = APIRouter()


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    module: str | None = None,
    action: str | None = None,
    user_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_permissions("audit.view")),
):
    stmt = select(AuditLog)
    if module:
        stmt = stmt.where(AuditLog.module == module)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    return db.scalars(stmt.order_by(AuditLog.id.desc()).offset(offset).limit(limit)).all()
