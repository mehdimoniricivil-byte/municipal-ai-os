import csv
import json
from pathlib import Path

import pytest

from municipal_ai_os.collection_agent import CollectionAgent, DuplicateRunError


def write_csv(path: Path):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "debtor",
                "address",
                "region",
                "collector",
                "debt_amount",
                "due_date",
                "last_contact_date",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "debtor": "Jane Doe",
                "address": "1 Main St",
                "region": "North",
                "collector": "Alex",
                "debt_amount": "1200",
                "due_date": "2026-01-01",
                "last_contact_date": "2026-02-01",
            }
        )
        writer.writerow(
            {
                "debtor": "Jane Doe",
                "address": "1 Main St",
                "region": "North",
                "collector": "Alex",
                "debt_amount": "1200",
                "due_date": "2026-01-01",
                "last_contact_date": "2026-02-01",
            }
        )
        writer.writerow(
            {
                "debtor": "Sam Smith",
                "address": "9 South St",
                "region": "South",
                "collector": "Blair",
                "debt_amount": "200",
                "due_date": "2026-06-20",
                "last_contact_date": "2026-06-25",
            }
        )


def write_snapshot_csv(path: Path, rows: list[dict[str, str]]):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "debtor_id",
                "debtor",
                "address",
                "mobile",
                "region",
                "zone",
                "business_category",
                "legal_status",
                "collector",
                "debt_amount",
                "due_date",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_agent_generates_work_queues_and_briefing(tmp_path):
    workspace = tmp_path / "agent"
    agent = CollectionAgent(workspace)
    write_csv(workspace / "inbox" / "debts.csv")

    state = agent.run()

    assert state.status == "completed"
    assert state.processed_debt_records == 3
    assert state.recommendations_generated == 2
    assert any("duplicate record skipped" in warning for warning in state.warnings)

    run_dir = workspace / "runs" / state.run_id
    queues = json.loads((run_dir / "collector_work_queues.json").read_text())
    assert set(queues) == {"CALL", "FIELD_VISIT", "NOTICE", "LEGAL", "FOLLOW_UP", "IGNORE"}
    queued_tasks = [task for queue in queues.values() for task in queue]
    jane_task = next(task for task in queued_tasks if task["debtor"] == "Jane Doe")
    assert jane_task["recommended_action"] in {
        "CALL",
        "FIELD_VISIT",
        "NOTICE",
        "LEGAL",
        "FOLLOW_UP",
        "IGNORE",
    }
    assert "estimated_success_probability" in jane_task
    assert (run_dir / "daily_call_queue.json").exists()
    assert (run_dir / "daily_visit_queue.json").exists()
    assert (run_dir / "daily_notice_queue.json").exists()
    assert (run_dir / "legal_queue.json").exists()
    assert (run_dir / "manager_dashboard.json").exists()

    manager_dashboard = json.loads((run_dir / "manager_dashboard.json").read_text())
    assert manager_dashboard["recommendation_only"] is True
    assert sum(manager_dashboard["queue_counts"].values()) == 2

    briefing = json.loads((run_dir / "manager_morning_briefing.json").read_text())
    assert briefing["today_total_target"] == 1400
    assert "region_comparison" in briefing
    assert "collector_comparison" in briefing
    assert briefing["recommended_management_actions"]

    dashboard = json.loads((run_dir / "mayor_dashboard.json").read_text())
    assert "executive_kpis" in dashboard
    assert "municipality_health_score" in dashboard["executive_kpis"]
    assert "collection_efficiency_score" in dashboard["executive_kpis"]

    intelligence = json.loads((run_dir / "executive_decision_engine.json").read_text())
    assert intelligence["executive_recommendations"]
    assert all("ai_reasoning" in item for item in intelligence["executive_recommendations"])
    assert (workspace / "state" / "executive_recommendations.jsonl").exists()


def test_agent_accepts_region_1_persian_schema(tmp_path):
    workspace = tmp_path / "agent"
    agent = CollectionAgent(workspace)
    path = workspace / "inbox" / "region_1.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "نشاني واحد صنفي",
                "نام متصدي",
                "بدهي معوقه",
                "تاريخ پرداخت",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "نشاني واحد صنفي": "بازار منطقه یک",
                "نام متصدي": "احمدی / رضا",
                "بدهي معوقه": "1500",
                "تاريخ پرداخت": "2026-01-01",
            }
        )

    state = agent.run()

    assert state.status == "completed"
    assert state.processed_debt_records == 1
    assert state.recommendations_generated == 1

    run_dir = workspace / "runs" / state.run_id
    validate = json.loads((run_dir / "validate_records.json").read_text())
    record = validate["records"][0]
    assert record["debtor"] == "احمدی / رضا"
    assert record["address"] == "بازار منطقه یک"
    assert record["debt_amount"] == 1500

    manager_dashboard = json.loads((run_dir / "manager_dashboard.json").read_text())
    assert sum(manager_dashboard["queue_counts"].values()) == 1


