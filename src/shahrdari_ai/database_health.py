from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text

from .etl.engine import make_engine

router = APIRouter(prefix="/api/health", tags=["Health"])


class DatabaseHealthResponse(BaseModel):
    status: Literal["connected", "disconnected"]
    database: Literal["postgresql"] | None = None
    error_code: str | None = None


@router.get("/database", response_model=DatabaseHealthResponse)
def database_health_endpoint(response: Response) -> DatabaseHealthResponse:
    try:
        engine = make_engine()
        if engine.dialect.name != "postgresql":
            response.status_code = 503
            return DatabaseHealthResponse(
                status="disconnected",
                error_code="unsupported_database",
            )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except RuntimeError:
        response.status_code = 503
        return DatabaseHealthResponse(
            status="disconnected",
            error_code="database_configuration_missing",
        )
    except Exception:
        response.status_code = 503
        return DatabaseHealthResponse(
            status="disconnected",
            error_code="database_connection_failed",
        )

    return DatabaseHealthResponse(status="connected", database="postgresql")
