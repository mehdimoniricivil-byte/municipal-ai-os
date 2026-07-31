from openpyxl import Workbook

from app.upload.parser import read_first_sheet
from app.upload.validator import validate_rows


def test_valid_monthly_xlsx(tmp_path):
    path = tmp_path / "sample.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["نام متصدي", "تاريخ پرداخت", "مبلغ فيش"])
    sheet.append(["علی", "1405/04/01", 100000])
    sheet.append(["رضا", "1405/04/02", 250000])
    workbook.save(path)

    result = validate_rows(read_first_sheet(path), 1405, 4)

    assert result.can_import is True
    assert result.valid_rows == 2
    assert result.total_amount_irr == 350000
