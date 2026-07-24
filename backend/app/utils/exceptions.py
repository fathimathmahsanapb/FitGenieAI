"""
Custom exceptions and centralized FastAPI exception handlers.

Every error response returned by this API follows the same JSON shape:

    {
        "success": false,
        "error": {
            "code": "AI_SERVICE_ERROR",
            "message": "Human-readable explanation"
        }
    }

so the frontend can parse errors uniformly regardless of which endpoint
or failure mode produced them.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("fitgenie.errors")


class AIServiceError(Exception):
    """Raised when the AI provider (Gemini) integration fails in a user-facing way."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _error_body(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app."""

    @app.exception_handler(AIServiceError)
    async def ai_service_error_handler(request: Request, exc: AIServiceError):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=_error_body("AI_SERVICE_ERROR", exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # Flatten pydantic's error list into one friendly message while
        # keeping the raw details available for debugging/logging.
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = f"Invalid input for '{field}': {first.get('msg', 'validation failed')}" if field else "Invalid request payload."
        logger.info("Validation error on %s: %s", request.url.path, exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("VALIDATION_ERROR", message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("HTTP_ERROR", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                "INTERNAL_SERVER_ERROR",
                "Something went wrong on our end. Please try again shortly.",
            ),
        )
