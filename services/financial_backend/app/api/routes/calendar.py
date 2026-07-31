from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CalendarDay
from app.db.session import get_db
from app.schemas.calendar import CalendarDayUpdate


router = APIRouter()


@router.get("")
def list_calendar(year: int, month: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(CalendarDay)
        .where(
            CalendarDay.persian_year == year,
            CalendarDay.persian_month == month,
        )
        .order_by(CalendarDay.persian_day)
    ).all()
    return rows


@router.patch("/{calendar_day_id}")
def update_calendar_day(
    calendar_day_id: int,
    payload: CalendarDayUpdate,
    db: Session = Depends(get_db),
):
    row = db.get(CalendarDay, calendar_day_id)
    if not row:
        raise HTTPException(status_code=404, detail="روز تقویم پیدا نشد.")

    row.day_type = payload.day_type
    row.weight = payload.weight
    row.description = payload.description
    row.is_approved = payload.is_approved
    db.commit()
    db.refresh(row)
    return row
