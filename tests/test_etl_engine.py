from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select

from shahrdari_ai.etl.engine import detect_changes, import_excel, normalize_column_name, read_snapshot_excel
from shahrdari_ai.etl.models import daily_changes, daily_snapshots, import_runs, taxpayers

COLUMNS = {
    "کد شناسایی": ["1", "2"],
    "شماره پرونده": ["P1", "P2"],
    "نام متصدی": ["علی", "رضا"],
    "شغل واحد": ["نانوایی", "سوپر"],
    "شماره تماس": ["0912", "0935"],
    "نشانی واحد صنفی": ["آدرس ۱", "آدرس ۲"],
    "تاریخ پرداخت": [None, "1405-04-17"],
    "مبلغ فیش": ["1,000", "2000"],
    "بدهی معوقه": ["5000", "3000"],
}


def write_excel(path: Path, data: dict) -> None:
    pd.DataFrame(data).to_excel(path, index=False)


def test_normalize_column_name_handles_arabic_persian_variants():
    assert normalize_column_name("  كد\u200c  شناسايي  ") == "کد شناسایی"
    assert normalize_column_name("ستون ۱۲٣") == "ستون 123"


def test_read_snapshot_excel_accepts_real_world_arabic_persian_column_variants(tmp_path):
    path = tmp_path / "real-world.xlsx"
    data = {
        "كد شناسايي": ["1", "2"],
        "شماره  پرونده": ["P1", "P2"],
        "نام متصدي": ["علی", "رضا"],
        "شغل واحد": ["نانوایی", "سوپر"],
        "شماره تماس": ["0912", "0935"],
        "نشاني واحد صنفي": ["آدرس ۱", "آدرس ۲"],
        "تاريخ پرداخت": [None, "1405-04-17"],
        "مبلغ فيش": ["1,000", "2000"],
        "بدهي معوقه": ["5000", "3000"],
    }
    write_excel(path, data)

    df = read_snapshot_excel(path)

    assert list(df.columns) == [
        "identification_code",
        "case_number",
        "operator_name",
        "job",
        "phone",
        "address",
        "payment_date",
        "bill_amount",
        "outstanding_debt",
    ]
    assert df.loc[0, "identification_code"] == "1"
    assert df.loc[0, "operator_name"] == "علی"
    assert df.loc[0, "bill_amount"] == Decimal("1000.00")


def test_read_snapshot_excel_missing_columns_error_is_persian_and_actionable(tmp_path):
    path = tmp_path / "missing.xlsx"
    write_excel(path, {"كد شناسايي": ["1"], "ستون ناشناس": ["x"]})

    try:
        read_snapshot_excel(path)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected missing-column ValueError")

    assert "ستون‌های ضروری فایل اکسل پیدا نشدند" in message
    assert "فیلد شماره پرونده (case_number)" in message
    assert "شماره پرونده" in message
    assert "ستون‌های موجود در فایل: كد شناسايي، ستون ناشناس" in message


def test_read_snapshot_excel_uses_column_names_and_cleans_values(tmp_path):
    path = tmp_path / "sample.xlsx"
    data = {"ستون اضافی": ["x", "y"]} | COLUMNS
    write_excel(path, data)

    df = read_snapshot_excel(path)

    assert list(df.columns) == [
        "identification_code",
        "case_number",
        "operator_name",
        "job",
        "phone",
        "address",
        "payment_date",
        "bill_amount",
        "outstanding_debt",
    ]
    assert df.loc[0, "bill_amount"] == Decimal("1000.00")


def test_detect_changes_reports_required_change_types():
    current = pd.DataFrame(
        [
            {"identification_code": "1", "case_number": "P1", "job": "کافه", "phone": "0913", "address": "جدید", "payment_date": "1405-04-18", "bill_amount": Decimal("1"), "outstanding_debt": Decimal("4000.00")},
            {"identification_code": "3", "case_number": "P3", "job": "کتاب", "phone": "0900", "address": "آدرس ۳", "payment_date": None, "bill_amount": Decimal("1"), "outstanding_debt": Decimal("10.00")},
        ]
    )
    previous = [
        {"identification_code": "1", "case_number": "P1", "job": "نانوایی", "phone": "0912", "address": "قدیم", "payment_date": None, "outstanding_debt": Decimal("5000.00")},
        {"identification_code": "2", "case_number": "P2", "job": "سوپر", "phone": "0935", "address": "آدرس ۲", "payment_date": None, "outstanding_debt": Decimal("3000.00")},
    ]

    types = [change["change_type"] for change in detect_changes(current, previous)]

    assert "new_taxpayer" in types
    assert "removed_taxpayer" in types
    assert "changed_debt" in types
    assert "decreased_debt" in types
    assert "new_payment_date" in types
    assert "changed_phone" in types
    assert "changed_address" in types
    assert "changed_job" in types


def test_import_excel_persists_snapshots_changes_and_report(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    write_excel(first, COLUMNS)
    changed = COLUMNS | {"کد شناسایی": ["1", "3"], "شماره تماس": ["0999", "0900"], "بدهی معوقه": ["7000", "10"]}
    write_excel(second, changed)

    import_excel(first, "1405-04-16", "منطقه یک", engine, tmp_path / "reports")
    result = import_excel(second, "1405-04-17", "منطقه یک", engine, tmp_path / "reports")

    with engine.connect() as conn:
        assert conn.execute(select(taxpayers)).fetchall()
        assert len(conn.execute(select(daily_snapshots)).fetchall()) == 4
        assert conn.execute(select(import_runs.c.status).order_by(import_runs.c.snapshot_date.desc())).first()[0] == "completed"
        change_types = {row.change_type for row in conn.execute(select(daily_changes.c.change_type))}
    assert {"new_taxpayer", "removed_taxpayer", "changed_debt", "increased_debt", "changed_phone"} <= change_types
    assert result.report_path.exists()
    assert "# گزارش روزانه مدیر - 1405-04-17" in result.report_path.read_text(encoding="utf-8")
