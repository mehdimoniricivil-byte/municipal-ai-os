# Autonomous Collection Agent v1

The Autonomous Collection Agent is a file-based worker that executes the daily municipal debt collection workflow. It can be run manually or as a long-running daily scheduler.

## Inputs

Place newly uploaded `.xlsx` or `.csv` files in:

```text
var/collection_agent/inbox/
```

Supported columns are normalized case-insensitively with spaces or dashes converted to underscores:

- `debtor`
- `address`
- `region`
- `collector`
- `debt_amount`
- `due_date` (ISO date recommended)
- `last_contact_date` (ISO date recommended)
- `status`

## Manual execution

```bash
python -m municipal_ai_os.collection_agent run --workspace var/collection_agent
```

## Daily scheduled execution

The built-in scheduler runs once per UTC day at the configured time and uses a lock file to prevent duplicate runs:

```bash
python -m municipal_ai_os.collection_agent schedule --workspace var/collection_agent --hour 6 --minute 0
```

This can be supervised by systemd, a container process manager, or another orchestrator.

## Workflow steps

1. Detect new Excel/CSV files by file hash.
2. Import uploaded data.
3. Clean and normalize data.
4. Validate required fields and positive debt amounts.
5. Detect and skip duplicates.
6. Apply the collection rule engine.
7. Run the deterministic AI Collection Assistant heuristic.
8. Generate recommendations.
9. Generate collector work queues.
10. Generate the Manager Morning Briefing.

## Outputs

Each run writes artifacts under:

```text
var/collection_agent/runs/<run_id>/
```

Key outputs:

- `collector_work_queues.json`: today's task list grouped by collector. Each task includes debtor, address, debt amount, recommended action, priority, explanation, and estimated success probability.
- `manager_morning_briefing.json`: executive briefing with targets, collectible forecast, priority cases, overdue follow-ups, region comparison, collector comparison, and management actions.
- `run_state.json`: execution history with start/end time, duration, processed files, processed records, recommendations generated, warnings, failures, completed steps, and recovery cursor.

Audit entries are appended to:

```text
var/collection_agent/audit/YYYY-MM-DD.jsonl
```

## Recovery

If a run fails or is interrupted, resume from the last successful step:

```bash
python -m municipal_ai_os.collection_agent run --workspace var/collection_agent --resume-run-id <run_id>
```

Completed steps are skipped and their saved artifacts are reloaded.

## Duplicate run prevention

The agent creates an exclusive lock file at `var/collection_agent/state/agent.lock`. A second run raises an error until the active run exits and removes the lock.

## Executive Decision Engine

The Executive Decision Engine runs after the daily collector workflow. It analyzes the municipality as a whole instead of only recommending debtor-level collection actions.

It produces:

- `executive_decision_engine.json`: executive intelligence with region performance, collector performance, district performance, and all executive recommendations.
- `mayor_dashboard.json`: a mayor-level dashboard with executive KPIs, weak regions, weak collectors, field-campaign districts, and daily strategic recommendations.
- `state/executive_recommendations.jsonl`: a durable learning log containing every executive recommendation emitted across runs.

Executive intelligence detects:

- weak-performing regions;
- weak-performing collectors;
- end-of-month revenue forecast;
- debts that will probably never be collected;
- collectors requiring intervention;
- taxpayers needing special negotiation;
- businesses likely to close;
- legal cases that should immediately move to Commission 77;
- districts requiring field campaigns;
- seasonal collection patterns;
- abnormal high-value behavior.

Executive KPIs include:

- open debt amount;
- expected collectible amount;
- predicted end-of-month revenue;
- Municipality Health Score;
- Collection Efficiency Score;
- high-priority case count;
- probably uncollectible amount;
- executive recommendation count.

Every executive recommendation includes a category, severity, management opportunity, recommended action, evidence, and an `ai_reasoning` explanation so managers can understand why the recommendation was produced.

# Multi-Agent Coordination System

Municipal AI OS now includes a file-backed multi-agent coordination system for independent AI workers:

- Collection Agent
- Call Center Agent
- Legal Agent
- Field Inspection Agent
- Manager Agent
- Mayor Agent

Use `build_default_coordinator()` from `municipal_ai_os.multi_agent_system` to create the six-agent system. Each agent has explicit goals, private memory, assigned tasks, a priority queue, result reporting, and the ability to create tasks for other agents.

## Coordination artifacts

The coordinator stores all coordination history under `var/multi_agent_system/` by default:

- `conversations.jsonl`: every agent-to-agent message.
- `decisions.jsonl`: every decision and task-creation event.
- `results.jsonl`: every task result report.
- `memory.jsonl`: each agent memory entry.
- `tasks/<task_id>.json`: current persisted task state.

## Example

```python
from municipal_ai_os.multi_agent_system import build_default_coordinator

coordinator = build_default_coordinator()
collection = coordinator.agents["collection"]
collection.create_task_for(
    assigned_to="legal",
    title="Prepare Commission 77 packet",
    description="Escalate high-value legal case for immediate review.",
    priority=1,
)
coordinator.run_next_task("legal")
```
