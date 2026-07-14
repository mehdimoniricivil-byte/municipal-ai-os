import asyncio
from pathlib import Path

from fastapi import HTTPException, UploadFile

from shahrdari_ai import upload_app


def test_upload_form_contains_persian_upload_fields():
    response = upload_app.upload_form()
    text = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "بارگذاری فایل اکسل شهرداری" in text
    assert 'name="username"' in text
    assert 'name="password"' in text
    assert 'name="region"' in text
    assert 'name="file_type"' in text
    assert 'name="snapshot_date"' in text
    assert 'name="file"' in text


def test_upload_rejects_non_xlsx(monkeypatch):
    monkeypatch.setenv("UPLOAD_USERNAME", "uploader")
    monkeypatch.setenv("UPLOAD_PASSWORD", "secret")
    file = UploadFile(filename="sample.csv", file=__import__("io").BytesIO(b"x"))

    try:
        asyncio.run(upload_app.upload_excel("uploader", "secret", "1405-04-17", "منطقه یک", "snapshot", file))
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("CSV upload should be rejected")


def test_upload_saves_xlsx_and_returns_import_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_USERNAME", "uploader")
    monkeypatch.setenv("UPLOAD_PASSWORD", "secret")
    monkeypatch.setattr(upload_app, "IMPORT_DIR", tmp_path / "imports")

    class Result:
        rows_imported = 2
        inserted_taxpayers = 1
        updated_taxpayers = 1
        skipped_duplicates = 0

    def fake_import_excel(path, snapshot_date, region, engine, **kwargs):
        assert Path(path).read_bytes() == b"xlsx"
        assert snapshot_date == "1405-04-17"
        assert region == "منطقه یک"
        assert kwargs["file_type"] == "snapshot"
        assert kwargs["uploaded_by"] == "uploader"
        assert kwargs["source_file_name"] == "sample.xlsx"
        return Result()

    monkeypatch.setattr(upload_app, "make_engine", lambda: object())
    monkeypatch.setattr(upload_app, "import_excel", fake_import_excel)
    file = UploadFile(filename="sample.xlsx", file=__import__("io").BytesIO(b"xlsx"))

    response = asyncio.run(upload_app.upload_excel("uploader", "secret", "1405-04-17", "منطقه یک", "snapshot", file))
    text = response.body.decode("utf-8")

    assert response.status_code == 200
    assert (tmp_path / "imports" / "sample.xlsx").exists()
    assert "موفق" in text
    assert "بارگذار:</strong> uploader" in text
    assert "منطقه:</strong> منطقه یک" in text
    assert "نوع فایل:</strong> snapshot" in text
    assert "تاریخ فایل:</strong> 1405-04-17" in text
    assert "مودیان اضافه‌شده:</strong> 1" in text
    assert "مودیان به‌روزرسانی‌شده:</strong> 1" in text
