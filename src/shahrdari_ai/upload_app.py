from __future__ import annotations

import html
import logging
import os
import secrets
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from .etl.engine import import_excel, make_engine

IMPORT_DIR = Path("data/imports")

logger = logging.getLogger(__name__)

app = FastAPI(title="Municipality Excel Upload")


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
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; line-height: 1.8; }}
    main {{ max-width: 42rem; margin: auto; }}
    label {{ display: block; margin-top: 1rem; font-weight: 700; }}
    input, select, button {{ box-sizing: border-box; font: inherit; width: 100%; padding: .7rem; margin-top: .25rem; }}
    button {{ background: #155eef; color: white; border: 0; border-radius: .4rem; margin-top: 1.25rem; }}
    .card {{ border: 1px solid #ddd; border-radius: .75rem; padding: 1rem; }}
    .error {{ color: #b42318; }}
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
        result = import_excel(destination, selected_snapshot_date, selected_region, make_engine())
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
