from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.models import CollectionUpload, User
from app.db.session import get_db
from app.schemas.upload import UploadHistoryItem
from app.services.audit import write_audit_log
from app.upload.service import import_validated_upload, save_and_validate_file

router = APIRouter()


@router.post("/validate")
def validate_collection_file(
    request: Request,
    region_id: int = Form(..., ge=1),
    year: int = Form(..., ge=1300, le=1600),
    month: int = Form(..., ge=1, le=12),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("collection.upload")),
):
    upload, preview = save_and_validate_file(db, file, region_id, year, month, user)
    write_audit_log(
        db,
        user=user,
        module="collections",
        action="validate_upload",
        record_type="collection_upload",
        record_id=str(upload.id),
        new_value={"status": upload.status, "filename": upload.original_filename, "period": f"{year}/{month:02d}"},
        request=request,
    )
    db.commit()
    return preview


@router.post("/{upload_id}/import")
def confirm_collection_import(
    upload_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("collection.upload")),
):
    upload = db.get(CollectionUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="فایل بارگذاری‌شده پیدا نشد")
    result = import_validated_upload(db, upload, user)
    write_audit_log(
        db,
        user=user,
        module="collections",
        action="import_upload",
        record_type="collection_upload",
        record_id=str(upload.id),
        new_value=result,
        request=request,
    )
    db.commit()
    return result


@router.get("/history", response_model=list[UploadHistoryItem])
def upload_history(
    year: int | None = Query(default=None, ge=1300, le=1600),
    month: int | None = Query(default=None, ge=1, le=12),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("collection.upload_status")),
):
    query = select(CollectionUpload)
    if user.role == "expert":
        if user.region_id is None:
            return []
        query = query.where(CollectionUpload.region_id == user.region_id)
    if year is not None:
        query = query.where(CollectionUpload.persian_year == year)
    if month is not None:
        query = query.where(CollectionUpload.persian_month == month)
    return db.scalars(query.order_by(CollectionUpload.uploaded_at.desc()).offset(offset).limit(limit)).all()


@router.get("/{upload_id}")
def upload_detail(
    upload_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("collection.upload_status")),
):
    upload = db.get(CollectionUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="فایل بارگذاری‌شده پیدا نشد")
    if user.role == "expert" and user.region_id != upload.region_id:
        raise HTTPException(status_code=403, detail="دسترسی کافی ندارید")
    result = json.loads(upload.validation_result or "{}")
    result.pop("records", None)
    return {
        "id": upload.id,
        "filename": upload.original_filename,
        "region_id": upload.region_id,
        "year": upload.persian_year,
        "month": upload.persian_month,
        "status": upload.status,
        "validation": result,
    }
