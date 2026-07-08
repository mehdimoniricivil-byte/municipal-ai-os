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
    "آدرس واحد": ["آدرس ۱", "آدرس ۲"],
    "تاریخ پرداخت": [None, "1405-04-17"],
    "عوارض راه عبور": ["10", "20"],
    "عوارض استفاده از معبر": ["30", "40"],
    "عوارض تابلو": ["50", "60"],
    "رفع زباله": ["70", "80"],
    "مبلغ فیش": ["1,000", "2000"],
    "عوارض کسب": ["90", "100"],
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
        "عوارض \nراه عبور": ["10", "20"],
        "عوارض استفاده\n از معبر": ["30", "40"],
        "عوارض تابلو": ["50", "60"],
        "دفع زبااله": ["70", "80"],
        "مبلغ فيش": ["1,000", "2000"],
        "عوارض كسب": ["90", "100"],
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
        "business_tax",
        "passage_tax",
        "sidewalk_use_tax",
        "signboard_tax",
        "waste_fee",
    ]
    assert df.loc[0, "identification_code"] == "1 | P1"
    assert df.loc[0, "operator_name"] == "علی"
    assert df.loc[0, "bill_amount"] == Decimal("1000.00")
    assert df.loc[0, "business_tax"] == Decimal("90.00")
    assert df.loc[0, "passage_tax"] == Decimal("10.00")


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
        "business_tax",
        "passage_tax",
        "sidewalk_use_tax",
        "signboard_tax",
        "waste_fee",
    ]
    assert df.loc[0, "bill_amount"] == Decimal("1000.00")
    assert df.loc[0, "business_tax"] == Decimal("90.00")
    assert df.loc[0, "passage_tax"] == Decimal("10.00")


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


def test_read_snapshot_excel_accepts_declared_real_municipality_headers(tmp_path):
    path = tmp_path / "declared-real.xlsx"
    write_excel(
        path,
        {
            "نام متصدی": ["علی"],
            "شماره تماس": ["0912"],
            "شغل واحد": ["نانوایی"],
            "آدرس واحد": ["آدرس ۱"],
            "تاریخ پرداخت": ["1405/01/15"],
            "عوارض راه عبور": ["10"],
            "عوارض استفاده از معبر": ["20"],
            "عوارض تابلو": ["30"],
            "رفع زباله": ["40"],
            "مبلغ فیش": ["1000"],
            "عوارض کسب": ["50"],
            "بدهی معوقه": ["60"],
            "کد شناسایی": ["ID1"],
            "شماره پرونده": ["P1"],
        },
    )

    df = read_snapshot_excel(path)

    assert df.loc[0, "identification_code"] == "ID1 | P1"
    assert df.loc[0, "case_number"] == "P1"
    assert df.loc[0, "operator_name"] == "علی"
    assert df.loc[0, "phone"] == "0912"
    assert df.loc[0, "job"] == "نانوایی"
    assert df.loc[0, "address"] == "آدرس ۱"
    assert df.loc[0, "payment_date"] == "1405/01/15"
    assert df.loc[0, "bill_amount"] == Decimal("1000.00")
    assert df.loc[0, "outstanding_debt"] == Decimal("60.00")
    assert df.loc[0, "business_tax"] == Decimal("50.00")
    assert df.loc[0, "passage_tax"] == Decimal("10.00")
    assert df.loc[0, "sidewalk_use_tax"] == Decimal("20.00")
    assert df.loc[0, "signboard_tax"] == Decimal("30.00")
    assert df.loc[0, "waste_fee"] == Decimal("40.00")


def test_import_excel_adds_new_tax_columns_to_existing_legacy_schema(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE taxpayers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identification_code VARCHAR(255) NOT NULL UNIQUE,
                case_number VARCHAR(255),
                operator_name TEXT,
                job TEXT,
                phone TEXT,
                address TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE import_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date VARCHAR(32) NOT NULL,
                region VARCHAR(255) NOT NULL,
                source_file TEXT NOT NULL,
                status VARCHAR(32) NOT NULL,
                rows_imported INTEGER NOT NULL DEFAULT 0,
                report_path TEXT,
                error_message TEXT,
                started_at DATETIME NOT NULL,
                finished_at DATETIME,
                CONSTRAINT uq_import_runs_snapshot_region UNIQUE (snapshot_date, region)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_run_id INTEGER NOT NULL,
                snapshot_date VARCHAR(32) NOT NULL,
                region VARCHAR(255) NOT NULL,
                identification_code VARCHAR(255) NOT NULL,
                case_number VARCHAR(255),
                operator_name TEXT,
                job TEXT,
                phone TEXT,
                address TEXT,
                payment_date VARCHAR(64),
                bill_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
                outstanding_debt NUMERIC(18, 2) NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_daily_snapshot_key UNIQUE (snapshot_date, region, identification_code)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE daily_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_run_id INTEGER NOT NULL,
                snapshot_date VARCHAR(32) NOT NULL,
                region VARCHAR(255) NOT NULL,
                identification_code VARCHAR(255) NOT NULL,
                case_number VARCHAR(255),
                change_type VARCHAR(64) NOT NULL,
                field_name VARCHAR(64),
                old_value TEXT,
                new_value TEXT,
                created_at DATETIME NOT NULL
            )
            """
        )
    path = tmp_path / "legacy-schema.xlsx"
    write_excel(path, COLUMNS)

    result = import_excel(path, "1405-04-18", "منطقه یک", engine, tmp_path / "reports")

    with engine.connect() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(daily_snapshots)")}
        snapshot = conn.execute(select(daily_snapshots)).first()

    assert result.rows_imported == 2
    assert {"business_tax", "passage_tax", "sidewalk_use_tax", "signboard_tax", "waste_fee"} <= columns
    assert snapshot.business_tax == Decimal("90.00")
    assert snapshot.passage_tax == Decimal("10.00")
