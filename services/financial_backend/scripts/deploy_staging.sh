#!/usr/bin/env bash
set -euo pipefail

umask 077

SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$SERVICE_DIR/docker-compose.staging.yml"
ENV_FILE="$SERVICE_DIR/.env.staging"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-shahrdari-postgres}"
DB_HOST="${FINANCIAL_DB_HOST:-shahrdari-postgres}"
DB_ROLE="${FINANCIAL_DB_ROLE:-shahrdari_financial_staging}"
DB_NAME="${FINANCIAL_DB_NAME:-shahrdari_financial_staging}"
COMPOSE_PROJECT="${FINANCIAL_COMPOSE_PROJECT:-shahrdari-financial-staging}"
RUN_USER="${SUDO_USER:-$USER}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
CREDENTIAL_FILE="${FINANCIAL_CREDENTIAL_FILE:-$RUN_HOME/financial-dashboard-staging-admin.txt}"
EXPLICIT_STAGING_PORT="${FINANCIAL_STAGING_PORT:-}"

for command_name in docker openssl curl ss; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "ERROR: $command_name is required" >&2
    exit 1
  }
done

sudo docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 || {
  echo "ERROR: PostgreSQL container '$POSTGRES_CONTAINER' was not found" >&2
  exit 1
}

POSTGRES_USER="$(sudo docker exec "$POSTGRES_CONTAINER" sh -lc 'printf %s "$POSTGRES_USER"')"
POSTGRES_DB="$(sudo docker exec "$POSTGRES_CONTAINER" sh -lc 'printf %s "$POSTGRES_DB"')"
DB_NETWORK="${FINANCIAL_DOCKER_NETWORK:-$(sudo docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' "$POSTGRES_CONTAINER" | sed -n '1p')}"

[[ "$DB_ROLE" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || { echo "ERROR: invalid database role" >&2; exit 1; }
[[ "$DB_NAME" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || { echo "ERROR: invalid database name" >&2; exit 1; }
[[ -n "$POSTGRES_USER" && -n "$POSTGRES_DB" && -n "$DB_NETWORK" ]] || {
  echo "ERROR: PostgreSQL metadata could not be detected" >&2
  exit 1
}

read_env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$ENV_FILE" 2>/dev/null | tail -n 1
}

if [[ -s "$ENV_FILE" ]]; then
  DB_PASSWORD="$(read_env_value FINANCIAL_DB_PASSWORD)"
  ADMIN_PASSWORD="$(read_env_value INITIAL_ADMIN_PASSWORD)"
  SECRET_KEY="$(read_env_value SECRET_KEY)"
  SAVED_STAGING_PORT="$(read_env_value FINANCIAL_STAGING_PORT)"
else
  DB_PASSWORD=""
  ADMIN_PASSWORD=""
  SECRET_KEY=""
  SAVED_STAGING_PORT=""
fi

DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 24)}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(openssl rand -hex 16)}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 48)}"

CURRENT_STAGING_PORT="$(sudo docker port shahrdari-financial-staging 8000/tcp 2>/dev/null | sed -n '1s/.*://p' || true)"

port_is_free() {
  [[ -z "$(ss -H -ltn "sport = :$1" 2>/dev/null)" ]]
}

port_is_valid() {
  [[ "$1" =~ ^[0-9]+$ ]] && ((1 <= 10#$1 && 10#$1 <= 65535))
}

STAGING_PORT="${EXPLICIT_STAGING_PORT:-$SAVED_STAGING_PORT}"
if [[ -n "$STAGING_PORT" ]] && ! port_is_valid "$STAGING_PORT"; then
  echo "ERROR: invalid staging port '$STAGING_PORT'" >&2
  exit 1
fi

if [[ -n "$STAGING_PORT" ]] && ! port_is_free "$STAGING_PORT" && [[ "$CURRENT_STAGING_PORT" != "$STAGING_PORT" ]]; then
  if [[ -n "$EXPLICIT_STAGING_PORT" ]]; then
    echo "ERROR: requested staging port $STAGING_PORT is already allocated" >&2
    exit 1
  fi
  STAGING_PORT=""
fi

if [[ -z "$STAGING_PORT" ]]; then
  for candidate in $(seq 8300 8399); do
    if port_is_free "$candidate" || [[ "$CURRENT_STAGING_PORT" == "$candidate" ]]; then
      STAGING_PORT="$candidate"
      break
    fi
  done
fi

[[ -n "$STAGING_PORT" ]] || {
  echo "ERROR: no free staging port was found in 8300-8399" >&2
  exit 1
}

cat >"$ENV_FILE" <<EOF
APP_NAME=Shahrdari AI Staging
APP_ENV=staging
DATABASE_URL=postgresql+psycopg://${DB_ROLE}:${DB_PASSWORD}@${DB_HOST}:5432/${DB_NAME}
SECRET_KEY=${SECRET_KEY}
ACCESS_TOKEN_MINUTES=30
REFRESH_TOKEN_DAYS=14
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=${ADMIN_PASSWORD}
INITIAL_ADMIN_FULL_NAME="مدیر آزمایشی سامانه"
STORAGE_PATH=/app/storage
LOG_LEVEL=INFO
AUTO_CREATE_SCHEMA=false
DASHBOARD_WAGE_RATE_PERCENT=6
ROOT_PATH=/backend-v1-staging
FINANCIAL_DOCKER_NETWORK=${DB_NETWORK}
FINANCIAL_DB_PASSWORD=${DB_PASSWORD}
FINANCIAL_STAGING_PORT=${STAGING_PORT}
EOF
chmod 600 "$ENV_FILE"

sudo docker exec -i "$POSTGRES_CONTAINER" \
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<SQL
DO \$body\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_ROLE}') THEN
    CREATE ROLE ${DB_ROLE} LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_ROLE} WITH LOGIN PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$body\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_ROLE}'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}')\gexec
ALTER DATABASE ${DB_NAME} OWNER TO ${DB_ROLE};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_ROLE};
SQL

cd "$SERVICE_DIR"
mkdir -p "$SERVICE_DIR/storage"
chmod 700 "$SERVICE_DIR/storage"
COMPOSE=(sudo docker compose --project-name "$COMPOSE_PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head
"${COMPOSE[@]}" up -d api

healthy=false
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${STAGING_PORT}/api/v1/live" >/dev/null; then
    healthy=true
    break
  fi
  sleep 2
done

if [[ "$healthy" != true ]]; then
  "${COMPOSE[@]}" ps
  "${COMPOSE[@]}" logs --tail=80 api
  echo "ERROR: staging API did not become ready" >&2
  exit 1
fi

cat >"$CREDENTIAL_FILE" <<EOF
آدرس ورود پس از فعال‌سازی Nginx:
https://shahrdari-ai.com/backend-v1-staging/dashboard/login.html

نام کاربری: admin
رمز موقت: ${ADMIN_PASSWORD}

این فایل را در چت ارسال نکنید. پس از اولین ورود رمز را تغییر دهید.
EOF
chmod 600 "$CREDENTIAL_FILE"
if [[ "$RUN_USER" != "$(id -un)" ]]; then
  chown "$RUN_USER":"$(id -gn "$RUN_USER")" "$CREDENTIAL_FILE"
fi

echo "STAGING PORT: $STAGING_PORT"
echo "STAGING API READY: http://127.0.0.1:${STAGING_PORT}/api/v1/live"
echo "LOGIN CREDENTIALS: $CREDENTIAL_FILE"
