from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class WageBracketInput(BaseModel):
    min_growth_percent: Decimal | None = None
    max_growth_percent: Decimal | None = None
    wage_rate_percent: Decimal = Field(ge=0)
    priority: int = 0


class WageRuleSetCreate(BaseModel):
    title: str
    version: str
    effective_from: date
    effective_to: date | None = None
    calculation_basis: str = "actual_collection"
    status: str = "draft"
    notes: str | None = None
    brackets: list[WageBracketInput]


class WageCalculateRequest(BaseModel):
    region_id: int
    rule_set_id: int
    persian_year: int
    persian_month: int = Field(ge=1, le=12)
    actual_collection_irr: Decimal = Field(ge=0)
    matched_collection_irr: Decimal = Field(gt=0)
