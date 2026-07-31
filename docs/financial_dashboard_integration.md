# Financial dashboard integration

The production system deliberately keeps two bounded services instead of
creating a second collection-import pipeline:

- `shahrdari_ai.upload_app` is the authoritative collection importer and serves
  the management data API under `/core-api/api/dashboard`.
- `services/financial_backend` owns authentication, expenses, contracts,
  statements, approvals, payments, and audit history under `/backend-v1`.
- The financial dashboard reads collection metrics from the core API and reads
  or writes financial records only through the authenticated financial API.

## Data contract

Every item in `scope_summaries` now includes period-aware collection fields:

- `latest_day_collection`
- `weekly_collection`
- `monthly_collection`
- `total_collection`
- `latest_payment_date`
- `unpaid_bill_count`
- `unpaid_bill_amount`
- `overdue_debt`

This prevents the financial UI from relying on its older, incomplete upload
schema. The original `daily_snapshots` and `import_runs` tables remain the
single source of truth for collection data.

## Database isolation

The financial backend must use its own database. It must not point at the core
database because both historical applications contain a table named `users`
with incompatible columns. Collection data crosses the boundary through the
HTTP API, not through shared ORM tables.

For a fresh financial database, run `alembic upgrade head` before starting the
service. For an existing v0.4 financial database, follow
`services/financial_backend/docs/MIGRATION_V0.5.0.md` and take a backup first.

## Proxy paths

- Core uploader/API: `/core-api` -> `127.0.0.1:8200`
- Financial backend: `/backend-v1` -> the financial container

The UI uses these public prefixes so it works correctly behind Nginx. Never
copy a backup file into `/etc/nginx/sites-enabled`; that directory is included
by wildcard and the backup would become an active duplicate configuration.

## Acceptance checks

Before switching the production upstream:

1. Verify `/api/v1/live` and `/api/v1/health` on the staging financial port.
2. Sign in with a newly configured administrator credential.
3. Confirm the collection totals match `/core-api/api/dashboard`.
4. Create and list a test expense in a non-production staging database.
5. Verify the statements page loads and permission checks reject unauthorized
   roles.
6. Confirm no fixed sample figures remain visible when either API is offline.

The staging compose file binds only to the first available localhost port in
`127.0.0.1:8300-8399` and joins the existing PostgreSQL Docker network through
`FINANCIAL_DOCKER_NETWORK`. It does not expose another PostgreSQL instance and
does not replace the production port `8001`.

The staging Nginx `proxy_pass` intentionally has no trailing slash. This keeps
the `/backend-v1-staging` prefix in the upstream request, which Starlette needs
to resolve mounted static dashboard files when `ROOT_PATH` is configured.