def test_snapshot_change_performance_alerts_and_monitoring_dashboard(tmp_path):
    workspace = tmp_path / "agent"
    agent = CollectionAgent(workspace)
    write_snapshot_csv(
        workspace / "inbox" / "day1.csv",
        [
            {
                "debtor_id": "A",
                "debtor": "Alpha",
                "address": "1 St",
                "mobile": "1",
                "region": "North",
                "zone": "N1",
                "business_category": "Retail",
                "legal_status": "open",
                "collector": "Alex",
                "debt_amount": "100",
                "due_date": "2026-01-01",
            },
            {
                "debtor_id": "B",
                "debtor": "Beta",
                "address": "2 St",
                "mobile": "2",
                "region": "North",
                "zone": "N1",
                "business_category": "Retail",
                "legal_status": "open",
                "collector": "Alex",
                "debt_amount": "200",
                "due_date": "2026-01-01",
            },
            {
                "debtor_id": "C",
                "debtor": "Gamma",
                "address": "3 St",
                "mobile": "3",
                "region": "South",
                "zone": "S1",
                "business_category": "Food",
                "legal_status": "open",
                "collector": "Alex",
                "debt_amount": "300",
                "due_date": "2026-01-01",
            },
            {
                "debtor_id": "D",
                "debtor": "Delta",
                "address": "4 St",
                "mobile": "4",
                "region": "South",
                "zone": "S1",
                "business_category": "Food",
                "legal_status": "open",
                "collector": "Alex",
                "debt_amount": "400",
                "due_date": "2026-01-01",
            },
        ],
    )
    first = agent.run()
    first_run = workspace / "runs" / first.run_id
    assert len(json.loads((first_run / "daily_snapshot.json").read_text())) == 4
    assert (first_run / "snapshot_summary.json").exists()

    write_snapshot_csv(
        workspace / "inbox" / "day2.csv",
        [
            {
                "debtor_id": "A",
                "debtor": "Alpha",
                "address": "1 New St",
                "mobile": "9",
                "region": "North",
                "zone": "N1",
                "business_category": "Retail",
                "legal_status": "open",
                "collector": "Alex",
                "debt_amount": "80",
                "due_date": "2026-01-01",
            },
            {
                "debtor_id": "B",
                "debtor": "Beta",
                "address": "2 St",
                "mobile": "2",
                "region": "North",
                "zone": "N1",
                "business_category": "Retail",
                "legal_status": "open",
                "collector": "Alex",
                "debt_amount": "250",
                "due_date": "2026-01-01",
            },
            {
                "debtor_id": "D",
                "debtor": "Delta",
                "address": "4 St",
                "mobile": "4",
                "region": "South",
                "zone": "S1",
                "business_category": "Food",
                "legal_status": "paid",
                "collector": "Alex",
                "debt_amount": "400",
                "due_date": "2026-01-01",
            },
            {
                "debtor_id": "E",
                "debtor": "Epsilon",
                "address": "5 St",
                "mobile": "5",
                "region": "East",
                "zone": "E1",
                "business_category": "Service",
                "legal_status": "open",
                "collector": "Blair",
                "debt_amount": "50",
                "due_date": "2026-01-01",
            },
        ],
    )
    second = agent.run()
    second_run = workspace / "runs" / second.run_id

    change_report = json.loads((second_run / "daily_change_report.json").read_text())
    assert [record["debtor_id"] for record in change_report["new_debtors"]] == ["E"]
    assert [record["debtor_id"] for record in change_report["removed_debtors"]] == ["C"]
    assert [item["debtor_id"] for item in change_report["debt_amount_decreased"]] == ["A"]
    assert [item["debtor_id"] for item in change_report["debt_amount_increased"]] == ["B"]
    assert [record["debtor_id"] for record in change_report["fully_paid_or_cleared_debtors"]] == [
        "D"
    ]
    assert [item["debtor_id"] for item in change_report["changed_address_or_mobile"]] == ["A"]

    performance = json.loads((second_run / "collector_performance_report.json").read_text())
    alex = next(row for row in performance["collectors"] if row["collector"] == "Alex")
    assert alex["assigned_case_count"] == 4
    assert alex["cases_improved"] == 2
    assert alex["cases_worsened"] == 1
    assert alex["paid_or_cleared_cases"] == 1
    assert 0 <= alex["performance_score"] <= 100

    alerts = agent._collector_alerts(
        {
            "collectors": [
                {
                    **agent._empty_collector_performance("Alex"),
                    "assigned_case_count": 2,
                    "cases_unchanged": 2,
                    "follow_up_overdue_cases": 2,
                }
            ]
        },
        [],
        {
            "unchanged_many_threshold": 2,
            "unchanged_ratio_alert": 0.5,
            "repeated_visit_no_progress_threshold": 2,
            "notice_no_payment_threshold": 2,
            "high_priority_ignored_score": 80,
        },
    )
    assert alerts["alerts"]

    dashboard = json.loads((second_run / "manager_daily_monitoring_dashboard.json").read_text())
    assert dashboard["total_new_debtors"] == 1
    assert dashboard["total_removed_or_paid_debtors"] == 2
    assert dashboard["net_debt_change"] == -220


def test_prevents_duplicate_runs_with_lock(tmp_path):
    agent = CollectionAgent(tmp_path / "agent")
    agent.lock_path.write_text("123")

    with pytest.raises(DuplicateRunError):
        agent.run()


def test_collection_workflow_preserves_snapshot_financial_and_field_steps():
    from municipal_ai_os.collection_agent import WORKFLOW_STEPS

    assert "generate_daily_snapshot" in WORKFLOW_STEPS
    assert "generate_executive_intelligence" in WORKFLOW_STEPS
    assert "generate_field_activity_attribution" in WORKFLOW_STEPS
    assert "generate_financial_intelligence" in WORKFLOW_STEPS
    assert WORKFLOW_STEPS.index("generate_field_activity_attribution") < WORKFLOW_STEPS.index(
        "generate_financial_intelligence"
    )
