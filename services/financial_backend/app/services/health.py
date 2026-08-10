from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

_STARTED_AT = time.time()


def _memory() -> dict:
    result = {"available": None, "total": None, "unit": "bytes"}
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return result
    values: dict[str, int] = {}
    for line in meminfo.read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) * 1024
    result["available"] = values.get("MemAvailable")
    result["total"] = values.get("MemTotal")
    return result


def health_report(db: Session, storage_path: str) -> tuple[dict, int]:
    checks: dict[str, dict] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:  # the public response deliberately hides credentials/details
        checks["database"] = {"status": "error", "message": type(exc).__name__}

    path = Path(storage_path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        checks["storage"] = {"status": "ok", "path": str(path)}
    except Exception as exc:
        checks["storage"] = {"status": "error", "message": type(exc).__name__}

    disk = shutil.disk_usage(path if path.exists() else "/")
    checks["disk"] = {
        "status": "ok" if disk.free > 100 * 1024 * 1024 else "warning",
        "total_bytes": disk.total,
        "free_bytes": disk.free,
    }
    checks["memory"] = {"status": "ok", **_memory()}
    checks["process"] = {"status": "ok", "pid": os.getpid(), "uptime_seconds": int(time.time() - _STARTED_AT)}

    overall = "ok" if all(c["status"] in {"ok", "warning"} for c in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}, (200 if overall == "ok" else 503)
