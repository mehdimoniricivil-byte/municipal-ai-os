from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import create_engine, delete, insert, select, update
from sqlalchemy.engine import Engine

from .models import daily_changes, daily_snapshots, import_runs, metadata, taxpayers

REQUIRED_COLUMNS = {
    "کد شناسایی": "identification_code",
    "شماره پرونده": "case_number",
    "نام متصدی": "operator_name",
    "شغل واحد": "job",
    "شماره تماس": "phone",
    "نشانی واحد صنفی": "address",
    "تاریخ پرداخت": "payment_date",
    "مبلغ فیش": "bill_amount",
    "بدهی معوقه": "outstanding_debt",
}
TEXT_FIELDS = ["case_number", "operator_name", "job", "phone", "address", "payment_date"]
PROFILE_CHANGE_FIELDS = ["phone", "address", "job"]


@dataclass(frozen=True)
class ImportResult:
    import_run_id: int
    rows_imported: int
    changes: list[dict]
    report_path: Path


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required unless an engine is passed explicitly")
    return create_engine(url)


def create_tables(engine: Engine) -> None:
    metadata.create_all(engine)


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


def read_snapshot_excel(path: str | Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=object)
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError("Missing required Excel columns: " + ", ".join(missing))
    df = df[list(REQUIRED_COLUMNS)].rename(columns=REQUIRED_COLUMNS)
    for field in TEXT_FIELDS:
        df[field] = df[field].map(_clean_text)
    df["identification_code"] = df["identification_code"].map(_clean_text)
    if df["identification_code"].isna().any():
        raise ValueError("کد شناسایی is required for every row")
    if df["identification_code"].duplicated().any():
        duplicates = sorted(df.loc[df["identification_code"].duplicated(), "identification_code"].unique())
        raise ValueError("Duplicate کد شناسایی values: " + ", ".join(duplicates))
    df["bill_amount"] = df["bill_amount"].map(_clean_money)
    df["outstanding_debt"] = df["outstanding_debt"].map(_clean_money)
    return df


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


def import_excel(file_path: str | Path, snapshot_date: str, region: str, engine: Engine | None = None, report_dir: str | Path = "data/reports") -> ImportResult:
    engine = engine or make_engine()
    create_tables(engine)
    df = read_snapshot_excel(file_path)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        existing_run = conn.execute(select(import_runs.c.id).where(import_runs.c.snapshot_date == snapshot_date, import_runs.c.region == region)).scalar_one_or_none()
        if existing_run is not None:
            conn.execute(delete(daily_changes).where(daily_changes.c.import_run_id == existing_run))
            conn.execute(delete(daily_snapshots).where(daily_snapshots.c.import_run_id == existing_run))
            conn.execute(delete(import_runs).where(import_runs.c.id == existing_run))
        run_id = conn.execute(insert(import_runs).values(snapshot_date=snapshot_date, region=region, source_file=str(file_path), status="running", rows_imported=0, started_at=now)).inserted_primary_key[0]
        previous_rows = _previous_snapshot_rows(conn, snapshot_date, region)
        rows = df.to_dict("records")
        for row in rows:
            found = conn.execute(select(taxpayers.c.id).where(taxpayers.c.identification_code == row["identification_code"])).scalar_one_or_none()
            values = {k: row.get(k) for k in ["identification_code", "case_number", "operator_name", "job", "phone", "address"]} | {"updated_at": now}
            if found:
                conn.execute(update(taxpayers).where(taxpayers.c.id == found).values(**values))
            else:
                conn.execute(insert(taxpayers).values(**values, created_at=now))
        snapshot_values = [row | {"import_run_id": run_id, "snapshot_date": snapshot_date, "region": region, "created_at": now} for row in rows]
        if snapshot_values:
            conn.execute(insert(daily_snapshots), snapshot_values)
        changes = detect_changes(df, previous_rows)
        if changes:
            conn.execute(insert(daily_changes), [c | {"import_run_id": run_id, "snapshot_date": snapshot_date, "region": region, "created_at": now} for c in changes])
        report_path = _write_report(snapshot_date, region, len(rows), changes, Path(report_dir))
        conn.execute(update(import_runs).where(import_runs.c.id == run_id).values(status="completed", rows_imported=len(rows), report_path=str(report_path), finished_at=datetime.now(timezone.utc)))
    return ImportResult(run_id, len(rows), changes, report_path)


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
