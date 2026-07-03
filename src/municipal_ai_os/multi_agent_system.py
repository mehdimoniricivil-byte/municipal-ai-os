"""Multi-agent coordination system for Municipal AI OS.

The coordinator is intentionally deterministic and file-backed: it can be used
by tests, local CLI runs, or a future service layer while preserving a complete
audit trail of agent messages, tasks, decisions, and results.
"""

from __future__ import annotations

import heapq
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AGENT_DEFINITIONS = {
    "collection": {
        "name": "Collection Agent",
        "goals": [
            "Recover municipal debt efficiently",
            "Generate debtor-level collection recommendations",
            "Escalate cases needing call center, legal, field, or manager action",
        ],
    },
    "call_center": {
        "name": "Call Center Agent",
        "goals": [
            "Contact taxpayers by phone",
            "Record promises to pay and failed contact attempts",
            "Request negotiation or escalation when calls reveal new risk",
        ],
    },
    "legal": {
        "name": "Legal Agent",
        "goals": [
            "Prepare legally actionable debt cases",
            "Evaluate Commission 77 escalation readiness",
            "Report legal blockers and required documentation",
        ],
    },
    "field_inspection": {
        "name": "Field Inspection Agent",
        "goals": [
            "Verify addresses and business operating status",
            "Run district field campaigns",
            "Report observations that change collection strategy",
        ],
    },
    "manager": {
        "name": "Manager Agent",
        "goals": [
            "Coordinate daily collector and specialist work",
            "Resolve cross-agent blockers",
            "Convert executive recommendations into accountable assignments",
        ],
    },
    "mayor": {
        "name": "Mayor Agent",
        "goals": [
            "Monitor municipality health and revenue forecast",
            "Set executive priorities",
            "Identify city-wide risks and policy opportunities",
        ],
    },
}


@dataclass(order=True)
class AgentTask:
    """A priority-ordered task assigned to one municipal AI agent."""

    sort_index: tuple[int, str] = field(init=False, repr=False)
    priority: int
    task_id: str
    assigned_to: str
    created_by: str
    title: str
    description: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
    context: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        self.sort_index = (self.priority, self.created_at)


