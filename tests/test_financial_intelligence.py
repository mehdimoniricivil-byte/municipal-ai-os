import json
from datetime import date

from municipal_ai_os.financial_intelligence import FinancialIntelligenceDashboard


def write_org(path):
    path.write_text(
        json.dumps(
            {
                "municipalities": [
                    {
                        "id": "mun-1",
                        "name": "Central Municipality",
                        "regions": [
                            {"id": "north", "name": "North", "zones": [{"id": "n1", "name": "N1"}]},
                            {"id": "south", "name": "South", "zones": [{"id": "s1", "name": "S1"}]},
                        ],
                    }
                ],
                "staff_roles": ["collector", "supervisor"],
                "employment_types": ["full_time", "contractor"],
                "cost_centers": ["North Collections", "South Collections"],
                "staff_members": [
                    {
                        "unique_id": "staff-n1",
                        "full_name": "North Collector",
                        "municipality": "Central Municipality",
                        "region": "North",
                        "zone": "N1",
                        "role": "collector",
                        "employment_status": "active",
                        "employment_type": "full_time",
                        "cost_center": "North Collections",
                        "salary": 150,
                        "insurance_cost": 20,
                        "transportation_cost": 10,
                        "communication_cost": 5,
                        "other_expenses": 5,
                    },
                    {
                        "unique_id": "staff-s1",
                        "full_name": "South Collector",
                        "municipality": "Central Municipality",
                        "region": "South",
                        "zone": "S1",
                        "role": "collector",
                        "employment_status": "active",
                        "employment_type": "contractor",
                        "cost_center": "South Collections",
                        "salary": 40,
                        "insurance_cost": 0,
                        "transportation_cost": 5,
                        "communication_cost": 5,
                        "other_expenses": 0,
                    },
                ],
            }
        )
    )


def test_financial_dashboard_uses_staff_costs_and_preserves_history(tmp_path):
    config = tmp_path / "financial_rules.json"
    config.write_text(
        json.dumps(
            {
                "contract_commission_rate": 0.1,
                "regions": {"North": {"contract_commission_rate": 0.2}},
            }
        )
    )
    org_path = tmp_path / "organization_model.json"
    write_org(org_path)
    dashboard = FinancialIntelligenceDashboard(tmp_path, config, org_path)
    previous = [
        {"debtor_id": "1", "region": "North", "assigned_collector": "A", "debt_amount": 1000},
        {"debtor_id": "2", "region": "South", "assigned_collector": "B", "debt_amount": 500},
    ]
    current = [
        {"debtor_id": "1", "region": "North", "assigned_collector": "A", "debt_amount": 700},
        {"debtor_id": "2", "region": "South", "assigned_collector": "B", "debt_amount": 400},
    ]

    result = dashboard.build(
        run_id="run-1", current_snapshot=current, previous_snapshot=previous, as_of=date(2026, 7, 4)
    )

    north = next(row for row in result["regions"] if row["region"] == "North")
    assert north["municipality"] == "Central Municipality"
    assert north["daily_collection_amount"] == 300
    assert north["company_revenue"] == 60
    assert north["staff_count"] == 1
    assert north["staff_member_ids"] == ["staff-n1"]
    assert north["salary"] == 150
    assert north["total_staff_cost"] == 190
    assert north["total_operational_cost"] == 190
    assert north["net_profit"] == -130
    assert north["profit_per_collector"] == -130
    assert north["profit_per_billion_collected"] == -433333333.33
    assert north["roi"] == -0.6842
    assert result["recommendation_only"] is True
    assert result["organization_snapshot"]["recommendation_only"] is True
    assert (tmp_path / "state" / "financial_history" / "2026-07-04.jsonl").exists()
    assert (tmp_path / "state" / "organization_snapshots" / "latest.json").exists()
    assert result["comparisons"]["North"]["yesterday"] == {"available": False}
    assert any(
        comment["type"] == "inefficient_staff_allocation"
        for comment in result["ai_financial_comments"]
    )
    assert any(
        comment["recommendation_only"] is True for comment in result["ai_financial_comments"]
    )


def test_financial_dashboard_compares_previous_run_and_periods(tmp_path):
    config = tmp_path / "financial_rules.json"
    config.write_text(json.dumps({"contract_commission_rate": 0.5}))
    org_path = tmp_path / "organization_model.json"
    write_org(org_path)
    dashboard = FinancialIntelligenceDashboard(tmp_path, config, org_path)
    history_dir = tmp_path / "state" / "financial_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_rows = [
        {
            "date": "2026-07-03",
            "run_id": "old",
            "region": "North",
            "daily_collection_amount": 200,
            "company_revenue": 100,
            "total_cost": 25,
            "net_profit": 75,
        },
        {
            "date": "2026-06-30",
            "run_id": "older",
            "region": "North",
            "daily_collection_amount": 100,
            "company_revenue": 50,
            "total_cost": 20,
            "net_profit": 30,
        },
    ]
    (history_dir / "2026-07-03.jsonl").write_text(
        "\n".join(json.dumps(row) for row in history_rows[:1]) + "\n"
    )
    (history_dir / "2026-06-30.jsonl").write_text(
        "\n".join(json.dumps(row) for row in history_rows[1:]) + "\n"
    )

    result = dashboard.build(
        run_id="new",
        current_snapshot=[
            {"debtor_id": "1", "region": "North", "assigned_collector": "A", "debt_amount": 100}
        ],
        previous_snapshot=[
            {"debtor_id": "1", "region": "North", "assigned_collector": "A", "debt_amount": 300}
        ],
        as_of=date(2026, 7, 4),
    )

    comparison = result["comparisons"]["North"]
    assert comparison["yesterday"]["net_profit_delta"] == -165
    assert comparison["previous_run"]["daily_collection_amount_delta"] == 0
    assert comparison["last_7_days"]["record_count"] == 2
    assert comparison["last_30_days"]["net_profit"] == 105
    assert comparison["current_month"]["record_count"] == 1
    assert comparison["year_to_date"]["record_count"] == 2


def test_financial_dashboard_recommends_staff_reallocation_without_changes(tmp_path):
    config = tmp_path / "financial_rules.json"
    config.write_text(json.dumps({"contract_commission_rate": 1.0}))
    org_path = tmp_path / "organization_model.json"
    write_org(org_path)
    dashboard = FinancialIntelligenceDashboard(tmp_path, config, org_path)

    result = dashboard.build(
        run_id="run-2",
        current_snapshot=[
            {"debtor_id": "1", "region": "North", "assigned_collector": "A", "debt_amount": 990},
            {"debtor_id": "2", "region": "South", "assigned_collector": "B", "debt_amount": 0},
        ],
        previous_snapshot=[
            {"debtor_id": "1", "region": "North", "assigned_collector": "A", "debt_amount": 1000},
            {"debtor_id": "2", "region": "South", "assigned_collector": "B", "debt_amount": 500},
        ],
        as_of=date(2026, 7, 4),
    )

    assert any(
        comment["type"] == "cross_region_staff_reallocation"
        for comment in result["ai_financial_comments"]
    )
    org_latest = json.loads(
        (tmp_path / "state" / "organization_snapshots" / "latest.json").read_text()
    )
    assert org_latest["recommendation_only"] is True
    assert [member["region"] for member in org_latest["model"]["staff_members"]] == [
        "North",
        "South",
    ]
