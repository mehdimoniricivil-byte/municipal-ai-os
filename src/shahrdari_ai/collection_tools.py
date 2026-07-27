from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from .etl.engine import make_engine

router = APIRouter(prefix="/api/ai/tools", tags=["AI Tools"])


class CollectionSummaryRequest(BaseModel):
    region_id: int = Field(gt=0)
    from_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    to_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def validate_range(self) -> "CollectionSummaryRequest":
        if self.from_date > self.to_date:
            raise ValueError("from_date must be before or equal to to_date")
        return self


class CollectionSummaryResponse(BaseModel):
    region_id: int
    actual_collection_irr: int
    payment_count: int
    data_status: Literal["available", "no_data", "region_not_found"]


_REGION_NAMES: dict[int, tuple[str, ...]] = {
    1: ("منطقه 1", "منطقه ۱", "منطقه یک"),
    2: ("منطقه 2", "منطقه ۲", "منطقه دو"),
    3: ("منطقه 3", "منطقه ۳", "منطقه سه"),
}


@router.post("/get-collection-summary", response_model=CollectionSummaryResponse)
def get_collection_summary(request: CollectionSummaryRequest) -> CollectionSummaryResponse:
    region_names = _REGION_NAMES.get(request.region_id)
    if region_names is None:
        return CollectionSummaryResponse(
            region_id=request.region_id,
            actual_collection_irr=0,
            payment_count=0,
            data_status="region_not_found",
        )

    # Snapshot dates are stored as Gregorian strings while payment dates are
    # Jalali strings. Therefore, choose the latest completed cumulative
    # snapshot independently, then filter its payment rows by normalized
    # Jalali payment_date values.
    statement = text(
        """
        WITH latest_runs AS (
            SELECT region, MAX(id) AS import_run_id
            FROM import_runs
            WHERE status = 'completed'
              AND region IN (:region_1, :region_2, :region_3)
            GROUP BY region
        ), normalized_payments AS (
            SELECT s.bill_amount,
                   REPLACE(
                       TRANSLATE(
                           TRIM(s.payment_date),
                           '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩',
                           '01234567890123456789'
                       ),
                       '/',
                       '-'
                   ) AS normalized_payment_date
            FROM daily_snapshots s
            JOIN latest_runs lr ON lr.import_run_id = s.import_run_id
            WHERE s.payment_date IS NOT NULL
              AND TRIM(s.payment_date) <> ''
              AND LOWER(TRIM(s.payment_date)) <> 'nan'
        )
        SELECT COALESCE(SUM(bill_amount), 0) AS actual_collection_irr,
               COUNT(*) AS payment_count
        FROM normalized_payments
        WHERE normalized_payment_date >= :from_date
          AND normalized_payment_date <= :to_date
        """
    )

    params = {
        "region_1": region_names[0],
        "region_2": region_names[1],
        "region_3": region_names[2],
        "from_date": request.from_date,
        "to_date": request.to_date,
    }

    try:
        engine = make_engine()
        with engine.connect() as connection:
            row = connection.execute(statement, params).one()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="collection_query_failed") from exc

    amount = int(row.actual_collection_irr or 0)
    count = int(row.payment_count or 0)
    return CollectionSummaryResponse(
        region_id=request.region_id,
        actual_collection_irr=amount,
        payment_count=count,
        data_status="available" if count else "no_data",
    )
