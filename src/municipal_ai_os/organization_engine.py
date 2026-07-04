"""Configurable organization model for Municipal AI OS."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTIVE_EMPLOYMENT_STATUSES = {"active", "probation", "contract_active"}
COLLECTOR_ROLES = {"collector", "senior_collector", "field_collector"}
STAFF_COST_FIELDS = [
    "salary",
    "insurance_cost",
    "transportation_cost",
    "communication_cost",
    "other_expenses",
]


@dataclass(frozen=True)
class StaffMember:
    """A single staff member with assignment and cost attributes."""

    unique_id: str
    full_name: str
    municipality: str
    region: str
    zone: str
    role: str
    employment_status: str
    employment_type: str
    cost_center: str
    salary: float
    insurance_cost: float
    transportation_cost: float
    communication_cost: float
    other_expenses: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.employment_status.lower() in ACTIVE_EMPLOYMENT_STATUSES

    @property
    def is_collector(self) -> bool:
        return self.role.lower() in COLLECTOR_ROLES

    @property
    def total_staff_cost(self) -> float:
        return round(
            self.salary
            + self.insurance_cost
            + self.transportation_cost
            + self.communication_cost
            + self.other_expenses,
            2,
        )


class OrganizationEngine:
    """Loads, validates, snapshots, and aggregates the municipal organization model."""

    def __init__(
        self,
        workspace: str | Path,
        model_path: str | Path = "config/organization_model.json",
    ) -> None:
        self.workspace = Path(workspace)
        self.model_path = Path(model_path)
        self.snapshot_dir = self.workspace / "state" / "organization_snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.model = self._load_model()
        self.staff = self._load_staff(self.model)
        self._validate_unique_staff_ids(self.staff)

    def snapshot(self, run_id: str, as_of: datetime | None = None) -> dict[str, Any]:
        """Persist the exact organization model used by a run without modifying assignments."""
        timestamp = (as_of or datetime.now(timezone.utc)).isoformat()
        payload = {
            "run_id": run_id,
            "snapshot_at": timestamp,
            "recommendation_only": True,
            "source_model_path": str(self.model_path),
            "model": self.model,
        }
        path = self.snapshot_dir / f"{timestamp.replace(':', '-')}-{run_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        latest = self.snapshot_dir / "latest.json"
        latest.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return {**payload, "snapshot_path": str(path)}

    def staff_by_region(self) -> dict[str, list[StaffMember]]:
        regions: dict[str, list[StaffMember]] = {}
        for member in self.staff:
            if member.is_active:
                regions.setdefault(member.region, []).append(member)
        return regions

    def aggregate_region_costs(self) -> dict[str, dict[str, Any]]:
        """Aggregate real active staff costs by assigned region."""
        aggregates: dict[str, dict[str, Any]] = {}
        for member in self.staff:
            if not member.is_active:
                continue
            bucket = aggregates.setdefault(
                member.region,
                {
                    "municipality": member.municipality,
                    "region": member.region,
                    "zones": set(),
                    "cost_centers": set(),
                    "staff_member_ids": [],
                    "staff_count": 0,
                    "collector_count": 0,
                    "salary": 0.0,
                    "insurance_cost": 0.0,
                    "transportation_cost": 0.0,
                    "communication_cost": 0.0,
                    "other_expenses": 0.0,
                    "total_staff_cost": 0.0,
                },
            )
            bucket["zones"].add(member.zone)
            bucket["cost_centers"].add(member.cost_center)
            bucket["staff_member_ids"].append(member.unique_id)
            bucket["staff_count"] += 1
            bucket["collector_count"] += 1 if member.is_collector else 0
            bucket["salary"] = round(bucket["salary"] + member.salary, 2)
            bucket["insurance_cost"] = round(bucket["insurance_cost"] + member.insurance_cost, 2)
            bucket["transportation_cost"] = round(
                bucket["transportation_cost"] + member.transportation_cost, 2
            )
            bucket["communication_cost"] = round(
                bucket["communication_cost"] + member.communication_cost, 2
            )
            bucket["other_expenses"] = round(bucket["other_expenses"] + member.other_expenses, 2)
            bucket["total_staff_cost"] = round(
                bucket["total_staff_cost"] + member.total_staff_cost, 2
            )
        for bucket in aggregates.values():
            bucket["zones"] = sorted(bucket["zones"])
            bucket["cost_centers"] = sorted(bucket["cost_centers"])
        return aggregates

    def known_regions(self) -> dict[str, dict[str, str]]:
        regions: dict[str, dict[str, str]] = {}
        for municipality in self.model.get("municipalities", []):
            municipality_name = str(
                municipality.get("name") or municipality.get("id") or "Unassigned"
            )
            for region in municipality.get("regions", []):
                region_name = str(region.get("name") or region.get("id") or "Unassigned")
                regions[region_name] = {
                    "municipality": municipality_name,
                    "region": region_name,
                    "zones": [
                        str(zone.get("name") or zone.get("id")) for zone in region.get("zones", [])
                    ],
                }
        return regions

    def _load_model(self) -> dict[str, Any]:
        if self.model_path.exists():
            return json.loads(self.model_path.read_text())
        return {"municipalities": [], "staff_members": []}

    def _load_staff(self, model: dict[str, Any]) -> list[StaffMember]:
        return [self._staff_member(row) for row in model.get("staff_members", [])]

    def _staff_member(self, row: dict[str, Any]) -> StaffMember:
        required = [
            "unique_id",
            "full_name",
            "municipality",
            "region",
            "zone",
            "role",
            "employment_status",
            "salary",
            "insurance_cost",
            "transportation_cost",
            "communication_cost",
        ]
        missing = [field for field in required if row.get(field) in (None, "")]
        if missing:
            raise ValueError(f"Staff member is missing required fields: {', '.join(missing)}")
        return StaffMember(
            unique_id=str(row["unique_id"]),
            full_name=str(row["full_name"]),
            municipality=str(row["municipality"]),
            region=str(row["region"]),
            zone=str(row["zone"]),
            role=str(row["role"]),
            employment_status=str(row["employment_status"]),
            employment_type=str(row.get("employment_type") or "unspecified"),
            cost_center=str(row.get("cost_center") or row["region"]),
            salary=self._money(row["salary"]),
            insurance_cost=self._money(row["insurance_cost"]),
            transportation_cost=self._money(row["transportation_cost"]),
            communication_cost=self._money(row["communication_cost"]),
            other_expenses=self._money(row.get("other_expenses", 0)),
            metadata=dict(row.get("metadata", {})),
        )

    @staticmethod
    def _validate_unique_staff_ids(staff: list[StaffMember]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for member in staff:
            if member.unique_id in seen:
                duplicates.add(member.unique_id)
            seen.add(member.unique_id)
        if duplicates:
            raise ValueError(f"Duplicate staff unique_id values: {', '.join(sorted(duplicates))}")

    @staticmethod
    def _money(value: Any) -> float:
        return (
            round(float(str(value).replace("$", "").replace(",", "")), 2)
            if value not in (None, "")
            else 0.0
        )


def serialize_staff(member: StaffMember) -> dict[str, Any]:
    """Return a JSON-safe staff dictionary for dashboards and tests."""
    return asdict(member)
