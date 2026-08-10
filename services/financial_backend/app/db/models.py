from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CalendarDay(Base):
    __tablename__ = "operational_calendar"

    id: Mapped[int] = mapped_column(primary_key=True)
    gregorian_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    persian_year: Mapped[int] = mapped_column(Integer, index=True)
    persian_month: Mapped[int] = mapped_column(Integer, index=True)
    persian_day: Mapped[int] = mapped_column(Integer)
    weekday_name: Mapped[str] = mapped_column(String(20))
    day_type: Mapped[str] = mapped_column(String(30), default="normal")
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("1"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)


class MonthlyCollection(Base):
    __tablename__ = "monthly_collections"
    __table_args__ = (
        UniqueConstraint("region_id", "persian_year", "persian_month", name="uq_collection_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    persian_year: Mapped[int] = mapped_column(Integer, index=True)
    persian_month: Mapped[int] = mapped_column(Integer, index=True)
    amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0), default=0)
    as_of_persian_date: Mapped[str] = mapped_column(String(10))
    source_import_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    region: Mapped[Region] = relationship()


class MonthlyTarget(Base):
    __tablename__ = "monthly_targets"
    __table_args__ = (
        UniqueConstraint("region_id", "persian_year", "persian_month", name="uq_target_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    persian_year: Mapped[int] = mapped_column(Integer, index=True)
    persian_month: Mapped[int] = mapped_column(Integer, index=True)
    baseline_year: Mapped[int] = mapped_column(Integer)
    baseline_amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    multiplier: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("2"))
    target_amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True)

    region: Mapped[Region] = relationship()


class WageRuleSet(Base):
    __tablename__ = "wage_rule_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    version: Mapped[str] = mapped_column(String(30), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    calculation_basis: Mapped[str] = mapped_column(String(50), default="actual_collection")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    brackets: Mapped[list[WageBracket]] = relationship(
        back_populates="rule_set",
        cascade="all, delete-orphan",
        order_by="WageBracket.priority",
    )


class WageBracket(Base):
    __tablename__ = "wage_brackets"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_set_id: Mapped[int] = mapped_column(ForeignKey("wage_rule_sets.id"), index=True)
    min_growth_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_growth_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    wage_rate_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    priority: Mapped[int] = mapped_column(Integer, default=0)

    rule_set: Mapped[WageRuleSet] = relationship(back_populates="brackets")


class WageCalculation(Base):
    __tablename__ = "wage_calculations"
    __table_args__ = (
        UniqueConstraint("region_id", "persian_year", "persian_month", name="uq_wage_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    rule_set_id: Mapped[int] = mapped_column(ForeignKey("wage_rule_sets.id"))
    persian_year: Mapped[int] = mapped_column(Integer)
    persian_month: Mapped[int] = mapped_column(Integer)
    actual_collection_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    matched_collection_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    growth_percent: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    wage_rate_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    wage_amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    calculation_trace: Mapped[str] = mapped_column(Text)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    region: Mapped[Region] = relationship()
    rule_set: Mapped[WageRuleSet] = relationship()


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    persian_year: Mapped[int] = mapped_column(Integer, index=True)
    persian_month: Mapped[int] = mapped_column(Integer, index=True)
    expense_date_persian: Mapped[str] = mapped_column(String(10))
    expense_type: Mapped[str] = mapped_column(String(20))  # direct/shared
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    region: Mapped[Region | None] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    region: Mapped[Region | None] = relationship()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship()


class LoginAudit(Base):
    __tablename__ = "login_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(80), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    module: Mapped[str] = mapped_column(String(60), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    record_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    record_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped[User | None] = relationship()


class CollectionUpload(Base):
    __tablename__ = "collection_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    persian_year: Mapped[int] = mapped_column(Integer, index=True)
    persian_month: Mapped[int] = mapped_column(Integer, index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="validated", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0), default=0)
    validation_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    region: Mapped[Region] = relationship()
    uploader: Mapped[User] = relationship()


class CollectionRecord(Base):
    __tablename__ = "collection_records"
    __table_args__ = (
        UniqueConstraint("region_id", "source_row_hash", name="uq_collection_record_region_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("collection_uploads.id"), index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    persian_year: Mapped[int] = mapped_column(Integer, index=True)
    persian_month: Mapped[int] = mapped_column(Integer, index=True)
    payment_date_persian: Mapped[str] = mapped_column(String(10), index=True)
    receipt_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    payer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    business_title: Mapped[str | None] = mapped_column(String(250), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    source_row_number: Mapped[int] = mapped_column(Integer)
    source_row_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    upload: Mapped[CollectionUpload] = relationship()
    region: Mapped[Region] = relationship()

class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    contract_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    start_date_persian: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date_persian: Mapped[str | None] = mapped_column(String(10), nullable=True)
    contract_amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0), default=0)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    region: Mapped[Region] = relationship()


class Statement(Base):
    __tablename__ = "statements"
    __table_args__ = (
        UniqueConstraint("contract_id", "persian_year", "persian_month", name="uq_statement_contract_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    persian_year: Mapped[int] = mapped_column(Integer, index=True)
    persian_month: Mapped[int] = mapped_column(Integer, index=True)
    collection_amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0), default=0)
    wage_rate_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    gross_amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0), default=0)
    deductions_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0), default=0)
    net_amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0), default=0)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    current_stage_order: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contract: Mapped[Contract] = relationship()
    region: Mapped[Region] = relationship()
    creator: Mapped[User] = relationship()
    workflow_items: Mapped[list["StatementWorkflow"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan", order_by="StatementWorkflow.stage_order"
    )
    payments: Mapped[list["StatementPayment"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan", order_by="StatementPayment.payment_date_persian"
    )
    versions: Mapped[list["StatementVersion"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan", order_by="StatementVersion.version"
    )


class StatementWorkflow(Base):
    __tablename__ = "statement_workflow"
    __table_args__ = (UniqueConstraint("statement_id", "stage_order", name="uq_statement_stage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    stage_order: Mapped[int] = mapped_column(Integer)
    stage_code: Mapped[str] = mapped_column(String(50), index=True)
    stage_title: Mapped[str] = mapped_column(String(120))
    required_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    action_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    statement: Mapped[Statement] = relationship(back_populates="workflow_items")
    actor: Mapped[User | None] = relationship()


class StatementPayment(Base):
    __tablename__ = "statement_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    amount_irr: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    payment_date_persian: Mapped[str] = mapped_column(String(10), index=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    statement: Mapped[Statement] = relationship(back_populates="payments")
    creator: Mapped[User] = relationship()


class StatementVersion(Base):
    __tablename__ = "statement_versions"
    __table_args__ = (UniqueConstraint("statement_id", "version", name="uq_statement_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    statement: Mapped[Statement] = relationship(back_populates="versions")
    creator: Mapped[User] = relationship()
