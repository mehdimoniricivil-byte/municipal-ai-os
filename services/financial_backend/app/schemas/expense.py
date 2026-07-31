from decimal import Decimal
from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    persian_year: int = 1405
    persian_month: int = Field(ge=1, le=12)
    expense_date_persian: str
    expense_type: str = Field(pattern="^(direct|shared)$")
    region_id: int | None = None
    category: str
    description: str | None = None
    amount_irr: Decimal = Field(gt=0)


class ExpenseRead(ExpenseCreate):
    id: int

    model_config = {"from_attributes": True}
