import json

from municipal_ai_os.multi_agent_system import AGENT_DEFINITIONS, build_default_coordinator


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_default_agents_have_goals_memory_tasks_and_reporting(tmp_path):
    coordinator = build_default_coordinator(tmp_path)

    assert set(coordinator.agents) == set(AGENT_DEFINITIONS)
    assert all(agent.goals for agent in coordinator.agents.values())

    task = coordinator.agents["collection"].create_task_for(
        assigned_to="call_center",
        title="Call high-value taxpayer",
        description="Attempt same-day contact and report promise-to-pay status.",
        priority=1,
        context={"debtor": "Jane Doe", "amount": 2500},
    )
    coordinator.agents["collection"].send_message(
        "call_center",
        "Please prioritize this taxpayer before noon.",
        related_task_id=task.task_id,
    )

    result = coordinator.run_next_task("call_center")

    assert result is not None
    assert result.task_id == task.task_id
    assert result.outcome == "completed"
    assert coordinator.agents["call_center"].completed_tasks[0].task_id == task.task_id
    assert coordinator.agents["call_center"].memory
    assert (tmp_path / "conversations.jsonl").exists()
    assert (tmp_path / "decisions.jsonl").exists()
    assert (tmp_path / "results.jsonl").exists()
    assert (tmp_path / "memory.jsonl").exists()

    conversations = read_jsonl(tmp_path / "conversations.jsonl")
    assert {message["sender"] for message in conversations} == {"collection", "call_center"}
    decisions = read_jsonl(tmp_path / "decisions.jsonl")
    assert any(entry.get("agent_id") == "call_center" for entry in decisions)


def test_priority_queue_runs_highest_priority_first(tmp_path):
    coordinator = build_default_coordinator(tmp_path)
    manager = coordinator.agents["manager"]
    low = manager.create_task_for("legal", "Low priority review", "Review when time allows", priority=9)
    high = manager.create_task_for("legal", "Commission 77 packet", "Prepare immediately", priority=1)

    first = coordinator.agents["legal"].pop_next_task()

    assert first.task_id == high.task_id
    assert first.priority < low.priority
