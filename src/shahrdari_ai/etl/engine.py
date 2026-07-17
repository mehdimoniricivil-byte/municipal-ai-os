from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import create_engine, delete, inspect, insert, select, text, update
from sqlalchemy.engine import Engine

from .models import daily_changes, daily_snapshots, import_runs, metadata, taxpayers

COLUMN_ALIASES = {
    "identification_code": ["کد شناسایی", "كد شناسايي", "کد شناسايي", "كد شناسایی"],
    "case_number": ["شماره پرونده"],
    "district": ["ناحیه", "ناحيه", "منطقه فرعی", "منطقه فرعي"],
    "operator_name": ["نام متصدی", "نام متصدي"],
    "job": ["شغل واحد"],
    "phone": ["شماره تماس"],
    "address": ["آدرس واحد", "نشانی واحد صنفی", "نشاني واحد صنفي", "نشانی واحد صنفي", "نشاني واحد صنفی"],
    "payment_date": ["تاریخ پرداخت", "تاريخ پرداخت"],
    "bill_amount": ["مبلغ فیش", "مبلغ فيش"],
    "outstanding_debt": ["بدهی معوقه", "بدهي معوقه"],
    "business_tax": ["عوارض کسب", "عوارض كسب"],
    "passage_tax": ["عوارض راه عبور", "عوارض  راه عبور"],
    "sidewalk_use_tax": ["عوارض استفاده از معبر"],
    "signboard_tax": ["عوارض تابلو"],
    "waste_fee": ["رفع زباله", "دفع زباله", "دفع زبااله"],
}

FIELD_LABELS = {
    "identification_code": "کد شناسایی",
    "case_number": "شماره پرونده",
    "operator_name": "نام متصدی",
    "job": "شغل واحد",
    "phone": "شماره تماس",
    "address": "آدرس واحد",
    "payment_date": "تاریخ پرداخت",
    "bill_amount": "مبلغ فیش",
    "outstanding_debt": "بدهی معوقه",
    "business_tax": "عوارض کسب",
    "passage_tax": "عوارض راه عبور",
    "sidewalk_use_tax": "عوارض استفاده از معبر",
    "signboard_tax": "عوارض تابلو",
    "waste_fee": "رفع زباله",
}

REQUIRED_COLUMNS = {aliases[0]: field for field, aliases in COLUMN_ALIASES.items()}
TEXT_FIELDS = ["case_number", "district", "operator_name", "job", "phone", "address", "payment_date"]
OPTIONAL_COLUMNS = {"district"}
MONEY_FIELDS = ["bill_amount", "outstanding_debt", "business_tax", "passage_tax", "sidewalk_use_tax", "signboard_tax", "waste_fee"]
PROFILE_CHANGE_FIELDS = ["phone", "address", "job"]

