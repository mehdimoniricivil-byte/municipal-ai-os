from decimal import Decimal
import pytest

from app.core.calculation_engine import calculate_balance, calculate_statement, calculate_wage


def test_calculate_wage_rounds_to_irr():
    assert calculate_wage("1001", "2.5") == Decimal("25")


def test_statement_uses_registered_gross_and_deductions():
    result = calculate_statement(
        collection_amount_irr="1000000",
        wage_rate_percent="5",
        gross_amount_irr="50000",
        deductions_irr="12500",
    )
    assert result.net_amount_irr == Decimal("37500")


def test_statement_never_has_negative_net():
    result = calculate_statement(
        collection_amount_irr="1000000",
        wage_rate_percent="5",
        deductions_irr="60000",
    )
    assert result.net_amount_irr == Decimal("0")


def test_balance_rejects_overpayment():
    with pytest.raises(ValueError):
        calculate_balance("100", "101")
