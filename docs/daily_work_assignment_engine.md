# Daily Work Assignment Engine

The Daily Work Assignment Engine turns daily municipal work queues into recommended agent assignments. It is recommendation-only: it does not send messages, call debtors, create notices, dispatch field staff, or perform legal actions.

## Inputs

Place these files in the assignment workspace:

- `priority_report.json`
- `daily_call_queue.json`
- `daily_visit_queue.json`
- `daily_notice_queue.json`
- `legal_queue.json`
- `assignment_rules.json` (optional, but recommended)

Queue files can be either a JSON list of task objects or an object containing a `tasks`, `queue`, `items`, `records`, or `cases` list. Tasks may include `task_id`, `case_id`, `record_id`, `priority`, `zone`, `district`, `region`, or `neighborhood`.

## Configurable rules

Rules are configured in `assignment_rules.json`. The most important setting is `agents`, where each available agent declares roles and daily capacities:

```json
{
  "schedule_date": "2026-07-03",
  "priority_order": ["critical", "high", "medium", "low"],
  "task_type_order": ["FIELD_VISIT", "CALL", "NOTICE", "LEGAL"],
  "balance_weight": 1.0,
  "zone_match_bonus": 2.5,
  "agents": [
    {
      "agent_id": "call_agent_1",
      "name": "Call Agent 1",
      "roles": ["CALL"],
      "available": true,
      "max_calls_per_day": 60,
      "max_visits_per_day": 0,
      "max_notices_per_day": 0,
      "max_legal_per_day": 0
    },
    {
      "agent_id": "field_agent_north",
      "name": "North Field Agent",
      "roles": ["FIELD_VISIT", "NOTICE"],
      "available": true,
      "zones": ["North"],
      "max_calls_per_day": 0,
      "max_visits_per_day": 25,
      "max_notices_per_day": 40,
      "max_legal_per_day": 0
    }
  ]
}
```

If `assignment_rules.json` is omitted, the engine uses conservative default agents so the workflow remains runnable in a new workspace.

## Assignment behavior

- CALL tasks are distributed across available call agents by current utilization so workloads remain fair.
- FIELD_VISIT tasks prefer agents whose configured `zones` match the task zone, while still respecting workload balance.
- NOTICE and LEGAL tasks are assigned only to agents with matching roles and available capacity.
- Capacity is enforced for `max_calls_per_day`, `max_visits_per_day`, `max_notices_per_day`, and `max_legal_per_day`.
- Any task that cannot be assigned is preserved in outputs with an `unassigned_reason`.

## Outputs

Running the engine writes these recommendation artifacts:

- `agent_assignments.json`
- `daily_agent_schedule.json`
- `workload_summary.json`
- `manager_assignment_dashboard.json`

Each output includes `recommendation_only: true` metadata so downstream users can distinguish recommended assignments from executed actions.

## Run

```bash
python -m municipal_ai_os.daily_work_assignment run --workspace var/daily_work_assignment
```

Use a separate rules file if needed:

```bash
python -m municipal_ai_os.daily_work_assignment run --workspace var/daily_work_assignment --rules config/assignment_rules.json
```
