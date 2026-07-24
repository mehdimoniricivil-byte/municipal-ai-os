from __future__ import annotations

import html
import logging
import os
import re
import secrets
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from sqlalchemy import text

from .etl.engine import import_excel, make_engine

IMPORT_DIR = Path("data/imports")

logger = logging.getLogger(__name__)

app = FastAPI(title="Municipality Excel Upload")


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 1rem; line-height: 1.8; background: #f6f7fb; color: #111827; }}
    main {{ max-width: 72rem; margin: auto; }}
    label {{ display: block; margin-top: 1rem; font-weight: 700; }}
    input, select, button {{ box-sizing: border-box; font: inherit; width: 100%; padding: .7rem; margin-top: .25rem; }}
    button {{ background: #155eef; color: white; border: 0; border-radius: .4rem; margin-top: 1.25rem; }}
    .card {{ border: 1px solid #ddd; border-radius: .75rem; padding: 1rem; background: white; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: .75rem; }}
    .card b {{ display: block; font-size: 1.35rem; margin-top: .35rem; }}
    .filters {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: .5rem; margin: 1rem 0; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: .75rem; overflow: hidden; margin: 1rem 0; font-size: .92rem; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: .55rem; text-align: right; vertical-align: top; }}
    th {{ background: #eef2ff; }}
    a {{ color: #155eef; }}
    .error {{ color: #b42318; }}
    @media (max-width: 640px) {{ body {{ padding: .5rem; }} table {{ display: block; overflow-x: auto; white-space: nowrap; }} h1 {{ font-size: 1.4rem; }} }}
  </style>
</head>
<body><main>{body}</main></body>
</html>""",
        status_code=status_code,
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_form() -> HTMLResponse:
    today = date.today().isoformat()
    return _page(
        "بارگذاری فایل اکسل شهرداری",
        f"""
<h1>بارگذاری فایل اکسل شهرداری</h1>
<form class="card" action="/upload" method="post" enctype="multipart/form-data">
  <label for="snapshot_date">تاریخ فایل</label>
  <input id="snapshot_date" name="snapshot_date" type="text" value="{today}" required>
  <label for="region">منطقه</label>
  <input id="region" name="region" type="text" value="منطقه یک" required>
  <label for="file_type">نوع فایل</label>
  <select id="file_type" name="file_type" required>
    <option value="snapshot">فایل وضعیت روزانه</option>
    <option value="taxpayers">فایل مودیان</option>
    <option value="payments">فایل پرداخت‌ها</option>
  </select>
  <label for="file">فایل اکسل (.xlsx)</label>
  <input id="file" name="file" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required>
  <button type="submit">بارگذاری و وارد کردن</button>
</form>""",
    )


@app.post("/upload", response_class=HTMLResponse)
async def upload_excel(
    snapshot_date: Annotated[str, Form()],
    region: Annotated[str, Form()],
    file_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> HTMLResponse:
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(status_code=400, detail="فقط فایل‌های .xlsx پذیرفته می‌شوند")

    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    destination = IMPORT_DIR / filename
    content = await file.read()
    destination.write_bytes(content)

    uploader = "admin"
    selected_region = region.strip()
    selected_file_type = file_type.strip()
    selected_snapshot_date = snapshot_date.strip()

    errors: list[str] = []
    status = "موفق"
    total_rows = inserted = updated = skipped = 0
    try:
        result = import_excel(
            destination,
            selected_snapshot_date,
            selected_region,
            make_engine(),
            file_type=selected_file_type,
            uploaded_by=uploader,
            source_file_name=filename,
        )
        total_rows = getattr(result, "total_rows", result.rows_imported)
        inserted = result.inserted_taxpayers
        updated = result.updated_taxpayers
        skipped = result.skipped_duplicates
        if getattr(result, "row_errors", 0):
            invalid_rows = getattr(result, "invalid_rows", ())
            row_numbers = "، ".join(str(row) for row in invalid_rows)
            errors.append(
                f"ردیف‌های دارای شناسه نامعتبر: {result.row_errors}"
                + (f" — ردیف‌های اکسل: {row_numbers}" if row_numbers else "")
            )
    except Exception as exc:
        status = "ناموفق"
        logger.exception(
            "Excel upload import failed: filename=%s snapshot_date=%s region=%s file_type=%s",
            filename,
            selected_snapshot_date,
            selected_region,
            selected_file_type,
        )
        errors.append(str(exc))

    error_items = "".join(f"<li>{html.escape(error)}</li>" for error in errors) or "<li>ندارد</li>"
    return _page(
        "نتیجه وارد کردن فایل",
        f"""
<h1>نتیجه وارد کردن فایل</h1>
<section class="card">
  <p><strong>بارگذار:</strong> {html.escape(uploader)}</p>
  <p><strong>منطقه:</strong> {html.escape(selected_region)}</p>
  <p><strong>نوع فایل:</strong> {html.escape(selected_file_type)}</p>
  <p><strong>تاریخ فایل:</strong> {html.escape(selected_snapshot_date)}</p>
  <p><strong>نام فایل:</strong> {html.escape(filename)}</p>
  <p><strong>وضعیت وارد کردن:</strong> {html.escape(status)}</p>
  <p><strong>تعداد کل ردیف‌ها:</strong> {total_rows}</p>
  <p><strong>مودیان اضافه‌شده:</strong> {inserted}</p>
  <p><strong>مودیان به‌روزرسانی‌شده:</strong> {updated}</p>
  <p><strong>موارد تکراری ردشده:</strong> {skipped}</p>
  <p><strong>خطاها:</strong></p>
  <ul class="{'error' if errors else ''}">{error_items}</ul>
</section>
<p><a href="/upload">بازگشت به صفحه بارگذاری</a></p>""",
        status_code=200 if status == "موفق" else 500,
    )


def _money(value: object) -> str:
    return f"{int(value or 0):,}"


def _dashboard_filters(region: str | None, snapshot_date: str | None, file_type: str | None) -> tuple[str, dict[str, str]]:
    clauses = []
    params = {}
    if region:
        clauses.append("s.region = :region")
        params["region"] = region
    if snapshot_date:
        clauses.append("s.snapshot_date = :snapshot_date")
        params["snapshot_date"] = snapshot_date
    if file_type:
        clauses.append("r.file_type = :file_type")
        params["file_type"] = file_type
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _query_rows(sql: str, params: dict | None = None) -> list[dict]:
    engine = make_engine()
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(sql), params or {})]


def _v1_jalali_parts(value: object) -> tuple[int, int, int] | None:
    normalized = str(value or "").translate(
        str.maketrans(
            "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
            "01234567890123456789",
        )
    )
    match = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", normalized)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return year, month, day

def _v1_jalali_ordinal(parts: tuple[int, int, int]) -> int:
    year, month, day = parts
    days_before_month = (
        (month - 1) * 31
        if month <= 7
        else 186 + (month - 7) * 30
    )
    return year * 365 + year // 4 + days_before_month + day

def _v1_number(name: str, default: Decimal = Decimal(0)) -> Decimal:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return Decimal(raw)
    except (ValueError, ArithmeticError):
        logger.warning("%s must contain a valid number", name)
        return default

def _v1_latest_snapshots(
    scope_name: str | None = None,
    report_date: str | None = None,
    region: str | None = None,
    district: str | None = None,
) -> list[dict]:
    clauses = ["status = 'completed'"]
    params: dict[str, object] = {}

    if report_date:
        clauses.append("snapshot_date <= :report_date")
        params["report_date"] = report_date

    rows = _query_rows(
        f"""
        SELECT id,
               snapshot_date AS report_date,
               region AS scope_name,
               imported_at AS uploaded_at,
               rows_imported AS imported_row_count,
               file_type,
               uploaded_by,
               source_file_name
        FROM import_runs
        WHERE {' AND '.join(clauses)}
        ORDER BY snapshot_date DESC,
                 imported_at DESC,
                 id DESC
        """,
        params,
    )

    latest_by_region: dict[str, dict] = {}
    for row in rows:
        region_name = str(row.get("scope_name") or "").strip()
        if not region_name:
            continue
        latest_by_region.setdefault(region_name, row)

    selected = list(latest_by_region.values())

    if scope_name:
        selected = [
            row
            for row in selected
            if str(row.get("scope_name") or "") == scope_name
        ]
    else:
        if region:
            selected = [
                row
                for row in selected
                if str(row.get("scope_name") or "") == region
                or str(row.get("scope_name") or "").startswith(
                    f"{region} -"
                )
            ]

        if district:
            selected = [
                row
                for row in selected
                if district in str(row.get("scope_name") or "")
            ]

    return selected


def _v1_records_for_snapshots(
    import_run_ids: list[int],
) -> list[dict]:
    if not import_run_ids:
        return []

    placeholders: list[str] = []
    params: dict[str, object] = {}

    for index, import_run_id in enumerate(import_run_ids):
        key = f"import_run_id_{index}"
        placeholders.append(f":{key}")
        params[key] = import_run_id

    return _query_rows(
        f"""
        SELECT id,
               import_run_id AS snapshot_id,
               identification_code,
               case_number,
               operator_name,
               job AS business_type,
               phone,
               address,
               payment_date,
               bill_amount,
               outstanding_debt AS overdue_debt,
               business_tax,
               passage_tax AS passage_fee,
               sidewalk_use_tax AS passage_usage_fee,
               signboard_tax AS signboard_fee,
               waste_fee,
               created_at
        FROM daily_snapshots
        WHERE import_run_id IN ({', '.join(placeholders)})
        ORDER BY import_run_id,
                 id
        """,
        params,
    )


def _v1_sum(rows: list[dict], field: str) -> Decimal:
    return sum(
        (Decimal(str(row.get(field) or 0)) for row in rows),
        Decimal(0),
    )

def _v1_record_metrics(rows: list[dict]) -> dict:
    case_numbers = [
        str(row["case_number"])
        for row in rows
        if str(row.get("case_number") or "").strip()
    ]

    case_counts: dict[str, int] = {}
    for case_number in case_numbers:
        case_counts[case_number] = (
            case_counts.get(case_number, 0) + 1
        )

    paid_rows = [
        row
        for row in rows
        if str(row.get("payment_date") or "").strip()
    ]
    unpaid_rows = [
        row
        for row in rows
        if not str(row.get("payment_date") or "").strip()
    ]

    return {
        "imported_rows": len(rows),
        "unique_case_count": len(set(case_numbers)),
        "duplicate_case_number_count": sum(
            1
            for count in case_counts.values()
            if count > 1
        ),
        "issued_bill_count": sum(
            1
            for row in rows
            if Decimal(str(row.get("bill_amount") or 0)) != 0
        ),
        "issued_bill_amount": _v1_sum(
            rows,
            "bill_amount",
        ),
        "paid_bill_count": len(paid_rows),
        "paid_bill_amount": _v1_sum(
            paid_rows,
            "bill_amount",
        ),
        "unpaid_bill_count": len(unpaid_rows),
        "unpaid_bill_amount": _v1_sum(
            unpaid_rows,
            "bill_amount",
        ),
        "overdue_debt": _v1_sum(
            rows,
            "overdue_debt",
        ),
        "business_tax": _v1_sum(
            rows,
            "business_tax",
        ),
        "waste_fee": _v1_sum(
            rows,
            "waste_fee",
        ),
        "signboard_fee": _v1_sum(
            rows,
            "signboard_fee",
        ),
        "passage_fee": _v1_sum(
            rows,
            "passage_fee",
        ),
        "passage_usage_fee": _v1_sum(
            rows,
            "passage_usage_fee",
        ),
        "missing_phone_count": sum(
            1
            for row in rows
            if not str(row.get("phone") or "").strip()
        ),
    }


def _v1_management_metrics(
    rows: list[dict],
    snapshots: list[dict],
    base_metrics: dict,
) -> dict:
    daily_collection: dict[str, Decimal] = {}

    for row in rows:
        parts = _v1_jalali_parts(row.get("payment_date"))
        if parts is None:
            continue

        day_key = f"{parts[0]:04d}/{parts[1]:02d}/{parts[2]:02d}"
        daily_collection[day_key] = (
            daily_collection.get(day_key, Decimal(0))
            + Decimal(str(row.get("bill_amount") or 0))
        )

    latest_payment_date = (
        max(
            daily_collection,
            key=lambda value: _v1_jalali_ordinal(
                _v1_jalali_parts(value)
            ),
        )
        if daily_collection
        else None
    )

    latest_report_date = max(
        (str(snapshot["report_date"]) for snapshot in snapshots),
        default="",
    )
    reference_parts = _v1_jalali_parts(latest_report_date)

    if reference_parts is None and latest_payment_date:
        reference_parts = _v1_jalali_parts(latest_payment_date)

    current_month = (
        f"{reference_parts[0]:04d}/{reference_parts[1]:02d}"
        if reference_parts
        else None
    )
    reference_ordinal = (
        _v1_jalali_ordinal(reference_parts)
        if reference_parts
        else None
    )

    monthly_collection = sum(
        (
            amount
            for day, amount in daily_collection.items()
            if current_month and day.startswith(current_month)
        ),
        Decimal(0),
    )

    weekly_collection = sum(
        (
            amount
            for day, amount in daily_collection.items()
            if reference_ordinal is not None
            and 0
            <= reference_ordinal
            - _v1_jalali_ordinal(_v1_jalali_parts(day))
            <= 6
        ),
        Decimal(0),
    )

    monthly_trend: dict[str, Decimal] = {}
    weekly_trend: dict[str, Decimal] = {}

    for day, amount in daily_collection.items():
        parts = _v1_jalali_parts(day)
        month_key = day[:7]
        week_key = (
            f"{parts[0]}-هفته-"
            f"{(_v1_jalali_ordinal(parts) % 366) // 7 + 1}"
        )
        monthly_trend[month_key] = (
            monthly_trend.get(month_key, Decimal(0)) + amount
        )
        weekly_trend[week_key] = (
            weekly_trend.get(week_key, Decimal(0)) + amount
        )

    monthly_target = _v1_number("DASHBOARD_MONTHLY_TARGET")
    contractor_rate = _v1_number("DASHBOARD_CONTRACTOR_FEE_RATE")
    project_costs = _v1_number("DASHBOARD_PROJECT_COSTS_TO_DATE")
    daily_project_cost = _v1_number("DASHBOARD_DAILY_PROJECT_COST")

    days_in_month = (
        31
        if reference_parts and reference_parts[1] <= 6
        else 30
    )
    expected_collection = (
        monthly_target
        * Decimal(reference_parts[2])
        / Decimal(days_in_month)
        if reference_parts
        else Decimal(0)
    )
    achievement = (
        monthly_collection * Decimal(100) / monthly_target
        if monthly_target
        else Decimal(0)
    )
    target_difference = monthly_collection - monthly_target
    achievement_factor = (
        min(achievement, Decimal(100)) / Decimal(100)
        if achievement > 0
        else Decimal(0)
    )

    thresholds_raw = os.environ.get(
        "DASHBOARD_DEBT_THRESHOLDS",
        "10000000,50000000,100000000",
    )
    thresholds: list[Decimal] = []

    for raw_threshold in thresholds_raw.split(","):
        raw_threshold = raw_threshold.strip()
        if not raw_threshold:
            continue
        try:
            thresholds.append(Decimal(raw_threshold))
        except (ValueError, ArithmeticError):
            logger.warning(
                "Ignoring invalid dashboard debt threshold: %s",
                raw_threshold,
            )

    return {
        **base_metrics,
        "total_collection": base_metrics["paid_bill_amount"],
        "monthly_collection": monthly_collection,
        "weekly_collection": weekly_collection,
        "latest_day_collection": (
            daily_collection.get(latest_payment_date, Decimal(0))
            if latest_payment_date
            else Decimal(0)
        ),
        "latest_payment_date": latest_payment_date,
        "monthly_target": monthly_target,
        "expected_collection_to_date": expected_collection,
        "achievement_percentage": achievement,
        "remaining_to_target": max(
            -target_difference,
            Decimal(0),
        ),
        "surplus_or_deficit": target_difference,
        "monthly_contractor_fee": (
            monthly_collection
            * contractor_rate
            / Decimal(100)
            * achievement_factor
        ),
        "project_costs_to_date": project_costs,
        "daily_project_cost": daily_project_cost,
        "profit_or_loss": (
            base_metrics["paid_bill_amount"] - project_costs
        ),
        "debtors_above_thresholds": [
            {
                "threshold": threshold,
                "count": sum(
                    1
                    for row in rows
                    if Decimal(str(row.get("overdue_debt") or 0))
                    >= threshold
                ),
            }
            for threshold in sorted(thresholds)
        ],
        "daily_trend": [
            {
                "period": key,
                "amount": daily_collection[key],
            }
            for key in sorted(
                daily_collection,
                key=lambda value: _v1_jalali_ordinal(
                    _v1_jalali_parts(value)
                ),
            )
        ],
        "weekly_trend": [
            {"period": key, "amount": value}
            for key, value in sorted(weekly_trend.items())
        ],
        "monthly_trend": [
            {"period": key, "amount": value}
            for key, value in sorted(monthly_trend.items())
        ],
    }

def _v1_dashboard_data(
    scope_name: str | None = None,
    report_date: str | None = None,
    region: str | None = None,
    district: str | None = None,
) -> dict:
    snapshots = _v1_latest_snapshots(
        scope_name=scope_name,
        report_date=report_date,
        region=region,
        district=district,
    )

    import_run_ids = [
        int(snapshot["id"])
        for snapshot in snapshots
    ]
    rows = _v1_records_for_snapshots(import_run_ids)

    rows_by_import_run: dict[int, list[dict]] = {
        import_run_id: []
        for import_run_id in import_run_ids
    }
    for row in rows:
        import_run_id = int(row["snapshot_id"])
        rows_by_import_run.setdefault(
            import_run_id,
            [],
        ).append(row)

    import_metrics = [
        _v1_record_metrics(
            rows_by_import_run[import_run_id]
        )
        for import_run_id in import_run_ids
    ]

    if import_metrics:
        metric_keys = import_metrics[0].keys()
        base_metrics = {
            key: sum(
                (
                    item[key]
                    for item in import_metrics
                ),
                (
                    Decimal(0)
                    if isinstance(
                        import_metrics[0][key],
                        Decimal,
                    )
                    else 0
                ),
            )
            for key in metric_keys
        }
    else:
        base_metrics = _v1_record_metrics([])

    base_metrics["import_warning_count"] = 0

    management_metrics = _v1_management_metrics(
        rows,
        snapshots,
        base_metrics,
    )

    scope_summaries = []
    for snapshot in snapshots:
        import_run_id = int(snapshot["id"])
        item_metrics = _v1_record_metrics(
            rows_by_import_run.get(
                import_run_id,
                [],
            )
        )
        scope_summaries.append(
            {
                "scope_name": snapshot["scope_name"],
                "report_date": snapshot["report_date"],
                "uploaded_at": snapshot["uploaded_at"],
                "imported_row_count": snapshot.get(
                    "imported_row_count",
                    0,
                ),
                "issued_amount": item_metrics[
                    "issued_bill_amount"
                ],
                "paid_amount": item_metrics[
                    "paid_bill_amount"
                ],
                "overdue_debt": item_metrics[
                    "overdue_debt"
                ],
            }
        )

    latest_catalog = _v1_latest_snapshots(
        report_date=report_date,
    )

    newest_report_date = max(
        (
            str(snapshot["report_date"])
            for snapshot in latest_catalog
        ),
        default=None,
    )

    freshness = [
        {
            "scope_name": snapshot["scope_name"],
            "report_date": snapshot["report_date"],
            "uploaded_at": snapshot["uploaded_at"],
            "status": (
                "up_to_date"
                if str(snapshot["report_date"])
                == newest_report_date
                else "stale"
            ),
        }
        for snapshot in latest_catalog
    ]

    top_debtors = sorted(
        (
            {
                "case_number": row.get(
                    "case_number"
                ),
                "operator_name": row.get(
                    "operator_name"
                ),
                "phone": row.get("phone"),
                "overdue_debt": (
                    row.get("overdue_debt") or 0
                ),
            }
            for row in rows
            if Decimal(
                str(row.get("overdue_debt") or 0)
            )
            > 0
        ),
        key=lambda item: Decimal(
            str(item["overdue_debt"])
        ),
        reverse=True,
    )[:20]

    return {
        "scope_name": scope_name,
        "as_of_report_date": report_date,
        "report_date": max(
            (
                str(snapshot["report_date"])
                for snapshot in snapshots
            ),
            default=None,
        ),
        "uploaded_at": max(
            (
                snapshot["uploaded_at"]
                for snapshot in snapshots
            ),
            default=None,
        ),
        "metrics": management_metrics,
        "snapshots": snapshots,
        "scope_summaries": scope_summaries,
        "freshness": freshness,
        "available_scopes": [
            str(snapshot["scope_name"])
            for snapshot in latest_catalog
        ],
        "top_debtors": top_debtors,
    }


def _v1_trend_chart(items: list[dict]) -> str:
    maximum = max(
        (
            Decimal(str(item["amount"]))
            for item in items
        ),
        default=Decimal(0),
    )

    if not items:
        return (
            '<section class="card">'
            "برای این دوره داده وصول ثبت نشده است."
            "</section>"
        )

    bars = []
    for item in items[-12:]:
        amount = Decimal(str(item["amount"]))
        height = (
            max(int(amount * Decimal(100) / maximum), 2)
            if maximum
            else 2
        )
        bars.append(
            '<div style="display:grid;'
            'grid-template-rows:1fr auto auto;'
            'align-items:end;min-width:4.5rem;'
            'height:11rem;text-align:center">'
            f'<div style="height:{height}%;'
            'background:linear-gradient(#155eef,#84adff);'
            'border-radius:.35rem .35rem 0 0;'
            'min-height:.25rem"></div>'
            f'<small>{html.escape(str(item["period"]))}</small>'
            f'<small>{_money(amount)}</small>'
            "</div>"
        )

    return (
        '<div style="display:flex;align-items:end;'
        'gap:.65rem;min-height:13rem;padding:1rem;'
        'background:white;border-radius:.75rem;'
        'overflow-x:auto">'
        + "".join(bars)
        + "</div>"
    )

@app.get("/api/dashboard", tags=["dashboard"])
def dashboard_api(
    scope_name: str | None = None,
    report_date: str | None = None,
    region: str | None = None,
    district: str | None = None,
) -> dict:
    return _v1_dashboard_data(
        scope_name=scope_name,
        report_date=report_date,
        region=region,
        district=district,
    )

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    region: str | None = None,
    snapshot_date: str | None = None,
    file_type: str | None = None,
    scope_name: str | None = None,
    report_date: str | None = None,
    district: str | None = None,
) -> HTMLResponse:
    del snapshot_date, file_type

    data = _v1_dashboard_data(
        scope_name=scope_name,
        report_date=report_date,
        region=region,
        district=district,
    )
    metrics = data["metrics"]

    cards = [
        ("کل وصولی", metrics["total_collection"], True),
        ("وصولی ماهانه", metrics["monthly_collection"], True),
        ("وصولی هفتگی", metrics["weekly_collection"], True),
        (
            "وصولی امروز / آخرین روز",
            metrics["latest_day_collection"],
            True,
        ),
        ("هدف ماهانه", metrics["monthly_target"], True),
        (
            "وصول مورد انتظار تا امروز",
            metrics["expected_collection_to_date"],
            True,
        ),
        (
            "درصد تحقق هدف",
            f'{metrics["achievement_percentage"]:.1f}٪',
            False,
        ),
        ("مانده تا هدف", metrics["remaining_to_target"], True),
        ("مازاد یا کسری", metrics["surplus_or_deficit"], True),
        (
            "حق‌الزحمه ماهانه پیمانکار",
            metrics["monthly_contractor_fee"],
            True,
        ),
        (
            "هزینه پروژه تا امروز",
            metrics["project_costs_to_date"],
            True,
        ),
        (
            "هزینه روزانه پروژه",
            metrics["daily_project_cost"],
            True,
        ),
        ("سود یا زیان", metrics["profit_or_loss"], True),
        (
            "تعداد فیش‌های صادره",
            metrics["issued_bill_count"],
            False,
        ),
        (
            "مبلغ فیش‌های صادره",
            metrics["issued_bill_amount"],
            True,
        ),
        (
            "تعداد فیش‌های پرداخت‌شده",
            metrics["paid_bill_count"],
            False,
        ),
        (
            "مبلغ فیش‌های پرداخت‌شده",
            metrics["paid_bill_amount"],
            True,
        ),
        (
            "تعداد فیش‌های پرداخت‌نشده",
            metrics["unpaid_bill_count"],
            False,
        ),
        (
            "مبلغ فیش‌های پرداخت‌نشده",
            metrics["unpaid_bill_amount"],
            True,
        ),
        ("بدهی معوقه", metrics["overdue_debt"], True),
    ]

    card_html = "".join(
        '<section class="card">'
        f"<strong>{html.escape(label)}</strong>"
        f"<b>{_money(value) if monetary else value}</b>"
        "</section>"
        for label, value, monetary in cards
    )

    options = ['<option value="">همه محدوده‌ها</option>']
    for available_scope in data["available_scopes"]:
        selected = (
            " selected"
            if available_scope == scope_name
            else ""
        )
        options.append(
            f'<option value="{html.escape(available_scope)}"'
            f"{selected}>"
            f"{html.escape(available_scope)}"
            "</option>"
        )

    scope_rows = "".join(
        "<tr>"
        f'<td>{html.escape(str(item["scope_name"]))}</td>'
        f'<td>{html.escape(str(item["report_date"]))}</td>'
        f'<td>{_money(item["issued_amount"])}</td>'
        f'<td>{_money(item["paid_amount"])}</td>'
        f'<td>{_money(item["overdue_debt"])}</td>'
        "</tr>"
        for item in data["scope_summaries"]
    )

    threshold_rows = "".join(
        "<tr>"
        f'<td>{_money(item["threshold"])}</td>'
        f'<td>{item["count"]}</td>'
        "</tr>"
        for item in metrics["debtors_above_thresholds"]
    )
    if not threshold_rows:
        threshold_rows = (
            '<tr><td colspan="2">'
            "آستانه‌ای تنظیم نشده است."
            "</td></tr>"
        )

    debtor_rows = "".join(
        "<tr>"
        f'<td>{html.escape(str(item["case_number"] or ""))}</td>'
        f'<td>{html.escape(str(item["operator_name"] or ""))}</td>'
        f'<td>{html.escape(str(item["phone"] or ""))}</td>'
        f'<td>{_money(item["overdue_debt"])}</td>'
        "</tr>"
        for item in data["top_debtors"]
    )

    status_labels = {
        "up_to_date": "به‌روز",
        "stale": "قدیمی",
        "missing": "فاقد گزارش",
    }
    freshness_rows = "".join(
        "<tr>"
        f'<td>{html.escape(str(item["scope_name"]))}</td>'
        f'<td>{html.escape(str(item["report_date"] or "-"))}</td>'
        f'<td>{html.escape(str(item["uploaded_at"] or "-"))}</td>'
        f'<td>{status_labels.get(item["status"], item["status"])}</td>'
        "</tr>"
        for item in data["freshness"]
    )

    body = f"""
<h1>داشبورد مدیریت شهرداری</h1>
<form class="filters" method="get">
  <label>محدوده
    <select name="scope_name">{''.join(options)}</select>
  </label>
  <label>منطقه
    <input name="region"
           value="{html.escape(region or '')}"
           placeholder="منطقه ۳">
  </label>
  <label>ناحیه
    <input name="district"
           value="{html.escape(district or '')}"
           placeholder="ناحیه ۲">
  </label>
  <label>تاریخ گزارش تا
    <input name="report_date"
           value="{html.escape(report_date or '')}"
           placeholder="۱۴۰۵/۰۵/۰۱">
  </label>
  <button>اعمال فیلتر</button>
</form>

<div class="grid">{card_html}</div>

<h2>روند وصول دوره‌ای</h2>
{_v1_trend_chart(metrics["monthly_trend"])}

<h2>روند وصول هفتگی</h2>
{_v1_trend_chart(metrics["weekly_trend"])}

<h2>روند وصول روزانه</h2>
{_v1_trend_chart(metrics["daily_trend"])}

<h2>عملکرد مناطق و نواحی</h2>
<table>
  <tr>
    <th>محدوده</th>
    <th>تاریخ گزارش</th>
    <th>مبلغ صادره</th>
    <th>مبلغ وصول‌شده</th>
    <th>بدهی معوقه</th>
  </tr>
  {scope_rows}
</table>

<h2>بدهکاران بالاتر از آستانه</h2>
<table>
  <tr>
    <th>آستانه بدهی</th>
    <th>تعداد بدهکار</th>
  </tr>
  {threshold_rows}
</table>

<h2>۲۰ بدهکار برتر</h2>
<table>
  <tr>
    <th>پرونده</th>
    <th>نام</th>
    <th>تلفن</th>
    <th>بدهی</th>
  </tr>
  {debtor_rows}
</table>

<h2>آخرین به‌روزرسانی مناطق</h2>
<table>
  <tr>
    <th>محدوده</th>
    <th>آخرین تاریخ گزارش</th>
    <th>آخرین زمان بارگذاری</th>
    <th>وضعیت</th>
  </tr>
  {freshness_rows}
</table>

<p>
  <a href="/taxpayers">جستجوی مودیان</a>
  |
  <a href="/upload">بارگذاری گزارش</a>
</p>
"""
    return _page("داشبورد مدیریت شهرداری", body)

@app.get("/taxpayers", response_class=HTMLResponse)
def taxpayers_page(q: str | None = None, region: str | None = None, snapshot_date: str | None = None, file_type: str | None = None) -> HTMLResponse:
    where, params = _dashboard_filters(region, snapshot_date, file_type)
    clauses = [where[7:]] if where else []
    if q:
        clauses.append("(s.operator_name LIKE :q OR s.phone LIKE :q OR s.identification_code LIKE :q OR s.case_number LIKE :q OR s.address LIKE :q)")
        params["q"] = f"%{q}%"
    sql_where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = _query_rows(f"""
        SELECT s.identification_code, s.case_number, s.operator_name, s.phone, s.address, s.region, s.snapshot_date, s.outstanding_debt
        FROM daily_snapshots s JOIN import_runs r ON r.id = s.import_run_id {sql_where}
        ORDER BY s.snapshot_date DESC, s.outstanding_debt DESC LIMIT 100
    """, params)
    body = f"""<h1>جستجوی مودیان</h1><form class="filters"><input name="q" placeholder="نام، تلفن، کد، پرونده یا نشانی" value="{html.escape(q or '')}"><input name="region" placeholder="منطقه" value="{html.escape(region or '')}"><input name="snapshot_date" placeholder="تاریخ" value="{html.escape(snapshot_date or '')}"><input name="file_type" placeholder="نوع فایل" value="{html.escape(file_type or '')}"><button>جستجو</button></form><table><tr><th>کد</th><th>پرونده</th><th>نام</th><th>تلفن</th><th>نشانی</th><th>منطقه</th><th>تاریخ</th><th>بدهی</th></tr>{''.join(f'<tr><td><a href="/taxpayers/{quote(str(r["identification_code"]))}">{html.escape(str(r["identification_code"]))}</a></td><td>{html.escape(str(r.get("case_number") or ""))}</td><td>{html.escape(str(r.get("operator_name") or ""))}</td><td>{html.escape(str(r.get("phone") or ""))}</td><td>{html.escape(str(r.get("address") or ""))}</td><td>{html.escape(str(r["region"]))}</td><td>{html.escape(str(r["snapshot_date"]))}</td><td>{_money(r["outstanding_debt"])}</td></tr>' for r in rows)}</table>"""
    return _page("جستجوی مودیان", body)


@app.get("/taxpayers/{taxpayer_id}", response_class=HTMLResponse)
def taxpayer_detail(taxpayer_id: str) -> HTMLResponse:
    rows = _query_rows("""
        SELECT identification_code, case_number, operator_name, job, phone, address, region, snapshot_date, bill_amount, outstanding_debt, business_tax
        FROM daily_snapshots WHERE identification_code = :id ORDER BY snapshot_date DESC, region
    """, {"id": taxpayer_id})
    if not rows:
        raise HTTPException(status_code=404, detail="مودی پیدا نشد")
    first = rows[0]
    body = f"<h1>{html.escape(str(first.get('operator_name') or taxpayer_id))}</h1><p>کد شناسایی: {html.escape(taxpayer_id)}</p><p>تلفن: {html.escape(str(first.get('phone') or ''))}</p><p>نشانی: {html.escape(str(first.get('address') or ''))}</p><h2>سوابق snapshot</h2><table><tr><th>تاریخ</th><th>منطقه</th><th>فیش</th><th>بدهی</th><th>عوارض کسب</th></tr>" + ''.join(f'<tr><td>{html.escape(str(r["snapshot_date"]))}</td><td>{html.escape(str(r["region"]))}</td><td>{_money(r["bill_amount"])}</td><td>{_money(r["outstanding_debt"])}</td><td>{_money(r["business_tax"])}</td></tr>' for r in rows) + "</table>"
    return _page("جزئیات مودی", body)
