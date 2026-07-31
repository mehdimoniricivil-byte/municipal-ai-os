#!/usr/bin/env bash
set -euo pipefail

RUN_USER="${SUDO_USER:-$USER}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
BACKUP_DIR="${NGINX_STAGING_BACKUP_DIR:-$RUN_HOME/nginx-financial-staging-backups}"
PUBLIC_LOGIN="https://shahrdari-ai.com/backend-v1-staging/dashboard/login.html"

curl -fsS http://127.0.0.1:8002/api/v1/live >/dev/null || {
  echo "ERROR: staging API is not ready on 127.0.0.1:8002" >&2
  exit 1
}

NGINX_MATCH="$(sudo grep -RIl 'location /backend-v1/' /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | sed -n '1p')"
[[ -n "$NGINX_MATCH" ]] || {
  echo "ERROR: active /backend-v1/ Nginx configuration was not found" >&2
  exit 1
}
NGINX_CONF="$(sudo readlink -f "$NGINX_MATCH")"

if sudo grep -q 'location /backend-v1-staging/' "$NGINX_CONF"; then
  echo "Nginx staging route already exists in $NGINX_CONF"
else
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/$(basename "$NGINX_CONF").$(date -u +%Y%m%dT%H%M%SZ).conf"
  sudo cp "$NGINX_CONF" "$BACKUP_FILE"
  sudo chown "$RUN_USER":"$(id -gn "$RUN_USER")" "$BACKUP_FILE"
  chmod 600 "$BACKUP_FILE"

  TEMP_FILE="$(mktemp)"
  trap 'rm -f "$TEMP_FILE"' EXIT
  awk '
    !inserted && /^[[:space:]]*location \/backend-v1\/[[:space:]]*\{/ {
      print "    location /backend-v1-staging/ {"
      print "        proxy_pass http://127.0.0.1:8002/;"
      print "        proxy_http_version 1.1;"
      print "        proxy_set_header Host $host;"
      print "        proxy_set_header X-Real-IP $remote_addr;"
      print "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;"
      print "        proxy_set_header X-Forwarded-Proto $scheme;"
      print "        proxy_set_header X-Forwarded-Prefix /backend-v1-staging;"
      print "    }"
      print ""
      inserted=1
    }
    { print }
    END { if (!inserted) exit 42 }
  ' "$NGINX_CONF" >"$TEMP_FILE" || {
    echo "ERROR: could not insert staging route" >&2
    exit 1
  }

  sudo install -m 644 "$TEMP_FILE" "$NGINX_CONF"
  if ! sudo nginx -t; then
    sudo install -m 644 "$BACKUP_FILE" "$NGINX_CONF"
    sudo nginx -t
    echo "ERROR: Nginx validation failed; the original file was restored" >&2
    exit 1
  fi
  sudo systemctl reload nginx
fi

curl -fsS -o /dev/null -w "PUBLIC STAGING LOGIN: %{http_code}\n" "$PUBLIC_LOGIN"
echo "$PUBLIC_LOGIN"
