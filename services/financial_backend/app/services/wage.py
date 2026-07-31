from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session

from app.db.models import WageBracket, WageCalculation, WageRuleSet
from app.schemas.wage import WageCalculateRequest


def _select_bracket(growth_percent: Decimal, brackets: list[WageBracket]) -> WageBracket:
    for bracket in sorted(brackets, key=lambda x: x.priority):
        min_ok = bracket.min_growth_percent is None or growth_percent >= bracket.min_growth_percent
        max_ok = bracket.max_growth_percent is None or growth_percent <= bracket.max_growth_percent
        if min_ok and max_ok:
            return bracket
    raise ValueError("برای این درصد رشد، پله دستمزد تعریف نشده است.")


def calculate_wage(db: Session, payload: WageCalculateRequest) -> WageCalculation:
    rule_set = db.get(WageRuleSet, payload.rule_set_id)
    if not rule_set:
        raise ValueError("دستورالعمل دستمزد پیدا نشد.")

    growth = (
        (payload.actual_collection_irr / payload.matched_collection_irr) - Decimal("1")
    ) * Decimal("100")

    bracket = _select_bracket(growth, rule_set.brackets)
    wage_amount = (
        payload.actual_collection_irr
        * bracket.wage_rate_percent
        / Decimal("100")
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    trace = (
        f"growth=(({payload.actual_collection_irr}/{payload.matched_collection_irr})-1)*100"
        f"; rate={bracket.wage_rate_percent}%"
        f"; wage={payload.actual_collection_irr}*{bracket.wage_rate_percent}/100"
    )

    result = WageCalculation(
        region_id=payload.region_id,
        rule_set_id=payload.rule_set_id,
        persian_year=payload.persian_year,
        persian_month=payload.persian_month,
        actual_collection_irr=payload.actual_collection_irr,
        matched_collection_irr=payload.matched_collection_irr,
        growth_percent=growth,
        wage_rate_percent=bracket.wage_rate_percent,
        wage_amount_irr=wage_amount,
        calculation_trace=trace,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result
