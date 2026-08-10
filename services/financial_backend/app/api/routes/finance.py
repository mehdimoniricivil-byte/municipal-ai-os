from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import require_roles
from app.services.finance import monthly_profit_loss
from app.core.config import settings


router = APIRouter()


@router.get("/settings")
def financial_settings(
    _user = Depends(
        require_roles(
            "brokerage_head",
            "executive_manager",
            "finance_manager",
            "tri_manager",
        )
    ),
):
    return {
        "dashboard_wage_rate_percent": settings.dashboard_wage_rate_percent,
    }


@router.get("/profit-loss")
def profit_loss(year: int, month: int, db: Session = Depends(get_db), _user = Depends(require_roles("brokerage_head", "executive_manager", "finance_manager", "tri_manager"))):
    return monthly_profit_loss(db, year, month)
