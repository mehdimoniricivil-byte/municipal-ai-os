from decimal import Decimal

from pydantic import BaseModel


class DashboardKpi(BaseModel):
    total_collection_irr: Decimal
    total_target_irr: Decimal
    collection_variance_irr: Decimal
    achievement_percent: Decimal | None
    wage_income_irr: Decimal
    total_expenses_irr: Decimal
    profit_or_loss_irr: Decimal
    profit_margin_percent: Decimal | None


class DashboardRegionRow(BaseModel):
    region_id: int
    region_code: str
    region_title: str
    collection_irr: Decimal
    target_irr: Decimal
    variance_irr: Decimal
    achievement_percent: Decimal | None
    wage_rate_percent: Decimal | None
    wage_amount_irr: Decimal
    allocated_expense_irr: Decimal
    profit_or_loss_irr: Decimal
    as_of_persian_date: str | None
    data_status: str


class DashboardSummary(BaseModel):
    persian_year: int
    persian_month: int
    kpi: DashboardKpi
    regions: list[DashboardRegionRow]
    generated_from: str = "database"
