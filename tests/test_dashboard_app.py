from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from shahrdari_ai import upload_app
from shahrdari_ai.etl.engine import import_excel


def _excel(path: Path, debts=(5000, 0), phones=("0912", None)):
    pd.DataFrame(
        {
            "کد شناسایی": ["1", "2"],
            "شماره پرونده": ["P1", "P2"],
            "نام متصدی": ["علی اکبری", "رضا"],
            "شغل واحد": ["نانوایی", "سوپر"],
            "شماره تماس": list(phones),
            "آدرس واحد": ["خیابان اول", "بازار"],
            "تاریخ پرداخت": [None, None],
            "عوارض راه عبور": ["10", "20"],
            "عوارض استفاده از معبر": ["30", "40"],
            "عوارض تابلو": ["50", "60"],
            "رفع زباله": ["70", "80"],
            "مبلغ فیش": ["1000", "2000"],
            "عوارض کسب": ["90", "100"],
            "بدهی معوقه": [str(debts[0]), str(debts[1])],
        }
    ).to_excel(path, index=False)


def test_dashboard_taxpayer_search_and_detail_use_database_totals(tmp_path, monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    path = tmp_path / "r1.xlsx"
    _excel(path)
    import_excel(path, "1405-04-17", "منطقه یک", engine, tmp_path / "reports", file_type="snapshot", uploaded_by="uploader", source_file_name="r1.xlsx")
    monkeypatch.setattr(upload_app, "make_engine", lambda: engine)

    dashboard = upload_app.dashboard()
    assert dashboard.status_code == 200
    text = dashboard.body.decode("utf-8")
    assert "داشبورد مدیریت شهرداری" in text
    assert "5,000" in text
    assert "بدون تلفن" in text
    assert "r1.xlsx" in text

    search = upload_app.taxpayers_page(q="علی")
    search_text = search.body.decode("utf-8")
    assert "علی اکبری" in search_text
    assert "5,000" in search_text

    detail = upload_app.taxpayer_detail("1 | P1")
    detail_text = detail.body.decode("utf-8")
    assert "خیابان اول" in detail_text
    assert "5,000" in detail_text


def test_import_excel_prevents_duplicate_snapshot_imports(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    path = tmp_path / "r1.xlsx"
    _excel(path)
    import_excel(path, "1405-04-17", "منطقه یک", engine, tmp_path / "reports", file_type="snapshot")

    try:
        import_excel(path, "1405-04-17", "منطقه یک", engine, tmp_path / "reports", file_type="snapshot")
    except ValueError as exc:
        assert "Duplicate snapshot import" in str(exc)
    else:
        raise AssertionError("duplicate import should fail")
