import json

import pytest

from municipal_ai_os.organization_engine import OrganizationEngine


def write_model(path, staff_members):
    path.write_text(
        json.dumps(
            {
                "municipalities": [
                    {
                        "id": "mun-1",
                        "name": "Central Municipality",
                        "regions": [
                            {
                                "id": "north",
                                "name": "North",
                                "zones": [{"id": "n1", "name": "North Zone 1"}],
                            }
                        ],
                    }
                ],
                "staff_roles": ["collector", "supervisor"],
                "employment_types": ["full_time", "contractor"],
                "cost_centers": ["North Collections"],
                "staff_members": staff_members,
            }
        )
    )


def test_organization_engine_validates_and_aggregates_staff_costs(tmp_path):
    model_path = tmp_path / "organization_model.json"
    write_model(
        model_path,
        [
            {
                "unique_id": "staff-1",
                "full_name": "Alex Collector",
                "municipality": "Central Municipality",
                "region": "North",
                "zone": "North Zone 1",
                "role": "collector",
                "employment_status": "active",
                "employment_type": "full_time",
                "cost_center": "North Collections",
                "salary": 100,
                "insurance_cost": 20,
                "transportation_cost": 10,
                "communication_cost": 5,
                "other_expenses": 3,
            },
            {
                "unique_id": "staff-2",
                "full_name": "Inactive Staff",
                "municipality": "Central Municipality",
                "region": "North",
                "zone": "North Zone 1",
                "role": "supervisor",
                "employment_status": "inactive",
                "employment_type": "full_time",
                "cost_center": "North Collections",
                "salary": 999,
                "insurance_cost": 999,
                "transportation_cost": 999,
                "communication_cost": 999,
            },
        ],
    )

    engine = OrganizationEngine(tmp_path, model_path)
    costs = engine.aggregate_region_costs()["North"]
    snapshot = engine.snapshot("run-1")

    assert costs["staff_count"] == 1
    assert costs["collector_count"] == 1
    assert costs["total_staff_cost"] == 138
    assert costs["staff_member_ids"] == ["staff-1"]
    assert costs["zones"] == ["North Zone 1"]
    assert snapshot["recommendation_only"] is True
    assert (tmp_path / "state" / "organization_snapshots" / "latest.json").exists()


def test_organization_engine_rejects_duplicate_staff_ids(tmp_path):
    model_path = tmp_path / "organization_model.json"
    duplicate_staff = {
        "unique_id": "staff-1",
        "full_name": "Alex Collector",
        "municipality": "Central Municipality",
        "region": "North",
        "zone": "North Zone 1",
        "role": "collector",
        "employment_status": "active",
        "employment_type": "full_time",
        "cost_center": "North Collections",
        "salary": 100,
        "insurance_cost": 20,
        "transportation_cost": 10,
        "communication_cost": 5,
    }
    write_model(model_path, [duplicate_staff, duplicate_staff])

    with pytest.raises(ValueError, match="Duplicate staff"):
        OrganizationEngine(tmp_path, model_path)
