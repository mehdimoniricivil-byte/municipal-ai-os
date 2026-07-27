from __future__ import annotations

from .collection_tools import router as collection_tools_router
from .database_health import router as database_health_router
from .upload_app import app

app.include_router(collection_tools_router)
app.include_router(database_health_router)
