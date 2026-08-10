from pathlib import Path

from app.main import app, root


STATIC_DIR = Path(__file__).parents[1] / "app" / "static"


def test_financial_dashboard_reads_collections_from_core_api():
    dashboard = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")

    assert 'const CORE_DASHBOARD_URL = "/core-api/api/dashboard"' in dashboard
    assert "data.scope_summaries || []" in dashboard
    assert "row.monthly_collection" in dashboard
    assert "row.weekly_collection" in dashboard
    assert "row.latest_day_collection" in dashboard
    assert "row.monthly_collection ?? row.paid_amount" in dashboard
    assert "row.total_collection ?? row.paid_amount" in dashboard
    assert "finance/settings" in dashboard


def test_expense_post_keeps_authorization_header_and_region_ids():
    dashboard = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")
    request_helper = dashboard.split("async function getJSON", 1)[1].split("function deltaHTML", 1)[0]

    assert request_helper.index("...options") < request_helper.index('headers: {"Accept"')
    assert '"Authorization":`Bearer ${localStorage.getItem("access_token")||""}`' in request_helper
    assert '{region_id:5,id:"r3"' in dashboard
    assert '{region_id:4,id:"a3"' in dashboard


def test_financial_pages_respect_backend_proxy_prefix():
    statements = (STATIC_DIR / "statements.html").read_text(encoding="utf-8")

    assert "location.pathname.split('/dashboard/')[0]" in statements
    assert "const API=BASE+'/api/v1'" in statements
    assert app.root_path == "/backend-v1"
    assert root().headers["location"] == "dashboard/login.html"


def test_dashboard_keeps_expenses_and_statements_navigation():
    dashboard = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")

    assert "فرم ورود هزینه" in dashboard
    assert 'id="expenseRows"' in dashboard
    assert "صورت‌وضعیت‌ها" in dashboard
    assert "/dashboard/statements.html" in dashboard


def test_dashboard_has_no_old_fixed_financial_or_debt_figures():
    dashboard = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")

    assert "۱۹٬۰۲۴٬۷۰۶٬۵۰۰" not in dashboard
    assert "۵۸٬۳۸۵٬۶۲۳٬۰۰۰" not in dashboard
    assert "هزینه فرضی" not in dashboard
    assert "const WAGE_RATE = 0.06" not in dashboard
    assert 'id="debtRows"' in dashboard
    assert 'id="financeSummaryBody"' in dashboard
