from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models import AuditLog, User


def _serialize(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def write_audit_log(
    db: Session,
    *,
    user: User | None,
    module: str,
    action: str,
    request: Request | None = None,
    record_type: str | None = None,
    record_id: int | str | None = None,
    old_value: Any = None,
    new_value: Any = None,
) -> AuditLog:
    row = AuditLog(
        user_id=user.id if user else None,
        module=module,
        action=action,
        record_type=record_type,
        record_id=str(record_id) if record_id is not None else None,
        old_value=_serialize(old_value),
        new_value=_serialize(new_value),
        ip_address=request.client.host if request and request.client else None,
        user_agent=(request.headers.get("user-agent", "")[:300] if request else None),
    )
    db.add(row)
    return row
