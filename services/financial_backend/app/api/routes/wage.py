from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import WageBracket, WageRuleSet
from app.db.session import get_db
from app.schemas.wage import WageCalculateRequest, WageRuleSetCreate
from app.services.wage import calculate_wage


router = APIRouter()


@router.post("/rule-sets")
def create_rule_set(payload: WageRuleSetCreate, db: Session = Depends(get_db)):
    rule_set = WageRuleSet(
        title=payload.title,
        version=payload.version,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        calculation_basis=payload.calculation_basis,
        status=payload.status,
        notes=payload.notes,
    )
    for item in payload.brackets:
        rule_set.brackets.append(WageBracket(**item.model_dump()))

    db.add(rule_set)
    db.commit()
    db.refresh(rule_set)
    return rule_set


@router.post("/calculate")
def calculate(payload: WageCalculateRequest, db: Session = Depends(get_db)):
    try:
        return calculate_wage(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
