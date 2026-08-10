from fastapi import APIRouter

from app.api.routes import audit, auth, calendar, collections, dashboard, expenses, finance, health, statements, upload, wage

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
api_router.include_router(collections.router, prefix="/collections", tags=["collections"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(wage.router, prefix="/wage", tags=["wage"])
api_router.include_router(expenses.router, prefix="/expenses", tags=["expenses"])
api_router.include_router(finance.router, prefix="/finance", tags=["finance"])

api_router.include_router(audit.router, prefix="/audit", tags=["audit"])

api_router.include_router(upload.router, prefix="/upload", tags=["collection-upload"])

api_router.include_router(statements.router, prefix="/statements", tags=["statements"])
