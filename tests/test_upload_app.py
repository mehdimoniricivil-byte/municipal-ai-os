from pathlib import Path

from fastapi.testclient import TestClient

from shahrdari_ai import upload_app


def test_upload_form_contains_persian_upload_fields():
    client = TestClient(upload_app.app)

    response = client.get("/upload")

    assert response.status_code == 200
    assert "بارگذاری فایل اکسل شهرداری" in response.text
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text
    assert 'name="region"' in response.text
    assert 'name="file_type"' in response.text
    assert 'name="snapshot_date"' in response.text
    assert 'name="file"' in response.text


def test_upload_rejects_non_xlsx(monkeypatch):
    monkeypatch.setenv("UPLOAD_USERNAME", "uploader")
    monkeypatch.setenv("UPLOAD_PASSWORD", "secret")
    client = TestClient(upload_app.app)

    response = client.post(
        "/upload",
        data={"username": "uploader", "password": "secret", "snapshot_date": "1405-04-17", "region": "منطقه یک", "file_type": "snapshot"},
        files={"file": ("sample.csv", b"x", "text/csv")},
    )

    assert response.status_code == 400


def test_upload_saves_xlsx_and_returns_import_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_USERNAME", "uploader")
    monkeypatch.setenv("UPLOAD_PASSWORD", "secret")
    monkeypatch.setattr(upload_app, "IMPORT_DIR", tmp_path / "imports")

    class Result:
        rows_imported = 2
        inserted_taxpayers = 1
        updated_taxpayers = 1
        skipped_duplicates = 0

    def fake_import_excel(path, snapshot_date, region, engine):
        assert Path(path).read_bytes() == b"xlsx"
        assert snapshot_date == "1405-04-17"
        assert region == "منطقه یک"
        return Result()

    monkeypatch.setattr(upload_app, "make_engine", lambda: object())
    monkeypatch.setattr(upload_app, "import_excel", fake_import_excel)
    client = TestClient(upload_app.app)

    response = client.post(
        "/upload",
        data={"username": "uploader", "password": "secret", "snapshot_date": "1405-04-17", "region": "منطقه یک", "file_type": "snapshot"},
        files={"file": ("sample.xlsx", b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200
    assert (tmp_path / "imports" / "sample.xlsx").exists()
    assert "موفق" in response.text
    assert "بارگذار:</strong> uploader" in response.text
    assert "منطقه:</strong> منطقه یک" in response.text
    assert "نوع فایل:</strong> snapshot" in response.text
    assert "تاریخ فایل:</strong> 1405-04-17" in response.text
    assert "مودیان اضافه‌شده:</strong> 1" in response.text
    assert "مودیان به‌روزرسانی‌شده:</strong> 1" in response.text
