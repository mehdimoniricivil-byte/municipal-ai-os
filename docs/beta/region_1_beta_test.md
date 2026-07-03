# Region 1 Beta Test Workflow

This guide prepares Municipal AI OS for a controlled beta test with real Region 1 Excel data. It does not add new product behavior; it uses the existing Autonomous Collection Agent outputs.

## 1. Prepare real Excel files

1. Confirm the Excel files contain the expected columns: `debtor`, `address`, `region`, `collector`, `debt_amount`, `due_date`, `last_contact_date`, and optional `status`.
2. Copy Region 1 Excel files into:

```bash
data/beta/region_1/inbox/
```

3. Keep real taxpayer files out of git.

## 2. Import and process Region 1 Excel files

Run the existing collection agent against the Region 1 beta workspace:

```bash
python -m municipal_ai_os.collection_agent run --workspace data/beta/region_1
```

The command imports any new `.xlsx` files from `data/beta/region_1/inbox/`, validates records, detects duplicates, applies collection rules, generates AI recommendations, and writes manager/executive outputs under `data/beta/region_1/runs/<run_id>/`.

## 3. Locate the beta run id

After the run completes, use the printed `run_id`, or inspect the latest folder:

```bash
find data/beta/region_1/runs -mindepth 1 -maxdepth 1 -type d | sort | tail -1
```

Set it for review commands:

```bash
RUN_ID=<paste-run-id-here>
```

## 4. Validation report output

Validation results are captured in the run state and validation artifact:

```bash
cat data/beta/region_1/runs/$RUN_ID/validate_records.json
cat data/beta/region_1/runs/$RUN_ID/run_state.json
```

Review `warnings`, `processed_debt_records`, and rejected rows before approving the beta output.

## 5. Duplicate report output

Duplicate detection results are written to:

```bash
cat data/beta/region_1/runs/$RUN_ID/detect_duplicates.json
```

Review the `duplicates` list and confirm skipped duplicates match municipal expectations.

## 6. AI recommendation report output

AI collection recommendations are written to:

```bash
cat data/beta/region_1/runs/$RUN_ID/generate_recommendations.json
cat data/beta/region_1/runs/$RUN_ID/collector_work_queues.json
```

Confirm recommendations include debtor, address, debt amount, recommended action, priority, explanation, and estimated success probability.

## 7. Manager briefing output

The manager morning briefing is written to:

```bash
cat data/beta/region_1/runs/$RUN_ID/manager_morning_briefing.json
```

Use this output for the Region 1 morning review with collection leadership.

## 8. Beta test checklist

Before the run:

- [ ] Confirm Region 1 source Excel files are approved for beta testing.
- [ ] Confirm no real taxpayer files are committed to git.
- [ ] Confirm column names match the expected import format.
- [ ] Confirm collectors and regions are populated.
- [ ] Confirm a beta reviewer is assigned for validation, duplicates, recommendations, and briefing outputs.

During the run:

- [ ] Run `python -m municipal_ai_os.collection_agent run --workspace data/beta/region_1`.
- [ ] Save the printed `run_id`.
- [ ] Confirm the run completes with `status` equal to `completed`.
- [ ] Confirm audit logs are created under `data/beta/region_1/audit/`.

After the run:

- [ ] Review `validate_records.json` and `run_state.json` warnings.
- [ ] Review `detect_duplicates.json` duplicates.
- [ ] Review `generate_recommendations.json` and `collector_work_queues.json`.
- [ ] Review `manager_morning_briefing.json` with the Region 1 manager.
- [ ] Record beta findings and do not modify production workflows until findings are approved.
