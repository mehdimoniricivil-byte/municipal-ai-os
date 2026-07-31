from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Expense, MonthlyCollection, WageCalculation


def monthly_profit_loss(db: Session, year: int, month: int) -> dict:
    collection = db.scalar(
        select(func.coalesce(func.sum(MonthlyCollection.amount_irr), 0)).where(
            MonthlyCollection.persian_year == year,
            MonthlyCollection.persian_month == month,
        )
    ) or Decimal("0")

    wage_income = db.scalar(
        select(func.coalesce(func.sum(WageCalculation.wage_amount_irr), 0)).where(
            WageCalculation.persian_year == year,
            WageCalculation.persian_month == month,
        )
    ) or Decimal("0")

    expenses = db.scalar(
        select(func.coalesce(func.sum(Expense.amount_irr), 0)).where(
            Expense.persian_year == year,
            Expense.persian_month == month,
        )
    ) or Decimal("0")

    profit = wage_income - expenses
    margin = (profit / wage_income * Decimal("100")) if wage_income > 0 else None

    return {
        "persian_year": year,
        "persian_month": month,
        "collection_irr": collection,
        "wage_income_irr": wage_income,
        "expenses_irr": expenses,
        "profit_or_loss_irr": profit,
        "profit_margin_percent": margin,
    }