@dataclass(frozen=True)
class AgentMessage:
    """A persisted communication between agents."""

    message_id: str
    sender: str
    recipient: str
    content: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    related_task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentDecision:
    """A persisted decision made by an agent."""

    decision_id: str
    agent_id: str
    summary: str
    reasoning: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    related_task_id: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    """A result reported after an agent executes or advances a task."""

    result_id: str
    agent_id: str
    task_id: str
    outcome: str
    details: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MunicipalAgent:
    """Independent municipal AI agent with goals, memory, tasks, and reporting."""

    def __init__(self, agent_id: str, name: str, goals: list[str], coordinator: "AgentCoordinator") -> None:
        self.agent_id = agent_id
        self.name = name
        self.goals = goals
        self.coordinator = coordinator
        self.memory: list[dict[str, Any]] = []
        self._queue: list[AgentTask] = []
        self.completed_tasks: list[AgentTask] = []

    @property
    def assigned_tasks(self) -> list[AgentTask]:
        return sorted(self._queue)

    def remember(self, memory_type: str, content: dict[str, Any]) -> None:
        entry = {
            "agent_id": self.agent_id,
            "memory_type": memory_type,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.memory.append(entry)
        self.coordinator.store_memory(entry)

    def assign_task(self, task: AgentTask) -> None:
        heapq.heappush(self._queue, task)
        self.remember("task_assigned", asdict(task))

    def create_task_for(
        self,
        assigned_to: str,
        title: str,
        description: str,
        priority: int = 5,
        context: dict[str, Any] | None = None,
    ) -> AgentTask:
        return self.coordinator.create_task(
            created_by=self.agent_id,
            assigned_to=assigned_to,
            title=title,
            description=description,
            priority=priority,
            context=context or {},
        )

    def send_message(
        self,
        recipient: str,
        content: str,
        related_task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        return self.coordinator.send_message(
            sender=self.agent_id,
            recipient=recipient,
            content=content,
            related_task_id=related_task_id,
            metadata=metadata or {},
        )

    def record_decision(
        self,
        summary: str,
        reasoning: str,
        related_task_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> AgentDecision:
        return self.coordinator.record_decision(
            agent_id=self.agent_id,
            summary=summary,
            reasoning=reasoning,
            related_task_id=related_task_id,
            evidence=evidence or {},
        )

    def report_result(self, task_id: str, outcome: str, details: dict[str, Any]) -> AgentResult:
        result = self.coordinator.report_result(self.agent_id, task_id, outcome, details)
        self.remember("result_reported", asdict(result))
        return result

    def pop_next_task(self) -> AgentTask | None:
        if not self._queue:
            return None
        task = heapq.heappop(self._queue)
        task.status = "in_progress"
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self.remember("task_started", asdict(task))
        return task

    def complete_task(self, task: AgentTask, outcome: str, details: dict[str, Any]) -> AgentResult:
        task.status = "completed"
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self.completed_tasks.append(task)
        self.coordinator.persist_task(task)
        return self.report_result(task.task_id, outcome, details)


class AgentCoordinator:
    """Coordinates communication, task routing, memory, and audit persistence."""

    def __init__(self, workspace: str | Path = "var/multi_agent_system") -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.agents = {
            agent_id: MunicipalAgent(agent_id, definition["name"], definition["goals"], self)
            for agent_id, definition in AGENT_DEFINITIONS.items()
        }
        self.tasks: dict[str, AgentTask] = {}

    def create_task(
        self,
        created_by: str,
        assigned_to: str,
        title: str,
        description: str,
        priority: int = 5,
        context: dict[str, Any] | None = None,
    ) -> AgentTask:
        self._require_agent(created_by)
        assignee = self._require_agent(assigned_to)
        task = AgentTask(
            priority=priority,
            task_id=f"task-{uuid.uuid4().hex[:12]}",
            assigned_to=assigned_to,
            created_by=created_by,
            title=title,
            description=description,
            context=context or {},
        )
        self.tasks[task.task_id] = task
        assignee.assign_task(task)
        self.persist_task(task)
        self._append_jsonl("decisions.jsonl", {
            "event": "task_created",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "task": asdict(task),
        })
        return task

    def send_message(
        self,
        sender: str,
        recipient: str,
        content: str,
        related_task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        self._require_agent(sender)
        recipient_agent = self._require_agent(recipient)
        message = AgentMessage(
            message_id=f"msg-{uuid.uuid4().hex[:12]}",
            sender=sender,
            recipient=recipient,
            content=content,
            related_task_id=related_task_id,
            metadata=metadata or {},
        )
        self.agents[sender].remember("message_sent", asdict(message))
        recipient_agent.remember("message_received", asdict(message))
        self._append_jsonl("conversations.jsonl", asdict(message))
        return message

    def record_decision(
        self,
        agent_id: str,
        summary: str,
        reasoning: str,
        related_task_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> AgentDecision:
        self._require_agent(agent_id)
        decision = AgentDecision(
            decision_id=f"decision-{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            summary=summary,
            reasoning=reasoning,
            related_task_id=related_task_id,
            evidence=evidence or {},
        )
        self.agents[agent_id].remember("decision", asdict(decision))
        self._append_jsonl("decisions.jsonl", asdict(decision))
        return decision

    def report_result(self, agent_id: str, task_id: str, outcome: str, details: dict[str, Any]) -> AgentResult:
        self._require_agent(agent_id)
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task: {task_id}")
        result = AgentResult(
            result_id=f"result-{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            task_id=task_id,
            outcome=outcome,
            details=details,
        )
        self._append_jsonl("results.jsonl", asdict(result))
        return result

    def store_memory(self, entry: dict[str, Any]) -> None:
        self._append_jsonl("memory.jsonl", entry)

    def persist_task(self, task: AgentTask) -> None:
        task_dir = self.workspace / "tasks"
        task_dir.mkdir(exist_ok=True)
        (task_dir / f"{task.task_id}.json").write_text(json.dumps(asdict(task), indent=2, sort_keys=True))

    def run_next_task(self, agent_id: str) -> AgentResult | None:
        agent = self._require_agent(agent_id)
        task = agent.pop_next_task()
        if task is None:
            return None
        decision = agent.record_decision(
            summary=f"Execute task: {task.title}",
            reasoning=f"This task supports goals: {', '.join(agent.goals)}.",
            related_task_id=task.task_id,
            evidence={"priority": task.priority, "created_by": task.created_by},
        )
        agent.send_message(
            recipient=task.created_by,
            content=f"{agent.name} is executing '{task.title}'. Decision: {decision.summary}",
            related_task_id=task.task_id,
        )
        return agent.complete_task(
            task,
            outcome="completed",
            details={"decision_id": decision.decision_id, "agent": agent.name},
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            agent_id: {
                "name": agent.name,
                "goals": agent.goals,
                "memory_count": len(agent.memory),
                "queued_tasks": [asdict(task) for task in agent.assigned_tasks],
                "completed_tasks": [asdict(task) for task in agent.completed_tasks],
            }
            for agent_id, agent in self.agents.items()
        }

    def _append_jsonl(self, filename: str, payload: dict[str, Any]) -> None:
        with (self.workspace / filename).open("a") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _require_agent(self, agent_id: str) -> MunicipalAgent:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"Unknown agent: {agent_id}") from exc


def build_default_coordinator(workspace: str | Path = "var/multi_agent_system") -> AgentCoordinator:
    """Create the default six-agent municipal coordination system."""
    return AgentCoordinator(workspace)
