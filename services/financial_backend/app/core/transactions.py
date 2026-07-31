from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")


def commit_or_rollback(db: Session, operation: Callable[[], T]) -> T:
    """Run a write operation atomically and rollback on every exception."""
    try:
        result = operation()
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
