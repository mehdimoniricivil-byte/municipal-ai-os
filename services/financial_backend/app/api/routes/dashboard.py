from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import require_roles
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import dashboard_summary


router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    year: int = Query(ge=1300, le=1600),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    _user = Depends(require_roles("brokerage_head", "executive_manager", "finance_manager", "tri_manager")),
):
    return dashboard_summary(db, year, month)
