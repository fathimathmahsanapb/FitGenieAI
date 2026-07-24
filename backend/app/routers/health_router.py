"""GET /api/health — liveness/readiness probe for AWS App Runner."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/api/health", summary="Health check")
async def health_check():
    settings = get_settings()
    return {
        "success": True,
        "data": {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
