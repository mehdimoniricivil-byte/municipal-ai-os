from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.seed import seed_reference_data


app = FastAPI(
    title=settings.app_name,
    version="0.5.0",
    description="سامانه وصول، هزینه، صورت‌وضعیت و زیرساخت انتشار آزمایشی",
    root_path="/backend-v1",
)


@app.on_event("startup")
def startup() -> None:
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    seed_reference_data()


app.include_router(api_router, prefix="/api/v1")
app.mount("/dashboard", StaticFiles(directory="app/static", html=True), name="dashboard")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="dashboard/login.html")
