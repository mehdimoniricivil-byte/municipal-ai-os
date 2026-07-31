from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MonthlyCollection
from app.db.session import get_db
from app.api.deps import require_roles


router = APIRouter()


@router.get("")
def list_monthly_collections(
    year: int = Query(ge=1300, le=1600),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    _user = Depends(require_roles("brokerage_head", "executive_manager", "finance_manager", "tri_manager")),
):
    return db.scalars(
        select(MonthlyCollection)
        .where(
            MonthlyCollection.persian_year == year,
            MonthlyCollection.persian_month == month,
        )
        .order_by(MonthlyCollection.region_id)
    ).all()
