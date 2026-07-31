from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.calculation_engine import calculate_balance, calculate_statement
from app.db.models import (
    Contract, MonthlyCollection, Statement, StatementPayment, StatementVersion,
    StatementWorkflow, User, WageCalculation,
)

WORKFLOW_STAGES = (
    (1, "supervisor", "سرپرست", "executive_manager"),
    (2, "finance_supervisor", "سرپرست مالی", "finance_manager"),
    (3, "regional_mayor", "شهردار منطقه", "tri_manager"),
    (4, "revenue_director", "مدیر درآمدهای عمومی", "tri_manager"),
    (5, "strategic_committee", "کمیته راهبردی", "tri_manager"),
    (6, "finance", "امور مالی", "finance_manager"),
)


def statement_query():
    return select(Statement).options(
        selectinload(Statement.workflow_items), selectinload(Statement.payments)
    )


def snapshot(statement: Statement) -> dict:
    return {
        "statement_number": statement.statement_number,
        "collection_amount_irr": str(statement.collection_amount_irr),
        "wage_rate_percent": str(statement.wage_rate_percent),
        "gross_amount_irr": str(statement.gross_amount_irr),
        "deductions_irr": str(statement.deductions_irr),
        "net_amount_irr": str(statement.net_amount_irr),
        "status": statement.status,
        "current_stage_order": statement.current_stage_order,
        "notes": statement.notes,
    }


def add_version(db: Session, statement: Statement, user: User, reason: str) -> None:
    db.add(StatementVersion(
        statement_id=statement.id,
        version=statement.version,
        snapshot_json=json.dumps(snapshot(statement), ensure_ascii=False),
        change_reason=reason,
        created_by=user.id,
    ))


def generate_statement_number(db: Session, year: int) -> str:
    count = db.scalar(select(func.count(Statement.id)).where(Statement.persian_year == year)) or 0
    return f"SV-{year}-{count + 1:05d}"


def create_statement(db: Session, *, contract: Contract, year: int, month: int,
                     deductions: Decimal, notes: str | None, user: User) -> Statement:
    existing = db.scalar(select(Statement).where(
        Statement.contract_id == contract.id,
        Statement.persian_year == year,
        Statement.persian_month == month,
    ))
    if existing:
        raise HTTPException(status_code=409, detail="برای این قرارداد و ماه قبلاً صورت‌وضعیت ایجاد شده است")

    collection = db.scalar(select(MonthlyCollection).where(
        MonthlyCollection.region_id == contract.region_id,
        MonthlyCollection.persian_year == year,
        MonthlyCollection.persian_month == month,
    ))
    wage = db.scalar(select(WageCalculation).where(
        WageCalculation.region_id == contract.region_id,
        WageCalculation.persian_year == year,
        WageCalculation.persian_month == month,
    ))
    if collection is None or wage is None:
        raise HTTPException(status_code=422, detail="وصول یا محاسبه دستمزد تأییدشده برای این ماه موجود نیست")

    calculated = calculate_statement(
        collection_amount_irr=collection.amount_irr,
        wage_rate_percent=wage.wage_rate_percent,
        deductions_irr=deductions,
        gross_amount_irr=wage.wage_amount_irr,
    )
    statement = Statement(
        statement_number=generate_statement_number(db, year),
        contract_id=contract.id,
        region_id=contract.region_id,
        persian_year=year,
        persian_month=month,
        collection_amount_irr=calculated.collection_amount_irr,
        wage_rate_percent=calculated.wage_rate_percent,
        gross_amount_irr=calculated.gross_amount_irr,
        deductions_irr=calculated.deductions_irr,
        net_amount_irr=calculated.net_amount_irr,
        status="pending_approval",
        current_stage_order=1,
        notes=notes,
        created_by=user.id,
    )
    db.add(statement)
    db.flush()
    for order, code, title, role in WORKFLOW_STAGES:
        db.add(StatementWorkflow(
            statement_id=statement.id, stage_order=order, stage_code=code,
            stage_title=title, required_role=role,
            status="current" if order == 1 else "pending",
        ))
    add_version(db, statement, user, "ایجاد اولیه")
    db.flush()
    return db.scalar(statement_query().where(Statement.id == statement.id))


def act_on_workflow(db: Session, statement: Statement, *, action: str, comment: str | None, user: User) -> Statement:
    if statement.status in {"rejected", "fully_settled"}:
        raise HTTPException(status_code=409, detail="این صورت‌وضعیت قابل اقدام نیست")
    item = next((x for x in statement.workflow_items if x.stage_order == statement.current_stage_order), None)
    if item is None or item.status != "current":
        raise HTTPException(status_code=409, detail="مرحله جاری معتبر نیست")
    if user.role != "brokerage_head" and item.required_role != user.role:
        raise HTTPException(status_code=403, detail="این مرحله مربوط به نقش شما نیست")

    item.action_by = user.id
    item.action_at = datetime.utcnow()
    item.comment = comment
    statement.version += 1
    if action == "reject":
        item.status = "rejected"
        statement.status = "rejected"
    else:
        item.status = "approved"
        next_item = next((x for x in statement.workflow_items if x.stage_order == item.stage_order + 1), None)
        if next_item:
            next_item.status = "current"
            statement.current_stage_order = next_item.stage_order
            statement.status = "pending_approval"
        else:
            statement.status = "approved_for_payment"
            statement.current_stage_order = len(WORKFLOW_STAGES) + 1
    add_version(db, statement, user, f"گردش کار: {action}")
    db.flush()
    return db.scalar(statement_query().where(Statement.id == statement.id))


def add_payment(db: Session, statement: Statement, *, amount: Decimal, date_persian: str,
                tracking: str | None, description: str | None, user: User) -> StatementPayment:
    if statement.status not in {"approved_for_payment", "partially_paid"}:
        raise HTTPException(status_code=409, detail="صورت‌وضعیت هنوز مجاز به پرداخت نیست")
    paid = sum((Decimal(x.amount_irr) for x in statement.payments), Decimal("0"))
    try:
        calculate_balance(statement.net_amount_irr, paid + amount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = StatementPayment(
        statement_id=statement.id, amount_irr=amount, payment_date_persian=date_persian,
        tracking_number=tracking, description=description, created_by=user.id,
    )
    db.add(row)
    statement.version += 1
    if paid + amount == Decimal(statement.net_amount_irr):
        statement.status = "fully_settled"
    else:
        statement.status = "partially_paid"
    add_version(db, statement, user, "ثبت پرداخت")
    db.flush()
    return row


def detail_payload(statement: Statement) -> dict:
    paid = sum((Decimal(x.amount_irr) for x in statement.payments), Decimal("0"))
    return {
        **{c.name: getattr(statement, c.name) for c in Statement.__table__.columns},
        "paid_amount_irr": paid,
        "remaining_amount_irr": max(Decimal("0"), Decimal(statement.net_amount_irr) - paid),
        "workflow_items": statement.workflow_items,
        "payments": statement.payments,
    }
