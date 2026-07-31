from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class ContractCreate(BaseModel):
    region_id: int
    contract_number: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    start_date_persian: str | None = None
    end_date_persian: str | None = None
    contract_amount_irr: Decimal = Decimal("0")


class ContractOut(ContractCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    created_at: datetime


class StatementCreate(BaseModel):
    contract_id: int
    persian_year: int = Field(ge=1400, le=1500)
    persian_month: int = Field(ge=1, le=12)
    deductions_irr: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class WorkflowAction(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    comment: str | None = None


class PaymentCreate(BaseModel):
    amount_irr: Decimal = Field(gt=0)
    payment_date_persian: str = Field(min_length=8, max_length=10)
    tracking_number: str | None = None
    description: str | None = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    stage_order: int
    stage_code: str
    stage_title: str
    required_role: str | None
    status: str
    action_by: int | None
    action_at: datetime | None
    comment: str | None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount_irr: Decimal
    payment_date_persian: str
    tracking_number: str | None
    description: str | None
    created_by: int
    created_at: datetime


class StatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    statement_number: str
    contract_id: int
    region_id: int
    persian_year: int
    persian_month: int
    collection_amount_irr: Decimal
    wage_rate_percent: Decimal
    gross_amount_irr: Decimal
    deductions_irr: Decimal
    net_amount_irr: Decimal
    status: str
    current_stage_order: int
    version: int
    notes: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class StatementDetail(StatementOut):
    paid_amount_irr: Decimal
    remaining_amount_irr: Decimal
    workflow_items: list[WorkflowOut]
    payments: list[PaymentOut]
