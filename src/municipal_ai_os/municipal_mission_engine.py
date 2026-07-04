"""Rules-based municipal mission generation.

The engine is intentionally deterministic: it turns existing collection
recommendations into manager-readable missions without sending messages,
changing finances, attributing field activity, or replacing the organization
engine.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_RULES_PATH = Path(__file__).with_name("municipal_mission_rules.json")


@dataclass(frozen=True)
class MissionContext:
    run_id: str
    recommendations: list[dict[str, Any]]
    scored_records: list[dict[str, Any]]


class MunicipalMissionEngine:
    """Build mission outputs from collection recommendations using JSON rules."""

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
        self.rules = json.loads(self.rules_path.read_text(encoding="utf-8"))

    def build(self, context: MissionContext) -> dict[str, Any]:
        missions: list[dict[str, Any]] = []
        missions.extend(self._high_value_missions(context))
        missions.extend(self._field_campaign_missions(context))
        missions.extend(self._legal_readiness_missions(context))
        missions.extend(self._collector_focus_missions(context))
        missions = sorted(missions, key=self._mission_sort_key)
        dashboard = self._dashboard(context.run_id, missions)
        return {
            "municipal_missions": missions,
            "municipal_mission_dashboard": dashboard,
            "human_readable_manager_report": self._manager_report(dashboard, missions),
        }

    def _high_value_missions(self, context: MissionContext) -> list[dict[str, Any]]:
        threshold = float(self.rules["high_value_debt_threshold"])
        records = [r for r in context.recommendations if r.get("debt_amount", 0) >= threshold]
        if not records:
            return []
        return [self._mission("high_value_recovery", records, "citywide")]

    def _field_campaign_missions(self, context: MissionContext) -> list[dict[str, Any]]:
        by_zone: dict[str, list[dict[str, Any]]] = {}
        for record in context.recommendations:
            if record.get("recommended_action") != "FIELD_VISIT":
                continue
            by_zone.setdefault(str(record.get("zone") or record.get("region") or "Unassigned"), []).append(record)
        missions = []
        case_threshold = int(self.rules["field_campaign_case_threshold"])
        debt_threshold = float(self.rules["field_campaign_debt_threshold"])
        for zone, records in by_zone.items():
            if len(records) >= case_threshold or sum(r.get("debt_amount", 0) for r in records) >= debt_threshold:
                missions.append(self._mission("field_campaign", records, zone))
        return missions

    def _legal_readiness_missions(self, context: MissionContext) -> list[dict[str, Any]]:
        statuses = {str(status).lower() for status in self.rules["legal_statuses"]}
        by_status = [
            rec
            for rec in context.recommendations
            if rec.get("recommended_action") == "LEGAL"
            or str(rec.get("legal_status", "")).lower() in statuses
        ]
        return [self._mission("legal_readiness", by_status, "legal")] if by_status else []

    def _collector_focus_missions(self, context: MissionContext) -> list[dict[str, Any]]:
        by_collector: dict[str, list[dict[str, Any]]] = {}
        for record in context.recommendations:
            if record.get("priority") in {"high", "medium"}:
                by_collector.setdefault(str(record.get("collector") or "Unassigned"), []).append(record)
        return [
            self._mission("collector_focus", records, collector)
            for collector, records in by_collector.items()
            if len(records) >= 2
        ]

    def _mission(self, template_key: str, records: list[dict[str, Any]], scope: str) -> dict[str, Any]:
        template = self.rules["mission_templates"][template_key]
        debt_amount = round(sum(float(record.get("debt_amount", 0)) for record in records), 2)
        priority = template["default_priority"]
        mission_id = hashlib.sha256(
            f"{template_key}|{scope}|{','.join(sorted(str(r.get('record_id')) for r in records))}".encode()
        ).hexdigest()[:16]
        return {
            "mission_id": mission_id,
            "mission_type": template_key,
            "scope": scope,
            "title_fa": template["title_fa"],
            "objective_fa": template["objective_fa"],
            "owner_role": template["owner_role"],
            "priority": priority,
            "case_count": len(records),
            "debt_amount": debt_amount,
            "target_record_ids": [record.get("record_id") for record in records],
            "recommended_actions": sorted({str(record.get("recommended_action")) for record in records}),
            "generated_date": date.today().isoformat(),
            "recommendation_only": True,
        }

    def _dashboard(self, run_id: str, missions: list[dict[str, Any]]) -> dict[str, Any]:
        by_priority: dict[str, int] = {}
        by_owner: dict[str, int] = {}
        for mission in missions:
            by_priority[mission["priority"]] = by_priority.get(mission["priority"], 0) + 1
            by_owner[mission["owner_role"]] = by_owner.get(mission["owner_role"], 0) + 1
        return {
            "run_id": run_id,
            "date": date.today().isoformat(),
            "recommendation_only": True,
            "mission_count": len(missions),
            "total_target_debt": round(sum(mission["debt_amount"] for mission in missions), 2),
            "missions_by_priority": by_priority,
            "missions_by_owner_role": by_owner,
        }

    def _manager_report(self, dashboard: dict[str, Any], missions: list[dict[str, Any]]) -> str:
        lines = [
            "# گزارش ماموریت‌های روزانه شهرداری",
            "",
            f"تاریخ: {dashboard['date']}",
            f"تعداد ماموریت‌ها: {dashboard['mission_count']}",
            f"مبلغ هدف: {dashboard['total_target_debt']}",
            "",
            "## ماموریت‌ها",
        ]
        if not missions:
            lines.append("- امروز ماموریت جدیدی بر اساس قواعد تعریف‌شده تولید نشد.")
        for mission in missions:
            lines.append(
                "- "
                f"{mission['title_fa']} | اولویت: {mission['priority']} | "
                f"مسئول: {mission['owner_role']} | پرونده‌ها: {mission['case_count']} | "
                f"مبلغ: {mission['debt_amount']} | دامنه: {mission['scope']}"
            )
            lines.append(f"  - هدف: {mission['objective_fa']}")
        lines.extend(["", "یادداشت: این خروجی فقط توصیه‌ای است و هیچ اقدام اجرایی ارسال نشده است."])
        return "\n".join(lines) + "\n"

    def _mission_sort_key(self, mission: dict[str, Any]) -> tuple[int, float, str]:
        order = self.rules.get("priority_order", [])
        priority_rank = order.index(mission["priority"]) if mission["priority"] in order else len(order)
        return (priority_rank, -float(mission["debt_amount"]), mission["mission_id"])
