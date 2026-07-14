# Municipality Dashboard MVP

This MVP adds a deterministic Persian RTL management dashboard to the existing FastAPI upload service. It uses only PostgreSQL/SQLAlchemy queries and Python formatting; no GPT, Open WebUI Knowledge, n8n workflow, voice, SMS, WhatsApp, or multi-agent flow is used for calculations.

## Routes

Run the existing FastAPI app:

```bash
uvicorn shahrdari_ai.upload_app:app --host 0.0.0.0 --port 8000
```

Open these pages:

- `GET /dashboard` — Persian management dashboard with KPI cards, grouped regional totals, top 20 debtors, latest imports, and data-quality warnings.
- `GET /taxpayers` — taxpayer search across operator name, phone, identification code, case number, and address.
- `GET /taxpayers/{id}` — taxpayer detail page with historical snapshot rows.

## Required import metadata

Each import run stores:

- `region`
- `file_type`
- `snapshot_date`
- `uploaded_by`
- `source_file_name`
- `imported_at`

The upload form passes the selected `file_type`, signed-in username, original file name, region, and snapshot date into the ETL importer.

## Deterministic calculations

Dashboard numbers are calculated from `daily_snapshots` joined to `import_runs` using SQL aggregation:

- total taxpayers
- total outstanding debt
- total bill amount
- total business tax
- average outstanding debt
- taxpayers with zero debt
- taxpayers with missing phone
- top 20 debtors sorted by outstanding debt descending
- totals grouped by region
- latest imports
- data quality warnings

## Filters

`/dashboard` and `/taxpayers` accept these query-string filters:

- `region`
- `snapshot_date`
- `file_type`

Example:

```text
/dashboard?region=منطقه%20یک&snapshot_date=1405-04-17&file_type=snapshot
```

## Historical snapshots and duplicates

Historical snapshots are preserved. A repeated import with the same `snapshot_date`, `region`, and `file_type` is rejected instead of replacing prior data.

## Mobile support

The dashboard HTML is RTL Persian and uses responsive CSS with:

- viewport metadata for iPhone Safari
- auto-fit KPI cards
- horizontally scrollable tables on small screens
- large tap-friendly inputs and buttons

## Uploading real Excel files

Use the existing `/upload` page for each real municipality Excel file. For four real files, choose the correct region, file type, and snapshot date before uploading each file. After import, open `/dashboard` to compare regions and validate totals.
