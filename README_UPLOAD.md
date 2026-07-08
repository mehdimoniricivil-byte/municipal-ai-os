# Excel Upload Web UI v1

This repository includes a small FastAPI upload page for importing municipality `.xlsx` files into PostgreSQL without SFTP.

## Environment variables

- `DATABASE_URL` — PostgreSQL SQLAlchemy connection string used by the existing ETL import logic.
- `UPLOAD_USERNAME` — shared username required by the upload form.
- `UPLOAD_PASSWORD` — shared password required by the upload form.

Example:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/municipality'
export UPLOAD_USERNAME='municipality-uploader'
export UPLOAD_PASSWORD='change-this-password'
```

## Run the upload server

Install the project dependencies, then run FastAPI with Uvicorn:

```bash
python -m pip install -e '.[test]'
uvicorn shahrdari_ai.upload_app:app --host 0.0.0.0 --port 8000
```

Open this page in Safari on iPhone or any browser:

```text
http://SERVER-IP:8000/upload
```

## Upload workflow

1. Enter the shared `UPLOAD_USERNAME` and `UPLOAD_PASSWORD`.
2. Choose the snapshot date, region, and file type.
3. Select a municipality Excel file ending in `.xlsx`.
4. Submit the form.

The server saves uploaded files under:

```text
data/imports/
```

After the file is saved, the page runs the existing ETL import logic with `DATABASE_URL` and shows a Persian result page with:

- uploader
- region
- file type
- snapshot date
- file name
- import status
- total rows
- inserted taxpayers
- updated taxpayers
- skipped duplicates
- errors

## Limits

- Only `.xlsx` files are accepted.
- The page is intentionally upload-only; it does not include dashboards, KPI pages, or AI-based calculations.
