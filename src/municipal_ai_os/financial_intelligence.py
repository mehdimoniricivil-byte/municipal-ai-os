"""Financial intelligence dashboard for municipal collection performance."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from municipal_ai_os.organization_engine import OrganizationEngine

DEFAULT_FINANCIAL_RULES: dict[str, Any] = {
    "contract_commission_rate": 0.12,
    "regions": {},
    "unusual_cost_increase_ratio": 0.25,
    "low_margin_threshold": 0.1,
    "high_cost_to_revenue_threshold": 0.85,
}

COMPARISON_WINDOWS = {
    "last_7_days": 7,
    "last_30_days": 30,
}


@dataclass(frozen=True)
class RegionFinancialRecord:
    """Immutable daily financial result preserved per municipality region."""

    date: str
    run_id: str
    municipality: str
    region: str
    zones: list[str]
    daily_collection_amount: float
    contract_commission_rate: float
    company_revenue: float
    staff_count: int
    staff_member_ids: list[str]
    cost_centers: list[str]
    salary: float
    insurance_cost: float
    transportation_cost: float
    communication_cost: float
    other_expenses: float
    total_staff_cost: float
    total_operational_cost: float
    total_cost: float
    net_profit: float
    profit_margin: float
    cost_to_revenue_ratio: float
    collector_count: int
    profit_per_collector: float
    profit_per_billion_collected: float
    roi: float
    source: str = "daily_collection_snapshot"
    recommendation_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class FinancialIntelligenceDashboard:
    """Builds a historical, file-backed financial dashboard by region."""

    def __init__(
        self,
        workspace: str | Path,
        config_path: str | Path = "config/financial_rules.json",
        organization_path: str | Path = "config/organization_model.json",
    ) -> None:
        self.workspace = Path(workspace)
        self.history_dir = self.workspace / "state" / "financial_history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = Path(config_path)
        self.organization = OrganizationEngine(self.workspace, organization_path)

    def build(
        self,
        *,
        run_id: str,
        current_snapshot: list[dict[str, Any]],
        previous_snapshot: list[dict[str, Any]] | None = None,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        day = as_of or date.today()
        rules = self._load_rules()
        organization_snapshot = self.organization.snapshot(run_id)
        records = self._region_records(
            run_id, day, current_snapshot, previous_snapshot or [], rules
        )
        self._preserve_history(records)
        history = self._load_history()
        comparisons = self._comparisons(records, history, day)
        comments = self._ai_comments(records, comparisons, rules)
        dashboard = {
            "date": day.isoformat(),
            "run_id": run_id,
            "regions": [asdict(record) for record in records],
            "comparisons": comparisons,
            "ai_financial_comments": comments,
            "organization_snapshot": organization_snapshot,
            "recommendation_only": True,
            "history_files": [str(self.history_dir / f"{record.date}.jsonl") for record in records],
        }
        return dashboard

    def _region_records(
        self,
        run_id: str,
        day: date,
        current_snapshot: list[dict[str, Any]],
        previous_snapshot: list[dict[str, Any]],
        rules: dict[str, Any],
    ) -> list[RegionFinancialRecord]:
        previous_by_debtor = {record["debtor_id"]: record for record in previous_snapshot}
        current_ids = {record["debtor_id"] for record in current_snapshot}
        collections: dict[str, float] = {}
        collectors: dict[str, set[str]] = {}
        organization_costs = self.organization.aggregate_region_costs()
        known_regions = self.organization.known_regions()
        all_regions = {str(record.get("region") or "Unassigned") for record in current_snapshot}
        all_regions.update(
            str(record.get("region") or "Unassigned") for record in previous_snapshot
        )
        all_regions.update(str(region) for region in rules.get("regions", {}))
        all_regions.update(organization_costs)
        all_regions.update(known_regions)
        for record in current_snapshot:
            region = str(record.get("region") or "Unassigned")
            collectors.setdefault(region, set()).add(
                str(record.get("assigned_collector") or "Unassigned")
            )
            before = previous_by_debtor.get(record["debtor_id"])
            if before:
                collected = max(
                    0.0, float(before.get("debt_amount", 0)) - float(record.get("debt_amount", 0))
                )
            else:
                collected = float(record.get("collected_amount", 0) or 0)
            collections[region] = round(collections.get(region, 0.0) + collected, 2)
        for record in previous_snapshot:
            if record["debtor_id"] not in current_ids:
                region = str(record.get("region") or "Unassigned")
                collections[region] = round(
                    collections.get(region, 0.0) + float(record.get("debt_amount", 0)), 2
                )
        return [
            self._record_for_region(
                run_id,
                day,
                region,
                collections.get(region, 0.0),
                len(collectors.get(region, set())),
                rules,
                organization_costs.get(region, {}),
                known_regions.get(region, {}),
            )
            for region in sorted(all_regions)
        ]

    def _record_for_region(
        self,
        run_id: str,
        day: date,
        region: str,
        collected: float,
        collector_count: int,
        rules: dict[str, Any],
        organization_costs: dict[str, Any],
        known_region: dict[str, Any],
    ) -> RegionFinancialRecord:
        region_rules = rules.get("regions", {}).get(region, {})
        commission = float(
            region_rules.get("contract_commission_rate", rules.get("contract_commission_rate", 0))
        )
        revenue = round(collected * commission, 2)
        total_staff_cost = self._money(organization_costs.get("total_staff_cost", 0))
        total_operational_cost = total_staff_cost
        total_cost = total_operational_cost
        net_profit = round(revenue - total_cost, 2)
        effective_collector_count = (
            int(organization_costs.get("collector_count", 0)) or collector_count
        )
        return RegionFinancialRecord(
            date=day.isoformat(),
            run_id=run_id,
            municipality=str(
                organization_costs.get("municipality")
                or known_region.get("municipality")
                or "Unassigned"
            ),
            region=region,
            zones=list(organization_costs.get("zones") or known_region.get("zones") or []),
            daily_collection_amount=round(collected, 2),
            contract_commission_rate=commission,
            company_revenue=revenue,
            staff_count=int(organization_costs.get("staff_count", 0)),
            staff_member_ids=list(organization_costs.get("staff_member_ids", [])),
            cost_centers=list(organization_costs.get("cost_centers", [])),
            salary=self._money(organization_costs.get("salary", 0)),
            insurance_cost=self._money(organization_costs.get("insurance_cost", 0)),
            transportation_cost=self._money(organization_costs.get("transportation_cost", 0)),
            communication_cost=self._money(organization_costs.get("communication_cost", 0)),
            other_expenses=self._money(organization_costs.get("other_expenses", 0)),
            total_staff_cost=total_staff_cost,
            total_operational_cost=total_operational_cost,
            total_cost=total_cost,
            net_profit=net_profit,
            profit_margin=self._ratio(net_profit, revenue),
            cost_to_revenue_ratio=self._ratio(total_cost, revenue),
            collector_count=effective_collector_count,
            profit_per_collector=self._ratio(net_profit, effective_collector_count),
            profit_per_billion_collected=round((net_profit / collected) * 1_000_000_000, 2)
            if collected
            else 0.0,
            roi=self._ratio(net_profit, total_cost),
        )

    def _comparisons(
        self, records: list[RegionFinancialRecord], history: list[dict[str, Any]], day: date
    ) -> dict[str, Any]:
        current = {record.region: asdict(record) for record in records}
        return {
            region: self._region_comparison(today, history, day)
            for region, today in current.items()
        }

    def _region_comparison(
        self, today: dict[str, Any], history: list[dict[str, Any]], day: date
    ) -> dict[str, Any]:
        region_history = [row for row in history if row["region"] == today["region"]]
        prior = [
            row
            for row in region_history
            if row["date"] < today["date"] or row["run_id"] != today["run_id"]
        ]
        previous_run = prior[-1] if prior else None
        yesterday = next(
            (
                row
                for row in reversed(prior)
                if row["date"] == (day - timedelta(days=1)).isoformat()
            ),
            None,
        )
        comparison = {
            "yesterday": self._delta(today, yesterday),
            "previous_run": self._delta(today, previous_run),
            "current_month": self._aggregate_delta(
                today, prior, lambda d: d.year == day.year and d.month == day.month
            ),
            "year_to_date": self._aggregate_delta(today, prior, lambda d: d.year == day.year),
        }
        for name, days in COMPARISON_WINDOWS.items():
            start = day - timedelta(days=days)
            comparison[name] = self._aggregate_delta(
                today, prior, lambda d, start=start: start <= d < day
            )
        return comparison

    def _aggregate_delta(
        self, today: dict[str, Any], prior: list[dict[str, Any]], predicate: Any
    ) -> dict[str, Any]:
        rows = [row for row in prior if predicate(date.fromisoformat(row["date"]))]
        aggregate = {
            "daily_collection_amount": 0.0,
            "company_revenue": 0.0,
            "total_cost": 0.0,
            "net_profit": 0.0,
        }
        for row in rows:
            for key in aggregate:
                aggregate[key] = round(aggregate[key] + float(row.get(key, 0)), 2)
        aggregate["record_count"] = len(rows)
        aggregate["average_net_profit"] = self._ratio(aggregate["net_profit"], len(rows))
        aggregate["delta_vs_today_net_profit"] = round(
            today["net_profit"] - aggregate["average_net_profit"], 2
        )
        return aggregate

    @staticmethod
    def _delta(today: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
        if not baseline:
            return {"available": False}
        return {
            "available": True,
            **{
                f"{key}_delta": round(float(today[key]) - float(baseline.get(key, 0)), 2)
                for key in [
                    "daily_collection_amount",
                    "company_revenue",
                    "total_cost",
                    "net_profit",
                ]
            },
        }

    def _ai_comments(
        self,
        records: list[RegionFinancialRecord],
        comparisons: dict[str, Any],
        rules: dict[str, Any],
    ) -> list[dict[str, Any]]:
        comments = []
        if records:
            best = max(records, key=lambda row: row.net_profit)
            comments.append(
                {
                    "recommendation_only": True,
                    "type": "profitable_region",
                    "region": best.region,
                    "comment": f"{best.region} is the most profitable region with net profit {best.net_profit:.2f} and margin {best.profit_margin:.2%}.",
                }
            )
        for record in records:
            if record.profit_margin < float(rules.get("low_margin_threshold", 0.1)):
                comments.append(
                    {
                        "recommendation_only": True,
                        "type": "inefficient_staff_allocation",
                        "region": record.region,
                        "comment": f"{record.region} has low profit margin ({record.profit_margin:.2%}) while carrying {record.staff_count} active staff; review assignments before changing any roster.",
                    }
                )
            if record.cost_to_revenue_ratio > float(
                rules.get("high_cost_to_revenue_threshold", 0.85)
            ):
                comments.append(
                    {
                        "recommendation_only": True,
                        "type": "staff_reallocation_opportunity",
                        "region": record.region,
                        "comment": f"{record.region} spends {record.cost_to_revenue_ratio:.2%} of revenue on staff-driven operational costs; consider whether staff could be reassigned to higher-profit regions, but do not modify assignments automatically.",
                    }
                )
            previous = comparisons[record.region]["previous_run"]
            if previous.get("available") and previous.get(
                "total_cost_delta", 0
            ) > record.total_cost * float(rules.get("unusual_cost_increase_ratio", 0.25)):
                comments.append(
                    {
                        "recommendation_only": True,
                        "type": "unusual_cost_increase",
                        "region": record.region,
                        "comment": f"{record.region} shows an unusual cost increase of {previous['total_cost_delta']:.2f} versus the previous run.",
                    }
                )
        comments.extend(self._staff_mobility_recommendations(records))
        return comments

    def _staff_mobility_recommendations(
        self, records: list[RegionFinancialRecord]
    ) -> list[dict[str, Any]]:
        if len(records) < 2:
            return []
        inefficient = [record for record in records if record.staff_count and record.net_profit < 0]
        profitable = [record for record in records if record.net_profit > 0]
        if not inefficient or not profitable:
            return []
        best = max(profitable, key=lambda record: record.profit_per_collector)
        return [
            {
                "recommendation_only": True,
                "type": "cross_region_staff_reallocation",
                "region": record.region,
                "target_region": best.region,
                "comment": f"Review whether one collector or support staff member from {record.region} could support {best.region}, where profit per collector is {best.profit_per_collector:.2f}; this is recommendation-only and no assignment was changed.",
            }
            for record in inefficient
            if best.region != record.region
        ]

    def _preserve_history(self, records: list[RegionFinancialRecord]) -> None:
        for record in records:
            path = self.history_dir / f"{record.date}.jsonl"
            with path.open("a") as handle:
                handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")

    def _load_history(self) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(self.history_dir.glob("*.jsonl")):
            rows.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
        return rows

    def _load_rules(self) -> dict[str, Any]:
        rules = json.loads(json.dumps(DEFAULT_FINANCIAL_RULES))
        if self.config_path.exists():
            configured = json.loads(self.config_path.read_text())
            rules.update(configured)
        return rules

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    @staticmethod
    def _money(value: Any) -> float:
        return (
            round(float(str(value).replace("$", "").replace(",", "")), 2)
            if value not in (None, "")
            else 0.0
        )
