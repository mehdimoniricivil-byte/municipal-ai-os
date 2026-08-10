from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.models import Contract, Statement, User
from app.db.session import get_db
from app.schemas.statements import (
    ContractCreate, ContractOut, PaymentCreate, PaymentOut, StatementCreate,
    StatementDetail, StatementOut, WorkflowAction,
)
from app.services.audit import write_audit_log
from app.services.statements import (
    act_on_workflow, add_payment, create_statement, detail_payload, statement_query,
)

router = APIRouter()


@router.post("/contracts", response_model=ContractOut, status_code=201)
def create_contract(payload: ContractCreate, request: Request,
                    user: User = Depends(require_permissions("statement.manage")),
                    db: Session = Depends(get_db)) -> Contract:
    if db.scalar(select(Contract).where(Contract.contract_number == payload.contract_number)):
        raise HTTPException(status_code=409, detail="شماره قرارداد تکراری است")
    row = Contract(**payload.model_dump())
    db.add(row); db.flush()
    write_audit_log(db, user=user, module="statements", action="contract.create", request=request,
                    record_type="contract", record_id=row.id, new_value=payload.model_dump())
    db.commit(); db.refresh(row)
    return row


@router.get("/contracts", response_model=list[ContractOut])
def list_contracts(region_id: int | None = None,
                   _user: User = Depends(require_permissions("statement.view")),
                   db: Session = Depends(get_db)) -> list[Contract]:
    stmt = select(Contract).order_by(Contract.id.desc())
    if region_id is not None:
        stmt = stmt.where(Contract.region_id == region_id)
    return list(db.scalars(stmt))


@router.post("", response_model=StatementDetail, status_code=201)
def create(payload: StatementCreate, request: Request,
           user: User = Depends(require_permissions("statement.manage")),
           db: Session = Depends(get_db)) -> dict:
    contract = db.get(Contract, payload.contract_id)
    if contract is None or contract.status != "active":
        raise HTTPException(status_code=404, detail="قرارداد فعال پیدا نشد")
    row = create_statement(db, contract=contract, year=payload.persian_year,
                           month=payload.persian_month, deductions=payload.deductions_irr,
                           notes=payload.notes, user=user)
    write_audit_log(db, user=user, module="statements", action="statement.create", request=request,
                    record_type="statement", record_id=row.id,
                    new_value={"statement_number": row.statement_number})
    db.commit()
    return detail_payload(row)


@router.get("", response_model=list[StatementOut])
def list_statements(year: int | None = Query(None), month: int | None = Query(None),
                    region_id: int | None = Query(None), status: str | None = Query(None),
                    _user: User = Depends(require_permissions("statement.view")),
                    db: Session = Depends(get_db)) -> list[Statement]:
    stmt = select(Statement).order_by(Statement.created_at.desc())
    for field, value in ((Statement.persian_year, year), (Statement.persian_month, month),
                         (Statement.region_id, region_id), (Statement.status, status)):
        if value is not None:
            stmt = stmt.where(field == value)
    return list(db.scalars(stmt))


@router.get("/{statement_id}", response_model=StatementDetail)
def detail(statement_id: int,
           _user: User = Depends(require_permissions("statement.view")),
           db: Session = Depends(get_db)) -> dict:
    row = db.scalar(statement_query().where(Statement.id == statement_id))
    if row is None:
        raise HTTPException(status_code=404, detail="صورت‌وضعیت پیدا نشد")
    return detail_payload(row)


@router.post("/{statement_id}/workflow", response_model=StatementDetail)
def workflow(statement_id: int, payload: WorkflowAction, request: Request,
             user: User = Depends(require_permissions("statement.approve")),
             db: Session = Depends(get_db)) -> dict:
    row = db.scalar(statement_query().where(Statement.id == statement_id))
    if row is None:
        raise HTTPException(status_code=404, detail="صورت‌وضعیت پیدا نشد")
    row = act_on_workflow(db, row, action=payload.action, comment=payload.comment, user=user)
    write_audit_log(db, user=user, module="statements", action=f"workflow.{payload.action}", request=request,
                    record_type="statement", record_id=row.id, new_value=payload.model_dump())
    db.commit()
    return detail_payload(row)


@router.post("/{statement_id}/payments", response_model=PaymentOut, status_code=201)
def payment(statement_id: int, payload: PaymentCreate, request: Request,
            user: User = Depends(require_permissions("payment.create")),
            db: Session = Depends(get_db)):
    row = db.scalar(statement_query().where(Statement.id == statement_id))
    if row is None:
        raise HTTPException(status_code=404, detail="صورت‌وضعیت پیدا نشد")
    payment_row = add_payment(db, row, amount=payload.amount_irr,
                              date_persian=payload.payment_date_persian,
                              tracking=payload.tracking_number,
                              description=payload.description, user=user)
    write_audit_log(db, user=user, module="statements", action="payment.create", request=request,
                    record_type="statement_payment", record_id=payment_row.id,
                    new_value=payload.model_dump())
    db.commit(); db.refresh(payment_row)
    return payment_row
