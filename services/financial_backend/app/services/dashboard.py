from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Expense, MonthlyCollection, MonthlyTarget, Region, WageCalculation


ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _decimal(value: object | None) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(value)


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= 0:
        return None
    return (numerator / denominator * HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def dashboard_summary(db: Session, year: int, month: int) -> dict:
    regions = db.scalars(
        select(Region).where(Region.is_active.is_(True)).order_by(Region.sort_order, Region.id)
    ).all()

    collections = {
        row.region_id: row
        for row in db.scalars(
            select(MonthlyCollection).where(
                MonthlyCollection.persian_year == year,
                MonthlyCollection.persian_month == month,
            )
        ).all()
    }
    targets = {
        row.region_id: row
        for row in db.scalars(
            select(MonthlyTarget).where(
                MonthlyTarget.persian_year == year,
                MonthlyTarget.persian_month == month,
            )
        ).all()
    }
    wages = {
        row.region_id: row
        for row in db.scalars(
            select(WageCalculation).where(
                WageCalculation.persian_year == year,
                WageCalculation.persian_month == month,
            )
        ).all()
    }

    direct_expenses = {
        region_id: _decimal(amount)
        for region_id, amount in db.execute(
            select(Expense.region_id, func.coalesce(func.sum(Expense.amount_irr), 0))
            .where(
                Expense.persian_year == year,
                Expense.persian_month == month,
                Expense.expense_type == "direct",
                Expense.region_id.is_not(None),
            )
            .group_by(Expense.region_id)
        ).all()
    }
    shared_expense = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Expense.amount_irr), 0)).where(
                Expense.persian_year == year,
                Expense.persian_month == month,
                Expense.expense_type == "shared",
            )
        )
    )

    total_collection = sum((_decimal(row.amount_irr) for row in collections.values()), ZERO)
    rows: list[dict] = []

    for region in regions:
        collection_row = collections.get(region.id)
        target_row = targets.get(region.id)
        wage_row = wages.get(region.id)

        collection = _decimal(collection_row.amount_irr if collection_row else None)
        target = _decimal(target_row.target_amount_irr if target_row else None)
        wage_amount = _decimal(wage_row.wage_amount_irr if wage_row else None)
        direct = direct_expenses.get(region.id, ZERO)
        shared_allocated = (
            (shared_expense * collection / total_collection).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if total_collection > 0
            else ZERO
        )
        allocated_expense = direct + shared_allocated
        profit = wage_amount - allocated_expense

        rows.append(
            {
                "region_id": region.id,
                "region_code": region.code,
                "region_title": region.title,
                "collection_irr": collection,
                "target_irr": target,
                "variance_irr": collection - target,
                "achievement_percent": _percent(collection, target),
                "wage_rate_percent": _decimal(wage_row.wage_rate_percent) if wage_row else None,
                "wage_amount_irr": wage_amount,
                "allocated_expense_irr": allocated_expense,
                "profit_or_loss_irr": profit,
                "as_of_persian_date": collection_row.as_of_persian_date if collection_row else None,
                "data_status": "available" if collection_row else "missing",
            }
        )

    total_target = sum((row["target_irr"] for row in rows), ZERO)
    total_wage = sum((row["wage_amount_irr"] for row in rows), ZERO)
    total_expense = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Expense.amount_irr), 0)).where(
                Expense.persian_year == year,
                Expense.persian_month == month,
            )
        )
    )
    total_profit = total_wage - total_expense

    return {
        "persian_year": year,
        "persian_month": month,
        "kpi": {
            "total_collection_irr": total_collection,
            "total_target_irr": total_target,
            "collection_variance_irr": total_collection - total_target,
            "achievement_percent": _percent(total_collection, total_target),
            "wage_income_irr": total_wage,
            "total_expenses_irr": total_expense,
            "profit_or_loss_irr": total_profit,
            "profit_margin_percent": _percent(total_profit, total_wage),
        },
        "regions": rows,
        "generated_from": "database",
    }
