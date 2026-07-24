"""
FitGenie AI — FastAPI backend entrypoint.

Run locally:
    uvicorn app.main:app --reload --port 8000

Run in production (see Dockerfile):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat_router, health_router, plan_router
from app.utils.exceptions import register_exception_handlers
from app.utils.logging_config import configure_logging

settings = get_settings()
configure_logging()
logger = logging.getLogger("fitgenie.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info(
        "FitGenie AI backend starting | env=%s | model=%s | cors_origins=%s",
        settings.app_env,
        settings.gemini_model,
        settings.cors_origins,
    )
    if not settings.gemini_api_key:
        logger.warning(
            "GEMINI_API_KEY is not set. /api/generate-plan and /api/chat will fail "
            "until it is configured."
        )
    yield
    # --- Shutdown ---
    logger.info("FitGenie AI backend shutting down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Backend API for FitGenie AI \u2014 generates personalized workout plans, "
        "meal plans, hydration and calorie targets, and powers the AI fitness "
        "chat assistant, with streaming Gemini responses."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------
# CORS — only allow the configured frontend origin(s), never "*" in prod.
# ---------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Global exception handlers — consistent {"success": false, "error": {...}}
# ---------------------------------------------------------------------
register_exception_handlers(app)

# ---------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------
app.include_router(health_router.router)
app.include_router(plan_router.router)
app.include_router(chat_router.router)


@app.get("/", tags=["Root"])
async def root():
    """Simple root endpoint — useful for a quick manual sanity check."""
    return {
        "success": True,
        "data": {
            "message": f"{settings.app_name} is running.",
            "docs": "/api/docs",
            "health": "/api/health",
        },
    }
