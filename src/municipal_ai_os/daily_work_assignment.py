"""Daily Work Assignment Engine for recommended municipal work allocation.

The engine is intentionally file based and side-effect safe: it only reads queue
artifacts plus configurable JSON rules, then writes recommended assignment JSON
outputs. It never sends messages, contacts debtors, or performs field actions.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


INPUT_FILES = {
    "priority_report": "priority_report.json",
    "calls": "daily_call_queue.json",
    "visits": "daily_visit_queue.json",
    "notices": "daily_notice_queue.json",
    "legal": "legal_queue.json",
}

OUTPUT_FILES = {
    "assignments": "agent_assignments.json",
    "schedule": "daily_agent_schedule.json",
    "summary": "workload_summary.json",
    "dashboard": "manager_assignment_dashboard.json",
}

DEFAULT_RULES: dict[str, Any] = {
    "schedule_date": None,
    "task_type_order": ["FIELD_VISIT", "CALL", "NOTICE", "LEGAL"],
    "priority_order": ["critical", "high", "medium", "low"],
    "balance_weight": 1.0,
    "zone_match_bonus": 2.5,
    "default_agents": [
        {
            "agent_id": "call_agent_1",
            "name": "Call Agent 1",
            "roles": ["CALL"],
            "available": True,
            "max_calls_per_day": 60,
            "max_visits_per_day": 0,
            "max_notices_per_day": 0,
            "max_legal_per_day": 0,
        },
        {
            "agent_id": "call_agent_2",
            "name": "Call Agent 2",
            "roles": ["CALL"],
            "available": True,
            "max_calls_per_day": 60,
            "max_visits_per_day": 0,
            "max_notices_per_day": 0,
            "max_legal_per_day": 0,
        },
        {
            "agent_id": "field_agent_1",
            "name": "Field Agent 1",
            "roles": ["FIELD_VISIT", "NOTICE"],
            "available": True,
            "zones": [],
            "max_calls_per_day": 0,
            "max_visits_per_day": 25,
            "max_notices_per_day": 40,
            "max_legal_per_day": 0,
        },
        {
            "agent_id": "legal_agent_1",
            "name": "Legal Agent 1",
            "roles": ["LEGAL"],
            "available": True,
            "max_calls_per_day": 0,
            "max_visits_per_day": 0,
            "max_notices_per_day": 0,
            "max_legal_per_day": 30,
        },
    ],
}

CAPACITY_FIELD_BY_TYPE = {
    "CALL": "max_calls_per_day",
    "FIELD_VISIT": "max_visits_per_day",
    "NOTICE": "max_notices_per_day",
    "LEGAL": "max_legal_per_day",
}

COUNT_FIELD_BY_TYPE = {
    "CALL": "calls",
    "FIELD_VISIT": "visits",
    "NOTICE": "notices",
    "LEGAL": "legal",
}


@dataclass
class AgentLoad:
    agent: dict[str, Any]
    assignments: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(
        default_factory=lambda: {"calls": 0, "visits": 0, "notices": 0, "legal": 0}
    )

    @property
    def agent_id(self) -> str:
        return str(self.agent["agent_id"])

    def capacity_for(self, task_type: str) -> int:
        return int(self.agent.get(CAPACITY_FIELD_BY_TYPE[task_type], 0) or 0)

    def count_for(self, task_type: str) -> int:
        return self.counts[COUNT_FIELD_BY_TYPE[task_type]]

    def has_capacity_for(self, task_type: str) -> bool:
        roles = {str(role).upper() for role in self.agent.get("roles", [])}
        return (
            bool(self.agent.get("available", True))
            and task_type in roles
            and self.count_for(task_type) < self.capacity_for(task_type)
        )

    def add(self, task: dict[str, Any]) -> None:
        task_type = task["task_type"]
        self.counts[COUNT_FIELD_BY_TYPE[task_type]] += 1
        self.assignments.append(task)

    def utilization_for(self, task_type: str) -> float:
        capacity = self.capacity_for(task_type)
        if capacity <= 0:
            return 1.0
        return self.count_for(task_type) / capacity

    def total_utilization(self) -> float:
        capacities = [self.capacity_for(kind) for kind in CAPACITY_FIELD_BY_TYPE]
        total_capacity = sum(capacities)
        if total_capacity <= 0:
            return 1.0
        return sum(self.counts.values()) / total_capacity


class DailyWorkAssignmentEngine:
    """Generate recommended daily assignments without executing work."""

    def __init__(self, workspace: str | Path, rules_path: str | Path | None = None) -> None:
        self.workspace = Path(workspace)
        self.rules_path = Path(rules_path) if rules_path else self.workspace / "assignment_rules.json"

    def run(self) -> dict[str, Any]:
        rules = self._load_rules()
        priority_report = self._read_json(INPUT_FILES["priority_report"], default={})
        tasks = self._load_tasks(priority_report, rules)
        agents = [AgentLoad(agent) for agent in rules.get("agents", rules["default_agents"])]

        unassigned: list[dict[str, Any]] = []
        for task in tasks:
            selected = self._select_agent(task, agents, rules)
            if selected is None:
                unassigned.append({**task, "unassigned_reason": self._unassigned_reason(task, agents)})
                continue
            selected.add(
                {
                    **task,
                    "assigned_agent_id": selected.agent_id,
                    "assigned_agent_name": selected.agent.get("name", selected.agent_id),
                }
            )

        outputs = self._build_outputs(agents, unassigned, rules, priority_report)
        self.workspace.mkdir(parents=True, exist_ok=True)
        for key, filename in OUTPUT_FILES.items():
            output = json.dumps(outputs[key], indent=2, sort_keys=True) + "\n"
            (self.workspace / filename).write_text(output)
        return outputs

    def _load_rules(self) -> dict[str, Any]:
        rules = json.loads(json.dumps(DEFAULT_RULES))
        if self.rules_path.exists():
            configured = json.loads(self.rules_path.read_text())
            rules.update(configured)
        if "agents" not in rules:
            rules["agents"] = rules["default_agents"]
        return rules

    def _read_json(self, filename: str, default: Any) -> Any:
        path = self.workspace / filename
        return json.loads(path.read_text()) if path.exists() else default

    def _load_tasks(self, priority_report: dict[str, Any], rules: dict[str, Any]) -> list[dict[str, Any]]:
        priority_index = self._priority_index(priority_report)
        tasks: list[dict[str, Any]] = []
        for key, task_type in [
            ("calls", "CALL"),
            ("visits", "FIELD_VISIT"),
            ("notices", "NOTICE"),
            ("legal", "LEGAL"),
        ]:
            raw = self._read_json(INPUT_FILES[key], default=[])
            for position, item in enumerate(self._extract_items(raw)):
                normalized = self._normalize_task(item, task_type, position, priority_index)
                tasks.append(normalized)
        priority_order = {p: i for i, p in enumerate(rules.get("priority_order", []))}
        type_order = {t: i for i, t in enumerate(rules.get("task_type_order", []))}
        tasks.sort(
            key=lambda t: (
                priority_order.get(t["priority"], 999),
                type_order.get(t["task_type"], 999),
                t["source_position"],
            )
        )
        return tasks

    @staticmethod
    def _extract_items(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            for key in ("tasks", "queue", "items", "records", "cases"):
                if isinstance(raw.get(key), list):
                    return [item for item in raw[key] if isinstance(item, dict)]
            flattened: list[dict[str, Any]] = []
            for value in raw.values():
                if isinstance(value, list):
                    flattened.extend(item for item in value if isinstance(item, dict))
            return flattened
        return []

    @staticmethod
    def _priority_index(priority_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for item in DailyWorkAssignmentEngine._extract_items(priority_report):
            case_id = item.get("case_id") or item.get("record_id") or item.get("task_id")
            if case_id:
                index[str(case_id)] = item
        return index

    @staticmethod
    def _normalize_task(
        item: dict[str, Any],
        task_type: str,
        position: int,
        priority_index: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        task_id = str(
            item.get("task_id")
            or item.get("case_id")
            or item.get("record_id")
            or f"{task_type.lower()}-{position + 1}"
        )
        priority_key = str(item.get("case_id") or item.get("record_id") or task_id)
        priority_item = priority_index.get(priority_key, {})
        priority = str(item.get("priority") or priority_item.get("priority") or "medium").lower()
        zone = (
            item.get("zone")
            or item.get("district")
            or item.get("region")
            or item.get("neighborhood")
            or "unassigned"
        )
        return {
            **item,
            "task_id": task_id,
            "task_type": task_type,
            "priority": priority,
            "zone": str(zone),
            "source_position": position,
            "recommendation_only": True,
        }

    def _select_agent(
        self, task: dict[str, Any], agents: list[AgentLoad], rules: dict[str, Any]
    ) -> AgentLoad | None:
        candidates = [agent for agent in agents if agent.has_capacity_for(task["task_type"])]
        if not candidates:
            return None
        candidates.sort(key=lambda agent: self._agent_score(agent, task, rules))
        return candidates[0]

    @staticmethod
    def _agent_score(agent: AgentLoad, task: dict[str, Any], rules: dict[str, Any]) -> float:
        score = agent.utilization_for(task["task_type"]) * float(rules.get("balance_weight", 1.0))
        score += agent.total_utilization() * float(rules.get("balance_weight", 1.0))
        if task["task_type"] == "FIELD_VISIT":
            zones = {str(zone).lower() for zone in agent.agent.get("zones", [])}
            if zones and str(task.get("zone", "")).lower() in zones:
                score -= float(rules.get("zone_match_bonus", 2.5))
        return score

    @staticmethod
    def _unassigned_reason(task: dict[str, Any], agents: list[AgentLoad]) -> str:
        capable = [
            agent
            for agent in agents
            if task["task_type"] in {str(role).upper() for role in agent.agent.get("roles", [])}
        ]
        if not capable:
            return f"No available agent is configured for {task['task_type']} tasks."
        return f"All configured {task['task_type']} agents reached daily capacity."

    def _build_outputs(
        self,
        agents: list[AgentLoad],
        unassigned: list[dict[str, Any]],
        rules: dict[str, Any],
        priority_report: dict[str, Any],
    ) -> dict[str, Any]:
        schedule_date = rules.get("schedule_date") or date.today().isoformat()
        assignment_map = {
            load.agent_id: {
                "agent_id": load.agent_id,
                "agent_name": load.agent.get("name", load.agent_id),
                "roles": load.agent.get("roles", []),
                "zones": load.agent.get("zones", []),
                "capacities": {
                    field: load.agent.get(field, 0)
                    for field in CAPACITY_FIELD_BY_TYPE.values()
                },
                "assigned_counts": load.counts,
                "assignments": load.assignments,
            }
            for load in agents
        }
        total_counts = {
            key: sum(load.counts[key] for load in agents)
            for key in ("calls", "visits", "notices", "legal")
        }
        total_capacity = {
            key: sum(load.capacity_for(task_type) for load in agents)
            for task_type, key in COUNT_FIELD_BY_TYPE.items()
        }
        summary = {
            "schedule_date": schedule_date,
            "recommendation_only": True,
            "total_assigned": sum(total_counts.values()),
            "total_unassigned": len(unassigned),
            "assigned_by_type": total_counts,
            "capacity_by_type": total_capacity,
            "unassigned_by_type": self._count_by(unassigned, "task_type"),
            "agent_utilization": {
                load.agent_id: {
                    "total_utilization": round(load.total_utilization(), 4),
                    "calls_utilization": round(load.utilization_for("CALL"), 4),
                    "visits_utilization": round(load.utilization_for("FIELD_VISIT"), 4),
                    "notices_utilization": round(load.utilization_for("NOTICE"), 4),
                    "legal_utilization": round(load.utilization_for("LEGAL"), 4),
                }
                for load in agents
            },
        }
        dashboard = {
            "schedule_date": schedule_date,
            "status": "ready_for_manager_review",
            "recommendation_only": True,
            "rules_source": str(self.rules_path),
            "priority_report_loaded": bool(priority_report),
            "summary": summary,
            "unassigned_tasks": unassigned,
            "review_notes": ["Assignments are recommendations only; no messages or actions were sent."],
        }
        schedule = {
            "schedule_date": schedule_date,
            "recommendation_only": True,
            "agents": [
                {
                    "agent_id": load.agent_id,
                    "agent_name": load.agent.get("name", load.agent_id),
                    "task_sequence": load.assignments,
                }
                for load in agents
            ],
            "unassigned_tasks": unassigned,
        }
        return {
            "assignments": assignment_map,
            "schedule": schedule,
            "summary": summary,
            "dashboard": dashboard,
        }

    @staticmethod
    def _count_by(items: list[dict[str, Any]], field_name: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            key = str(item.get(field_name, "unknown"))
            counts[key] = counts.get(key, 0) + 1
        return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily Work Assignment Engine")
    parser.add_argument("run", nargs="?", default="run")
    parser.add_argument("--workspace", default="var/daily_work_assignment")
    parser.add_argument("--rules", default=None)
    args = parser.parse_args(argv)
    if args.run != "run":
        parser.error("Only the 'run' command is supported")
    DailyWorkAssignmentEngine(args.workspace, args.rules).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