_DIGIT_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_column_name(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.translate(_DIGIT_TRANSLATION)
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ").replace("\u200f", " ").replace("\ufeff", " ")
    return " ".join(text.split())


def _column_alias_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            lookup[normalize_column_name(alias)] = field
    return lookup


def _format_missing_columns_error(missing_fields: list[str], actual_columns: list[object]) -> str:
    lines = [
        "ستون‌های ضروری فایل اکسل پیدا نشدند.",
        "برای هر فیلد، یکی از نام‌های پذیرفته‌شده زیر باید در فایل وجود داشته باشد:",
    ]
    for field in missing_fields:
        aliases = "، ".join(COLUMN_ALIASES[field])
        lines.append(f"- فیلد {FIELD_LABELS[field]} ({field}): {aliases}")
    actual = "، ".join(str(column) for column in actual_columns) or "بدون ستون"
    lines.append(f"ستون‌های موجود در فایل: {actual}")
    return "\n".join(lines)


def _resolve_excel_columns(columns: Iterable[object]) -> dict[str, object]:
    alias_lookup = _column_alias_lookup()
    resolved: dict[str, object] = {}
    for column in columns:
        field = alias_lookup.get(normalize_column_name(column))
        if field and field not in resolved:
            resolved[field] = column
    missing = [field for field in COLUMN_ALIASES if field not in resolved and field not in OPTIONAL_COLUMNS]
    if missing:
        raise ValueError(_format_missing_columns_error(missing, list(columns)))
    return resolved


@dataclass(frozen=True)
class ImportResult:
    import_run_id: int
    rows_imported: int
    changes: list[dict]
    report_path: Path
    inserted_taxpayers: int = 0
    updated_taxpayers: int = 0
    skipped_duplicates: int = 0
    total_rows: int = 0
    row_errors: int = 0


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required unless an engine is passed explicitly")
    return create_engine(url)


def create_tables(engine: Engine) -> None:
    metadata.create_all(engine)
    _ensure_runtime_schema(engine)


def _ensure_runtime_schema(engine: Engine) -> None:
    """Apply lightweight additive migrations required by existing deployments."""
    required_import_run_columns = {
        "file_type": "VARCHAR(64) NOT NULL DEFAULT 'snapshot'",
        "uploaded_by": "VARCHAR(255) NOT NULL DEFAULT 'system'",
        "source_file_name": "TEXT NOT NULL DEFAULT ''",
        "imported_at": "DATETIME",
    }
    required_daily_snapshot_columns = {
        "business_tax": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "passage_tax": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "sidewalk_use_tax": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "signboard_tax": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "waste_fee": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "district": "VARCHAR(255)",
    }
    inspector = inspect(engine)
    existing_import_columns = {column["name"] for column in inspector.get_columns("import_runs")}
    missing_import_columns = [(name, ddl) for name, ddl in required_import_run_columns.items() if name not in existing_import_columns]
    existing_snapshot_columns = {column["name"] for column in inspector.get_columns("daily_snapshots")}
    missing_snapshot_columns = [(name, ddl) for name, ddl in required_daily_snapshot_columns.items() if name not in existing_snapshot_columns]
    if not missing_import_columns and not missing_snapshot_columns:
        return
    with engine.begin() as conn:
        for name, ddl in missing_import_columns:
            conn.execute(text(f"ALTER TABLE import_runs ADD COLUMN {name} {ddl}"))
        if "imported_at" in {name for name, _ in missing_import_columns}:
            conn.execute(text("UPDATE import_runs SET imported_at = COALESCE(finished_at, started_at) WHERE imported_at IS NULL"))
        for name, ddl in missing_snapshot_columns:
            conn.execute(text(f"ALTER TABLE daily_snapshots ADD COLUMN {name} {ddl}"))


def _clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _clean_money(value: object) -> Decimal:
    if pd.isna(value) or value == "":
        return Decimal("0")
    text = str(value).strip().replace(",", "").replace("٬", "")
    text = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
    if not text or text in {"-", "."}:
        return Decimal("0")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc



def _build_taxpayer_identifier(row: pd.Series) -> str | None:
    identification_code = _clean_text(row.get("identification_code"))
    case_number = _clean_text(row.get("case_number"))
    if identification_code and case_number:
        return f"{identification_code} | {case_number}"
    return identification_code or case_number

def read_snapshot_excel(path: str | Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=object)
    resolved_columns = _resolve_excel_columns(df.columns)
    total_rows = len(df)
    df = df[[source for source in resolved_columns.values()]].rename(
        columns={source: field for field, source in resolved_columns.items()}
    )
    for field in TEXT_FIELDS:
        if field in df.columns:
            df[field] = df[field].map(_clean_text)
    df["identification_code"] = df["identification_code"].map(_clean_text)
    df["identification_code"] = df.apply(_build_taxpayer_identifier, axis=1)
    missing_identifier_mask = df["identification_code"].isna()
    row_errors = int(missing_identifier_mask.sum())
    if missing_identifier_mask.any():
        df = df.loc[~missing_identifier_mask].copy()
    duplicate_mask = df["identification_code"].duplicated(keep=False)
    skipped_duplicates = int(duplicate_mask.sum())
    if duplicate_mask.any():
        df = df.loc[~duplicate_mask].copy()
    df.attrs["total_rows"] = total_rows
    df.attrs["skipped_duplicates"] = skipped_duplicates
    df.attrs["row_errors"] = row_errors
    for field in MONEY_FIELDS:
        df[field] = df[field].map(_clean_money)
    ordered_columns = [field for field in COLUMN_ALIASES if field in df.columns]
    return df[ordered_columns]


def _rows_by_key(rows: Iterable[dict]) -> dict[str, dict]:
    return {row["identification_code"]: dict(row) for row in rows}


def _value_changed(old: object, new: object) -> bool:
    return (old or None) != (new or None)


def detect_changes(current: pd.DataFrame, previous_rows: Iterable[dict]) -> list[dict]:
    current_by_key = _rows_by_key(current.to_dict("records"))
    previous_by_key = _rows_by_key(previous_rows)
    changes: list[dict] = []
    for key, row in current_by_key.items():
        previous = previous_by_key.get(key)
        if previous is None:
            changes.append({"identification_code": key, "case_number": row.get("case_number"), "change_type": "new_taxpayer", "field_name": None, "old_value": None, "new_value": None})
            continue
        old_debt = Decimal(str(previous.get("outstanding_debt") or 0)).quantize(Decimal("0.01"))
        new_debt = Decimal(str(row.get("outstanding_debt") or 0)).quantize(Decimal("0.01"))
        if old_debt != new_debt:
            change_type = "decreased_debt" if new_debt < old_debt else "increased_debt"
            changes.append({"identification_code": key, "case_number": row.get("case_number"), "change_type": "changed_debt", "field_name": "outstanding_debt", "old_value": str(old_debt), "new_value": str(new_debt)})
            changes.append({"identification_code": key, "case_number": row.get("case_number"), "change_type": change_type, "field_name": "outstanding_debt", "old_value": str(old_debt), "new_value": str(new_debt)})
        if _value_changed(previous.get("payment_date"), row.get("payment_date")) and row.get("payment_date"):
            changes.append({"identification_code": key, "case_number": row.get("case_number"), "change_type": "new_payment_date", "field_name": "payment_date", "old_value": previous.get("payment_date"), "new_value": row.get("payment_date")})
        for field in PROFILE_CHANGE_FIELDS:
            if _value_changed(previous.get(field), row.get(field)):
                changes.append({"identification_code": key, "case_number": row.get("case_number"), "change_type": f"changed_{field}", "field_name": field, "old_value": previous.get(field), "new_value": row.get(field)})
    for key, row in previous_by_key.items():
        if key not in current_by_key:
            changes.append({"identification_code": key, "case_number": row.get("case_number"), "change_type": "removed_taxpayer", "field_name": None, "old_value": None, "new_value": None})
    return changes


def _previous_snapshot_rows(conn, snapshot_date: str, region: str) -> list[dict]:
    previous_date = conn.execute(
        select(daily_snapshots.c.snapshot_date)
        .where(daily_snapshots.c.region == region, daily_snapshots.c.snapshot_date < snapshot_date)
        .order_by(daily_snapshots.c.snapshot_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    if previous_date is None:
        return []
    return [dict(row._mapping) for row in conn.execute(select(daily_snapshots).where(daily_snapshots.c.region == region, daily_snapshots.c.snapshot_date == previous_date))]


def _write_report(snapshot_date: str, region: str, rows_imported: int, changes: list[dict], report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    counts = pd.Series([c["change_type"] for c in changes], dtype="object").value_counts().to_dict() if changes else {}
    labels = {
        "new_taxpayer": "مودیان جدید",
        "removed_taxpayer": "مودیان حذف‌شده",
        "changed_debt": "تغییر بدهی",
        "decreased_debt": "کاهش بدهی",
        "increased_debt": "افزایش بدهی",
        "new_payment_date": "تاریخ پرداخت جدید",
        "changed_phone": "تغییر شماره تماس",
        "changed_address": "تغییر نشانی",
        "changed_job": "تغییر شغل",
    }
    lines = [f"# گزارش روزانه مدیر - {snapshot_date}", "", f"- منطقه: {region}", f"- تعداد ردیف‌های وارد شده: {rows_imported}", f"- تعداد کل تغییرات: {len(changes)}", "", "## خلاصه تغییرات"]
    for key, label in labels.items():
        lines.append(f"- {label}: {counts.get(key, 0)}")
    lines.extend(["", "## جزئیات تغییرات", "| کد شناسایی | شماره پرونده | نوع تغییر | فیلد | مقدار قبلی | مقدار جدید |", "|---|---|---|---|---|---|"])
    for change in changes:
        lines.append(f"| {change.get('identification_code') or ''} | {change.get('case_number') or ''} | {change.get('change_type') or ''} | {change.get('field_name') or ''} | {change.get('old_value') or ''} | {change.get('new_value') or ''} |")
    path = report_dir / f"{snapshot_date}-manager-report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def import_excel(
    file_path: str | Path,
    snapshot_date: str,
    region: str,
    engine: Engine | None = None,
    report_dir: str | Path = "data/reports",
    file_type: str = "snapshot",
    uploaded_by: str = "system",
    source_file_name: str | None = None,
    district: str | None = None,
) -> ImportResult:
    engine = engine or make_engine()
    create_tables(engine)
    df = read_snapshot_excel(file_path)
    skipped_duplicates = int(df.attrs.get("skipped_duplicates", 0))
    total_rows = int(df.attrs.get("total_rows", len(df)))
    row_errors = int(df.attrs.get("row_errors", 0))
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        selected_file_type = (file_type or "snapshot").strip() or "snapshot"
        selected_uploader = (uploaded_by or "system").strip() or "system"
        selected_source_name = source_file_name or Path(file_path).name
        existing_run = conn.execute(
            select(import_runs.c.id).where(
                import_runs.c.snapshot_date == snapshot_date,
                import_runs.c.region == region,
                import_runs.c.file_type == selected_file_type,
            )
        ).scalar_one_or_none()
        if existing_run is not None:
            raise ValueError("Duplicate snapshot import: this region, file type, and snapshot date already exist")
        run_id = conn.execute(
            insert(import_runs).values(
                snapshot_date=snapshot_date,
                region=region,
                source_file=str(file_path),
                file_type=selected_file_type,
                uploaded_by=selected_uploader,
                source_file_name=selected_source_name,
                imported_at=now,
                status="running",
                rows_imported=0,
                started_at=now,
            )
        ).inserted_primary_key[0]
        previous_rows = _previous_snapshot_rows(conn, snapshot_date, region)
        rows = df.to_dict("records")
        inserted_taxpayers = 0
        updated_taxpayers = 0
        for row in rows:
            found = conn.execute(select(taxpayers.c.id).where(taxpayers.c.identification_code == row["identification_code"])).scalar_one_or_none()
            values = {k: row.get(k) for k in ["identification_code", "case_number", "operator_name", "job", "phone", "address"]} | {"updated_at": now}
            if found:
                conn.execute(update(taxpayers).where(taxpayers.c.id == found).values(**values))
                updated_taxpayers += 1
            else:
                conn.execute(insert(taxpayers).values(**values, created_at=now))
                inserted_taxpayers += 1
        snapshot_values = [row | {"import_run_id": run_id, "snapshot_date": snapshot_date, "region": region, "district": row.get("district") or district, "created_at": now} for row in rows]
        if snapshot_values:
            conn.execute(insert(daily_snapshots), snapshot_values)
        changes = detect_changes(df, previous_rows)
        if changes:
            conn.execute(insert(daily_changes), [c | {"import_run_id": run_id, "snapshot_date": snapshot_date, "region": region, "created_at": now} for c in changes])
        report_path = _write_report(snapshot_date, region, len(rows), changes, Path(report_dir))
        conn.execute(update(import_runs).where(import_runs.c.id == run_id).values(status="completed", rows_imported=len(rows), report_path=str(report_path), finished_at=datetime.now(timezone.utc)))
    return ImportResult(run_id, len(rows), changes, report_path, inserted_taxpayers, updated_taxpayers, skipped_duplicates, total_rows, row_errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shahrdari_ai.etl")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-excel")
    imp.add_argument("--file", required=True)
    imp.add_argument("--date", required=True)
    imp.add_argument("--region", required=True)
    imp.add_argument("--database-url", default=None)
    imp.add_argument("--report-dir", default="data/reports")
    args = parser.parse_args(argv)
    if args.command == "import-excel":
        result = import_excel(args.file, args.date, args.region, make_engine(args.database_url), args.report_dir)
        print(f"Imported {result.rows_imported} rows; changes={len(result.changes)}; report={result.report_path}")
    return 0
