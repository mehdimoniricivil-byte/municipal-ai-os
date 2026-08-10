from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.models import Expense, User
from app.db.session import get_db
from app.schemas.expense import ExpenseCreate, ExpenseRead
from app.services.audit import write_audit_log

router = APIRouter()


@router.post("", response_model=ExpenseRead)
def create_expense(
    payload: ExpenseCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("expense.create")),
):
    if payload.expense_type == "direct" and payload.region_id is None:
        raise HTTPException(status_code=422, detail="برای هزینه مستقیم، منطقه الزامی است.")
    if payload.expense_type == "shared":
        payload.region_id = None

    row = Expense(**payload.model_dump())
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        user=user,
        module="expenses",
        action="create",
        request=request,
        record_type="Expense",
        record_id=row.id,
        new_value=payload.model_dump(),
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("", response_model=list[ExpenseRead])
def list_expenses(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permissions("expense.view")),
):
    return db.scalars(
        select(Expense)
        .where(Expense.persian_year == year, Expense.persian_month == month)
        .order_by(Expense.id.desc())
    ).all()
