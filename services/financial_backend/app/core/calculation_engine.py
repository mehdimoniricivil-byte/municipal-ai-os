"""Pure financial calculations used across routes and services.

All amounts are kept as :class:`Decimal` and rounded to whole IRR using
ROUND_HALF_UP. Keeping this module free of database and HTTP dependencies makes
its rules independently testable and auditable.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0")
ONE_IRR = Decimal("1")


def as_decimal(value: Decimal | int | str | float | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_irr(value: Decimal | int | str | float) -> Decimal:
    return as_decimal(value).quantize(ONE_IRR, rounding=ROUND_HALF_UP)


def ensure_non_negative(value: Decimal, field_name: str) -> Decimal:
    if value < ZERO:
        raise ValueError(f"{field_name} نمی‌تواند منفی باشد")
    return value


def calculate_wage(collection_amount_irr: Decimal | int | str, wage_rate_percent: Decimal | int | str) -> Decimal:
    collection = ensure_non_negative(as_decimal(collection_amount_irr), "مبلغ وصول")
    rate = ensure_non_negative(as_decimal(wage_rate_percent), "نرخ دستمزد")
    return round_irr(collection * rate / Decimal("100"))


def calculate_balance(total_amount_irr: Decimal | int | str, paid_amount_irr: Decimal | int | str) -> Decimal:
    total = ensure_non_negative(as_decimal(total_amount_irr), "مبلغ کل")
    paid = ensure_non_negative(as_decimal(paid_amount_irr), "مبلغ پرداخت‌شده")
    if paid > total:
        raise ValueError("مبلغ پرداخت‌شده از مبلغ کل بیشتر است")
    return round_irr(total - paid)


@dataclass(frozen=True, slots=True)
class StatementCalculation:
    collection_amount_irr: Decimal
    wage_rate_percent: Decimal
    gross_amount_irr: Decimal
    deductions_irr: Decimal
    net_amount_irr: Decimal


def calculate_statement(
    *,
    collection_amount_irr: Decimal | int | str,
    wage_rate_percent: Decimal | int | str,
    deductions_irr: Decimal | int | str = ZERO,
    gross_amount_irr: Decimal | int | str | None = None,
) -> StatementCalculation:
    collection = ensure_non_negative(as_decimal(collection_amount_irr), "مبلغ وصول")
    rate = ensure_non_negative(as_decimal(wage_rate_percent), "نرخ دستمزد")
    deductions = ensure_non_negative(as_decimal(deductions_irr), "کسورات")
    gross = calculate_wage(collection, rate) if gross_amount_irr is None else round_irr(
        ensure_non_negative(as_decimal(gross_amount_irr), "مبلغ ناخالص")
    )
    net = max(ZERO, round_irr(gross - deductions))
    return StatementCalculation(
        collection_amount_irr=round_irr(collection),
        wage_rate_percent=rate,
        gross_amount_irr=gross,
        deductions_irr=round_irr(deductions),
        net_amount_irr=net,
    )
