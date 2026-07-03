import json
from pathlib import Path

from municipal_ai_os.daily_work_assignment import DailyWorkAssignmentEngine


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload))


def test_daily_assignment_balances_capacity_and_zones(tmp_path):
    write_json(
        tmp_path / "assignment_rules.json",
        {
            "schedule_date": "2026-07-03",
            "agents": [
                {
                    "agent_id": "caller_a",
                    "name": "Caller A",
                    "roles": ["CALL"],
                    "available": True,
                    "max_calls_per_day": 2,
                    "max_visits_per_day": 0,
                    "max_notices_per_day": 0,
                    "max_legal_per_day": 0,
                },
                {
                    "agent_id": "caller_b",
                    "name": "Caller B",
                    "roles": ["CALL"],
                    "available": True,
                    "max_calls_per_day": 2,
                    "max_visits_per_day": 0,
                    "max_notices_per_day": 0,
                    "max_legal_per_day": 0,
                },
                {
                    "agent_id": "north_field",
                    "name": "North Field",
                    "roles": ["FIELD_VISIT", "NOTICE"],
                    "available": True,
                    "zones": ["North"],
                    "max_calls_per_day": 0,
                    "max_visits_per_day": 2,
                    "max_notices_per_day": 1,
                    "max_legal_per_day": 0,
                },
                {
                    "agent_id": "south_field",
                    "name": "South Field",
                    "roles": ["FIELD_VISIT", "NOTICE"],
                    "available": True,
                    "zones": ["South"],
                    "max_calls_per_day": 0,
                    "max_visits_per_day": 2,
                    "max_notices_per_day": 1,
                    "max_legal_per_day": 0,
                },
            ],
        },
    )
    write_json(tmp_path / "priority_report.json", {"tasks": [{"case_id": "c1", "priority": "critical"}]})
    write_json(tmp_path / "daily_call_queue.json", [{"case_id": "c1"}, {"case_id": "c2"}, {"case_id": "c3"}])
    write_json(
        tmp_path / "daily_visit_queue.json",
        [{"case_id": "v1", "zone": "North"}, {"case_id": "v2", "zone": "South"}],
    )
    write_json(tmp_path / "daily_notice_queue.json", [{"case_id": "n1", "zone": "North"}])
    write_json(tmp_path / "legal_queue.json", [{"case_id": "l1"}])

    outputs = DailyWorkAssignmentEngine(tmp_path).run()

    assert outputs["assignments"]["caller_a"]["assigned_counts"]["calls"] in {1, 2}
    assert outputs["assignments"]["caller_b"]["assigned_counts"]["calls"] in {1, 2}
    assert outputs["assignments"]["north_field"]["assignments"][0]["zone"] == "North"
    assert outputs["assignments"]["south_field"]["assignments"][0]["zone"] == "South"
    assert outputs["summary"]["total_unassigned"] == 1
    assert outputs["dashboard"]["recommendation_only"] is True
    for filename in [
        "agent_assignments.json",
        "daily_agent_schedule.json",
        "workload_summary.json",
        "manager_assignment_dashboard.json",
    ]:
        assert (tmp_path / filename).exists()
