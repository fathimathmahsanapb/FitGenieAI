"""Structured logging setup for the FitGenie AI backend."""

import logging
import sys

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=log_format,
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )

    # Keep third-party libraries quieter than our own app logs by default.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    logging.getLogger("fitgenie").setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
