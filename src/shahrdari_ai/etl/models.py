from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

taxpayers = Table(
    "taxpayers",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("identification_code", String(255), nullable=False, unique=True, index=True),
    Column("case_number", String(255), nullable=True, index=True),
    Column("operator_name", Text, nullable=True),
    Column("job", Text, nullable=True),
    Column("phone", Text, nullable=True),
    Column("address", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

import_runs = Table(
    "import_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("snapshot_date", String(32), nullable=False),
    Column("region", String(255), nullable=False),
    Column("source_file", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("rows_imported", Integer, nullable=False, default=0),
    Column("report_path", Text, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("snapshot_date", "region", name="uq_import_runs_snapshot_region"),
)

daily_snapshots = Table(
    "daily_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("import_run_id", Integer, ForeignKey("import_runs.id"), nullable=False, index=True),
    Column("snapshot_date", String(32), nullable=False, index=True),
    Column("region", String(255), nullable=False, index=True),
    Column("identification_code", String(255), nullable=False, index=True),
    Column("case_number", String(255), nullable=True, index=True),
    Column("operator_name", Text, nullable=True),
    Column("job", Text, nullable=True),
    Column("phone", Text, nullable=True),
    Column("address", Text, nullable=True),
    Column("payment_date", String(64), nullable=True),
    Column("bill_amount", Numeric(18, 2), nullable=False, default=0),
    Column("outstanding_debt", Numeric(18, 2), nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("snapshot_date", "region", "identification_code", name="uq_daily_snapshot_key"),
)

daily_changes = Table(
    "daily_changes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("import_run_id", Integer, ForeignKey("import_runs.id"), nullable=False, index=True),
    Column("snapshot_date", String(32), nullable=False, index=True),
    Column("region", String(255), nullable=False, index=True),
    Column("identification_code", String(255), nullable=False, index=True),
    Column("case_number", String(255), nullable=True),
    Column("change_type", String(64), nullable=False, index=True),
    Column("field_name", String(64), nullable=True),
    Column("old_value", Text, nullable=True),
    Column("new_value", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
