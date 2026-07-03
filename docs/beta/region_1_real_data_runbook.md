# Region 1 Real Data Beta Runbook

Use this runbook only with approved real Region 1 Excel files. Do not create or use fake data for the real-data beta run.

## 1. Place the Excel file

Put the approved `.xlsx` file in the prepared inbox folder:

```text
data/beta/region_1/inbox/
```

Recommended filename:

```text
data/beta/region_1/inbox/region_1_debt_records.xlsx
```

The expected columns are `debtor`, `address`, `region`, `collector`, `debt_amount`, `due_date`, `last_contact_date`, and optional `status`.

## 2. Run the beta workflow

From the repository root, run:

```bash
python -m municipal_ai_os.collection_agent run --workspace data/beta/region_1
```

This uses the existing Autonomous Collection Agent business logic. It does not require a separate beta command.

## 3. Find the run output folder

The command prints a `run_id`. All run reports are written under:

```text
data/beta/region_1/runs/<run_id>/
```

If you need to locate the latest run folder manually:

```bash
find data/beta/region_1/runs -mindepth 1 -maxdepth 1 -type d | sort | tail -1
```

## 4. Expected outputs

Replace `<run_id>` with the printed run id.

| Output | File |
| --- | --- |
| Validation report | `data/beta/region_1/runs/<run_id>/validate_records.json` |
| Run status and validation warnings | `data/beta/region_1/runs/<run_id>/run_state.json` |
| Duplicate report | `data/beta/region_1/runs/<run_id>/detect_duplicates.json` |
| AI recommendation report | `data/beta/region_1/runs/<run_id>/generate_recommendations.json` |
| Collector task queues | `data/beta/region_1/runs/<run_id>/collector_work_queues.json` |
| Manager morning briefing | `data/beta/region_1/runs/<run_id>/manager_morning_briefing.json` |
| Audit logs | `data/beta/region_1/audit/YYYY-MM-DD.jsonl` |

## 5. Verify success

Open `run_state.json` and confirm:

- `status` is `completed`;
- `processed_files` includes the Region 1 Excel filename;
- `processed_debt_records` is greater than `0`;
- `failures` is empty;
- `completed_steps` includes `generate_manager_briefing`.

Then confirm these files exist in the run folder:

```text
validate_records.json
detect_duplicates.json
generate_recommendations.json
collector_work_queues.json
manager_morning_briefing.json
```

## 6. Failure messages

- `Collection agent is already running`: another run has the lock file in `data/beta/region_1/state/agent.lock`; wait for it to finish before retrying.
- `openpyxl is required` or `No module named 'openpyxl'`: install project dependencies before importing Excel files.
- `processed_files` is empty: no new `.xlsx` file was found in `data/beta/region_1/inbox/`, or the file was already processed.
- `warnings` contains `missing debtor`, `missing address`, or `debt_amount must be positive`: the Excel file has rows that failed validation and should be reviewed before accepting the beta output.
- `failures` is not empty: stop the beta run, save `run_state.json`, and review the audit log for the same date.
