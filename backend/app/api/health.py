"""Health and system status endpoints."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from app.core.config import settings
from app.schemas.responses import HealthResponse

router = APIRouter(tags=["System"])

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    TZ = timezone(timedelta(hours=7))


@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy",
        app_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(TZ),
    )
