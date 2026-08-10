from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.health import health_report

router = APIRouter()


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict:
    report, status_code = health_report(db, settings.storage_path)
    response.status_code = status_code
    return report


@router.get("/live")
def live() -> dict:
    return {"status": "ok"}
