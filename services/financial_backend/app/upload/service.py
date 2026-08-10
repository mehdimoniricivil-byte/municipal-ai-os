from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import CollectionRecord, CollectionUpload, MonthlyCollection, User
from app.upload.parser import WorkbookReadError, read_first_sheet
from app.upload.validator import validate_rows

UPLOAD_ROOT = Path(os.getenv("COLLECTION_UPLOAD_DIR", "uploads/collections"))
MAX_FILE_SIZE = int(os.getenv("COLLECTION_MAX_FILE_SIZE", str(20 * 1024 * 1024)))


def assert_region_access(user: User, region_id: int) -> None:
    if user.role == "expert" and user.region_id != region_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="کارشناس فقط مجاز به بارگذاری فایل واحد خودش است")


def save_and_validate_file(
    db: Session,
    file: UploadFile,
    region_id: int,
    year: int,
    month: int,
    user: User,
) -> tuple[CollectionUpload, dict]:
    assert_region_access(user, region_id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise HTTPException(status_code=422, detail="فقط فایل Excel با پسوند xlsx یا xls قابل قبول است")

    content = file.file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="حجم فایل بیشتر از ۲۰ مگابایت است")
    if not content:
        raise HTTPException(status_code=422, detail="فایل خالی است")

    file_hash = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(CollectionUpload).where(CollectionUpload.file_hash == file_hash))
    if existing is not None and (
        existing.region_id != region_id
        or existing.persian_year != year
        or existing.persian_month != month
    ):
        raise HTTPException(
            status_code=409,
            detail="همین فایل قبلاً برای واحد یا دوره دیگری ثبت شده است؛ واحد، سال و ماه را بررسی کنید",
        )

    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_ROOT / f"{uuid4().hex}{suffix}"
    stored_path.write_bytes(content)

    try:
        rows = read_first_sheet(stored_path)
        result = validate_rows(rows, selected_year=year, selected_month=month)
    except WorkbookReadError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # فایل‌های وصول ماهانه Snapshot تجمعی هستند. بنابراین وجود رکوردهای نسخه قبلی
    # در همان واحد/سال/ماه نباید اعتبارسنجی نسخه جدید را مسدود کند؛ نسخه جدید
    # هنگام ثبت نهایی به صورت اتمیک جایگزین Snapshot قبلی همان دوره می‌شود.
    summary = result.summary(include_records=True)

    if existing is None:
        upload = CollectionUpload(
            region_id=region_id,
            persian_year=year,
            persian_month=month,
            original_filename=Path(file.filename or "upload").name,
            stored_path=str(stored_path),
            file_hash=file_hash,
            status="validated" if result.can_import else "rejected",
            total_rows=result.total_rows,
            valid_rows=result.valid_rows,
            invalid_rows=result.invalid_rows,
            total_amount_irr=result.total_amount_irr,
            validation_result=json.dumps(summary, ensure_ascii=False),
            uploaded_by=user.id,
        )
        db.add(upload)
    else:
        # اگر دقیقاً همان فایل برای همین دوره دوباره انتخاب شد، همان شناسه را
        # دوباره وارد چرخه اعتبارسنجی می‌کنیم و قفل «قبلاً ثبت نهایی شده» نداریم.
        upload = existing
        upload.original_filename = Path(file.filename or "upload").name
        upload.stored_path = str(stored_path)
        upload.status = "validated" if result.can_import else "rejected"
        upload.total_rows = result.total_rows
        upload.valid_rows = result.valid_rows
        upload.invalid_rows = result.invalid_rows
        upload.total_amount_irr = result.total_amount_irr
        upload.validation_result = json.dumps(summary, ensure_ascii=False)
        upload.uploaded_by = user.id
        upload.uploaded_at = datetime.utcnow()
        upload.imported_at = None

    db.commit()
    db.refresh(upload)

    preview = dict(summary)
    preview["records"] = preview.get("records", [])[:20]
    preview["upload_id"] = upload.id
    preview["status"] = upload.status
    preview["filename"] = upload.original_filename
    return upload, preview


def import_validated_upload(db: Session, upload: CollectionUpload, user: User) -> dict:
    assert_region_access(user, upload.region_id)
    if upload.status != "validated":
        raise HTTPException(status_code=422, detail="فقط فایل بدون خطای اعتبارسنجی قابل ثبت نهایی است")

    validation = json.loads(upload.validation_result or "{}")
    records = validation.get("records", [])
    if not records:
        raise HTTPException(status_code=422, detail="رکورد معتبری برای ثبت وجود ندارد")

    try:
        # ثبت هر فایل برای یک واحد/ماه، Snapshot قبلی همان دوره را جایگزین می‌کند.
        # به این ترتیب آپلود مجدد باعث دوبرابر شدن وصول یا تکرار رکوردها نمی‌شود.
        db.execute(
            delete(CollectionRecord).where(
                CollectionRecord.region_id == upload.region_id,
                CollectionRecord.persian_year == upload.persian_year,
                CollectionRecord.persian_month == upload.persian_month,
            )
        )
        db.flush()

        for record in records:
            db.add(CollectionRecord(
                upload_id=upload.id,
                region_id=upload.region_id,
                persian_year=record["persian_year"],
                persian_month=record["persian_month"],
                payment_date_persian=record["payment_date_persian"],
                receipt_number=record.get("receipt_number"),
                payer_name=record.get("payer_name"),
                phone=record.get("phone"),
                business_title=record.get("business_title"),
                address=record.get("address"),
                amount_irr=Decimal(str(record["amount_irr"])),
                source_row_number=record["source_row_number"],
                source_row_hash=record["source_row_hash"],
                raw_data=json.dumps(record.get("raw_data", {}), ensure_ascii=False),
            ))
        db.flush()

        aggregate = db.execute(
            select(
                func.coalesce(func.sum(CollectionRecord.amount_irr), 0),
                func.max(CollectionRecord.payment_date_persian),
            ).where(
                CollectionRecord.region_id == upload.region_id,
                CollectionRecord.persian_year == upload.persian_year,
                CollectionRecord.persian_month == upload.persian_month,
            )
        ).one()
        total_amount, as_of_date = aggregate
        monthly = db.scalar(select(MonthlyCollection).where(
            MonthlyCollection.region_id == upload.region_id,
            MonthlyCollection.persian_year == upload.persian_year,
            MonthlyCollection.persian_month == upload.persian_month,
        ))
        if monthly is None:
            monthly = MonthlyCollection(
                region_id=upload.region_id,
                persian_year=upload.persian_year,
                persian_month=upload.persian_month,
                amount_irr=total_amount,
                as_of_persian_date=as_of_date or f"{upload.persian_year:04d}/{upload.persian_month:02d}/01",
                source_import_id=upload.id,
            )
            db.add(monthly)
        else:
            monthly.amount_irr = total_amount
            monthly.as_of_persian_date = as_of_date or monthly.as_of_persian_date
            monthly.source_import_id = upload.id

        upload.status = "imported"
        upload.imported_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "upload_id": upload.id,
        "status": upload.status,
        "imported_rows": len(records),
        "total_amount_irr": int(upload.total_amount_irr),
    }
