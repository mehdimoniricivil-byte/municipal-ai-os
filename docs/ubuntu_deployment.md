# Ubuntu production deployment

These commands install the runtime dependencies, configure PostgreSQL, run the upload server, and verify the real municipality Excel import.

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib build-essential libpq-dev
cd /opt
sudo git clone <REPO_URL> municipal-ai-os
sudo chown -R "$USER":"$USER" /opt/municipal-ai-os
cd /opt/municipal-ai-os
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
sudo -u postgres psql -c "CREATE USER municipal_ai WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE municipal_ai_os OWNER municipal_ai;"
export DATABASE_URL='postgresql+psycopg://municipal_ai:CHANGE_ME_STRONG_PASSWORD@127.0.0.1:5432/municipal_ai_os'
export UPLOAD_USERNAME='admin'
export UPLOAD_PASSWORD='CHANGE_ME_UPLOAD_PASSWORD'
python - <<'PY'
from shahrdari_ai.etl.engine import import_excel
result = import_excel(
    'data/beta/region_1/inbox/صادره 1405 کسب و پیشه منطقه یک.xlsx',
    '1405-01-31',
    'منطقه یک',
)
print({
    'total_rows': result.total_rows,
    'rows_imported': result.rows_imported,
    'inserted_taxpayers': result.inserted_taxpayers,
    'updated_taxpayers': result.updated_taxpayers,
    'duplicates': result.skipped_duplicates,
    'row_errors': result.row_errors,
})
PY
python -m uvicorn shahrdari_ai.upload_app:app --host 0.0.0.0 --port 8000 --log-level info
```

Open `http://SERVER_IP:8000/upload`, sign in with `UPLOAD_USERNAME` / `UPLOAD_PASSWORD`, and upload the Excel file.

For systemd, create `/etc/systemd/system/municipal-ai-os.service`:

```ini
[Unit]
Description=Municipal AI OS upload service
After=network.target postgresql.service

[Service]
WorkingDirectory=/opt/municipal-ai-os
Environment="DATABASE_URL=postgresql+psycopg://municipal_ai:CHANGE_ME_STRONG_PASSWORD@127.0.0.1:5432/municipal_ai_os"
Environment="UPLOAD_USERNAME=admin"
Environment="UPLOAD_PASSWORD=CHANGE_ME_UPLOAD_PASSWORD"
ExecStart=/opt/municipal-ai-os/.venv/bin/python -m uvicorn shahrdari_ai.upload_app:app --host 0.0.0.0 --port 8000 --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now municipal-ai-os
sudo journalctl -u municipal-ai-os -f
```
