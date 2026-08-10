from __future__ import annotations
import os
import time
from pathlib import Path

root = Path(os.getenv("TEMP_UPLOAD_PATH", "storage/tmp"))
max_age = int(os.getenv("TEMP_FILE_MAX_AGE_SECONDS", "86400"))
now = time.time()
removed = 0
if root.exists():
    for path in root.rglob("*"):
        if path.is_file() and now - path.stat().st_mtime > max_age:
            path.unlink()
            removed += 1
print(f"removed={removed}")
