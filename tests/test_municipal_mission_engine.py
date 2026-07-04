import json

from municipal_ai_os.collection_agent import CollectionAgent
from municipal_ai_os.municipal_mission_engine import MissionContext, MunicipalMissionEngine


def test_mission_engine_generates_rules_based_outputs():
    outputs = MunicipalMissionEngine().build(
        MissionContext(
            run_id="run-1",
            recommendations=[
                {
                    "record_id": "r1",
                    "collector": "Alex",
                    "zone": "North",
                    "region": "North",
                    "debt_amount": 12000,
                    "priority": "high",
                    "recommended_action": "FIELD_VISIT",
                },
                {
                    "record_id": "r2",
                    "collector": "Alex",
                    "zone": "North",
                    "region": "North",
                    "debt_amount": 4000,
                    "priority": "medium",
                    "recommended_action": "CALL",
                },
                {
                    "record_id": "r3",
                    "collector": "Blair",
                    "zone": "South",
                    "region": "South",
                    "debt_amount": 5000,
                    "priority": "high",
                    "recommended_action": "LEGAL",
                    "legal_status": "legal",
                },
            ],
            scored_records=[],
        )
    )

    missions = outputs["municipal_missions"]
    assert {mission["mission_type"] for mission in missions} >= {
        "high_value_recovery",
        "legal_readiness",
        "collector_focus",
    }
    assert outputs["municipal_mission_dashboard"]["mission_count"] == len(missions)
    assert "گزارش ماموریت‌های روزانه شهرداری" in outputs["human_readable_manager_report"]
    assert all(mission["recommendation_only"] is True for mission in missions)


def test_collection_agent_writes_mission_outputs_before_snapshot(tmp_path):
    workspace = tmp_path / "agent"
    agent = CollectionAgent(workspace)
    inbox_file = workspace / "inbox" / "debts.csv"
    inbox_file.write_text(
        "debtor,address,region,zone,collector,debt_amount,due_date,last_contact_date\n"
        "High Value,1 Main,North,North,Alex,12000,2026-01-01,2026-01-10\n"
        "Medium Case,2 Main,North,North,Alex,700,2026-01-01,2026-01-10\n"
    )

    state = agent.run()

    run_dir = workspace / "runs" / state.run_id
    assert state.completed_steps.index("generate_mission_outputs") < state.completed_steps.index(
        "generate_daily_snapshot"
    )
    missions = json.loads((run_dir / "municipal_missions.json").read_text())
    dashboard = json.loads((run_dir / "municipal_mission_dashboard.json").read_text())
    report = (run_dir / "human_readable_manager_report.md").read_text(encoding="utf-8")

    assert missions
    assert dashboard["recommendation_only"] is True
    assert "ماموریت" in report
    assert (run_dir / "daily_snapshot.json").exists()
