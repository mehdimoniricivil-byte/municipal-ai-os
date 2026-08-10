from decimal import Decimal
from pydantic import BaseModel, Field


class CalendarDayUpdate(BaseModel):
    day_type: str = Field(pattern="^(normal|thursday|friday|holiday|special_workday)$")
    weight: Decimal = Field(ge=0)
    description: str | None = None
    is_approved: bool = True
