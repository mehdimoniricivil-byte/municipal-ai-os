from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

HEADER_ALIASES = {
    "payment_date": {"تاریخ پرداخت", "تاريخ پرداخت", "تاریخ واریز", "تاريخ واريز"},
    "amount": {"مبلغ فیش", "مبلغ فيش", "مبلغ پرداخت", "مبلغ وصول", "مبلغ"},
    "receipt_number": {"شماره فیش", "شماره فيش", "شماره قبض", "شناسه پرداخت", "کد رهگیری"},
    "payer_name": {"نام متصدی", "نام متصدي", "نام پرداخت کننده", "مودی", "نام مودی"},
    "phone": {"شماره تماس", "تلفن", "موبایل"},
    "business_title": {"شغل واحد", "عنوان شغل", "شغل", "نام واحد صنفی"},
    "address": {"نشانی واحد صنفی", "نشاني واحد صنفي", "آدرس", "نشانی"},
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS)
    text = text.replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip()


def normalize_header(value: Any) -> str:
    return normalize_text(value).replace("‌", " ")


def build_column_map(headers: list[Any]) -> dict[str, int]:
    normalized = [normalize_header(item) for item in headers]
    mapping: dict[str, int] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        normalized_aliases = {normalize_header(alias) for alias in aliases}
        for index, header in enumerate(normalized):
            if header in normalized_aliases:
                mapping[canonical] = index
                break
    return mapping


def parse_amount(value: Any) -> Decimal:
    if value is None or value == "":
        raise ValueError("مبلغ خالی است")
    if isinstance(value, str):
        value = normalize_text(value).replace(",", "").replace("٬", "")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("مبلغ عدد معتبر نیست") from exc
    if amount <= 0:
        raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد")
    return amount.quantize(Decimal("1"))


def parse_persian_date(value: Any) -> tuple[str, int, int]:
    text = normalize_text(value).replace("-", "/").replace(".", "/")
    match = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
    if not match:
        raise ValueError("تاریخ پرداخت باید به شکل 1405/01/01 باشد")
    year, month, day = map(int, match.groups())
    max_day = 31 if month <= 6 else 30
    if month == 12:
        max_day = 30
    if not 1300 <= year <= 1600 or not 1 <= month <= 12 or not 1 <= day <= max_day:
        raise ValueError("تاریخ پرداخت معتبر نیست")
    return f"{year:04d}/{month:02d}/{day:02d}", year, month


@dataclass
class ValidationIssue:
    row: int | None
    field: str | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"row": self.row, "field": self.field, "message": self.message}


@dataclass
class ValidationResult:
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    total_amount_irr: Decimal = Decimal("0")
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)

    @property
    def can_import(self) -> bool:
        return not self.errors and bool(self.records)

    def summary(self, include_records: bool = False) -> dict[str, Any]:
        payload = {
            "can_import": self.can_import,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "total_amount_irr": int(self.total_amount_irr),
            "errors": [issue.as_dict() for issue in self.errors],
            "warnings": [issue.as_dict() for issue in self.warnings],
        }
        if include_records:
            payload["records"] = self.records
        return payload


def validate_rows(rows: list[list[Any]], selected_year: int, selected_month: int) -> ValidationResult:
    result = ValidationResult()
    if not rows:
        result.errors.append(ValidationIssue(None, None, "فایل خالی است"))
        return result

    column_map = build_column_map(rows[0])
    for required in ("payment_date", "amount"):
        if required not in column_map:
            label = "تاریخ پرداخت" if required == "payment_date" else "مبلغ فیش"
            result.errors.append(ValidationIssue(1, required, f"ستون الزامی «{label}» پیدا نشد"))
    if result.errors:
        return result

    seen_hashes: set[str] = set()
    for row_number, values in enumerate(rows[1:], start=2):
        if not any(normalize_text(value) for value in values):
            continue
        result.total_rows += 1
        row_errors: list[ValidationIssue] = []

        def value_for(field: str) -> Any:
            index = column_map.get(field)
            return values[index] if index is not None and index < len(values) else None

        try:
            payment_date, year, month = parse_persian_date(value_for("payment_date"))
            if year != selected_year or month != selected_month:
                row_errors.append(ValidationIssue(row_number, "payment_date", "ماه یا سال پرداخت با دوره انتخاب‌شده یکسان نیست"))
        except ValueError as exc:
            payment_date, year, month = "", selected_year, selected_month
            row_errors.append(ValidationIssue(row_number, "payment_date", str(exc)))

        try:
            amount = parse_amount(value_for("amount"))
        except ValueError as exc:
            amount = Decimal("0")
            row_errors.append(ValidationIssue(row_number, "amount", str(exc)))

        record = {
            "source_row_number": row_number,
            "payment_date_persian": payment_date,
            "persian_year": year,
            "persian_month": month,
            "amount_irr": int(amount),
            "receipt_number": normalize_text(value_for("receipt_number")) or None,
            "payer_name": normalize_text(value_for("payer_name")) or None,
            "phone": normalize_text(value_for("phone")) or None,
            "business_title": normalize_text(value_for("business_title")) or None,
            "address": normalize_text(value_for("address")) or None,
            "raw_data": {normalize_header(header) or f"column_{i+1}": normalize_text(values[i]) if i < len(values) else "" for i, header in enumerate(rows[0])},
        }
        identity = json.dumps(
            {
                "date": record["payment_date_persian"],
                "amount": record["amount_irr"],
                "receipt": record["receipt_number"],
                "payer": record["payer_name"],
                "address": record["address"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        record["source_row_hash"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if record["source_row_hash"] in seen_hashes:
            row_errors.append(ValidationIssue(row_number, None, "این ردیف در همین فایل تکراری است"))
        seen_hashes.add(record["source_row_hash"])

        if row_errors:
            result.errors.extend(row_errors)
            result.invalid_rows += 1
        else:
            result.records.append(record)
            result.valid_rows += 1
            result.total_amount_irr += amount

    if result.total_rows == 0:
        result.errors.append(ValidationIssue(None, None, "هیچ ردیف اطلاعاتی در فایل وجود ندارد"))
    return result
