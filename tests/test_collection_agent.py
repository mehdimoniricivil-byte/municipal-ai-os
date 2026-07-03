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
    assert set(queues) == {"Alex", "Blair"}
    alex_task = queues["Alex"][0]
    assert alex_task["debtor"] == "Jane Doe"
    assert alex_task["recommended_action"] in {"field visit", "phone call", "courtesy reminder"}
    assert "estimated_success_probability" in alex_task

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


def test_prevents_duplicate_runs_with_lock(tmp_path):
    agent = CollectionAgent(tmp_path / "agent")
    agent.lock_path.write_text("123")

    with pytest.raises(DuplicateRunError):
        agent.run()
