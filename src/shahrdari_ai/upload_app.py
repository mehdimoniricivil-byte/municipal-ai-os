from __future__ import annotations

import html
import logging
import os
import secrets
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from sqlalchemy import text

from .auth import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserRead,
    authenticate_user,
    create_user_record,
    get_current_user,
)
from .etl.engine import import_excel, make_engine

IMPORT_DIR = Path("data/imports")

logger = logging.getLogger(__name__)

app = FastAPI(title="Municipality Excel Upload")


@app.post("/api/users", response_model=UserRead, status_code=201, tags=["users"])
def create_user(payload: UserCreate) -> UserRead:
    return create_user_record(payload)


@app.post("/api/auth/login", response_model=TokenResponse, tags=["auth"])
def login_user(payload: UserLogin) -> TokenResponse:
    return authenticate_user(payload)


@app.get("/api/users/me", response_model=UserRead, tags=["users"])
def read_current_user(current_user: UserRead = Depends(get_current_user)) -> UserRead:
    return current_user


def _login_is_valid(username: str | None, password: str | None) -> bool:
    expected_username = os.environ.get("UPLOAD_USERNAME")
    expected_password = os.environ.get("UPLOAD_PASSWORD")
    return (
        bool(expected_username)
        and bool(expected_password)
        and username is not None
        and password is not None
        and secrets.compare_digest(username, expected_username)
        and secrets.compare_digest(password, expected_password)
    )


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
  <label for="username">نام کاربری</label>
  <input id="username" name="username" type="text" autocomplete="username" required>
  <label for="password">رمز عبور</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
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
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    snapshot_date: Annotated[str, Form()],
    region: Annotated[str, Form()],
    file_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> HTMLResponse:
    if not _login_is_valid(username, password):
        raise HTTPException(status_code=401, detail="نام کاربری یا رمز عبور نادرست است")
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(status_code=400, detail="فقط فایل‌های .xlsx پذیرفته می‌شوند")

    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    destination = IMPORT_DIR / filename
    content = await file.read()
    destination.write_bytes(content)

    uploader = username.strip()
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
            errors.append(f"ردیف‌های دارای شناسه نامعتبر: {result.row_errors}")
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


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(region: str | None = None, snapshot_date: str | None = None, file_type: str | None = None) -> HTMLResponse:
    where, params = _dashboard_filters(region, snapshot_date, file_type)
    kpi = _query_rows(f"""
        SELECT COUNT(DISTINCT s.identification_code) total_taxpayers,
               COALESCE(SUM(s.outstanding_debt),0) total_outstanding_debt,
               COALESCE(SUM(s.bill_amount),0) total_bill_amount,
               COALESCE(SUM(s.business_tax),0) total_business_tax,
               COALESCE(AVG(s.outstanding_debt),0) average_outstanding_debt,
               SUM(CASE WHEN s.outstanding_debt = 0 THEN 1 ELSE 0 END) zero_debt,
               SUM(CASE WHEN s.phone IS NULL OR TRIM(s.phone) = '' THEN 1 ELSE 0 END) missing_phone
        FROM daily_snapshots s JOIN import_runs r ON r.id = s.import_run_id {where}
    """, params)[0]
    by_region = _query_rows(f"""
        SELECT s.region, COUNT(DISTINCT s.identification_code) taxpayers,
               COALESCE(SUM(s.outstanding_debt),0) debt, COALESCE(SUM(s.bill_amount),0) bill
        FROM daily_snapshots s JOIN import_runs r ON r.id = s.import_run_id {where}
        GROUP BY s.region ORDER BY s.region
    """, params)
    top = _query_rows(f"""
        SELECT s.identification_code, s.case_number, s.operator_name, s.phone, s.region, s.outstanding_debt
        FROM daily_snapshots s JOIN import_runs r ON r.id = s.import_run_id {where}
        ORDER BY s.outstanding_debt DESC, s.identification_code LIMIT 20
    """, params)
    imports = _query_rows("""
        SELECT snapshot_date, region, file_type, uploaded_by, source_file_name, imported_at, rows_imported, status
        FROM import_runs ORDER BY imported_at DESC, id DESC LIMIT 20
    """)
    warnings = []
    if int(kpi.get("missing_phone") or 0):
        warnings.append(f"{kpi['missing_phone']} مودی شماره تماس ندارد.")
    if int(kpi.get("zero_debt") or 0):
        warnings.append(f"{kpi['zero_debt']} مودی بدهی صفر دارد.")
    if not imports:
        warnings.append("هنوز هیچ فایل واقعی وارد نشده است.")
    warning_items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings) or "<li>هشدار مهمی وجود ندارد.</li>"
    cards = [
        ("تعداد مودیان", kpi["total_taxpayers"]), ("کل بدهی معوقه", _money(kpi["total_outstanding_debt"])),
        ("کل مبلغ فیش", _money(kpi["total_bill_amount"])), ("کل عوارض کسب", _money(kpi["total_business_tax"])),
        ("میانگین بدهی", _money(kpi["average_outstanding_debt"])), ("بدهی صفر", kpi["zero_debt"]), ("بدون تلفن", kpi["missing_phone"]),
    ]
    body = f"""
<h1>داشبورد مدیریت شهرداری</h1>
<form class="filters"><input name="region" placeholder="منطقه" value="{html.escape(region or '')}"><input name="snapshot_date" placeholder="تاریخ snapshot" value="{html.escape(snapshot_date or '')}"><input name="file_type" placeholder="نوع فایل" value="{html.escape(file_type or '')}"><button>اعمال فیلتر</button></form>
<div class="grid">{''.join(f'<section class="card"><strong>{t}</strong><b>{v}</b></section>' for t,v in cards)}</div>
<h2>مقایسه مناطق</h2><table><tr><th>منطقه</th><th>مودیان</th><th>بدهی معوقه</th><th>مبلغ فیش</th></tr>{''.join(f'<tr><td>{html.escape(str(r["region"]))}</td><td>{r["taxpayers"]}</td><td>{_money(r["debt"])}</td><td>{_money(r["bill"])}</td></tr>' for r in by_region)}</table>
<h2>۲۰ بدهکار برتر</h2><table><tr><th>کد</th><th>پرونده</th><th>نام</th><th>تلفن</th><th>منطقه</th><th>بدهی</th></tr>{''.join(f'<tr><td><a href="/taxpayers/{quote(str(r["identification_code"]))}">{html.escape(str(r["identification_code"]))}</a></td><td>{html.escape(str(r.get("case_number") or ""))}</td><td>{html.escape(str(r.get("operator_name") or ""))}</td><td>{html.escape(str(r.get("phone") or ""))}</td><td>{html.escape(str(r.get("region") or ""))}</td><td>{_money(r["outstanding_debt"])}</td></tr>' for r in top)}</table>
<h2>آخرین واردسازی‌ها</h2><table><tr><th>تاریخ</th><th>منطقه</th><th>نوع</th><th>بارگذار</th><th>فایل</th><th>زمان</th><th>ردیف</th><th>وضعیت</th></tr>{''.join(f'<tr><td>{html.escape(str(r["snapshot_date"]))}</td><td>{html.escape(str(r["region"]))}</td><td>{html.escape(str(r["file_type"]))}</td><td>{html.escape(str(r["uploaded_by"]))}</td><td>{html.escape(str(r["source_file_name"]))}</td><td>{html.escape(str(r["imported_at"]))}</td><td>{r["rows_imported"]}</td><td>{html.escape(str(r["status"]))}</td></tr>' for r in imports)}</table>
<h2>هشدارهای کیفیت داده</h2><ul>{warning_items}</ul><p><a href="/taxpayers">جستجوی مودیان</a></p>"""
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
