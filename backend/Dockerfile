# ============================================================
# FitGenie AI Backend — Production Dockerfile
# Optimized for AWS App Runner (single-container, HTTP on $PORT).
# ============================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files / buffering stdout — cleaner logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies (kept minimal for a small, fast image)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app
COPY tests ./tests

# Create a non-root user and switch to it (security best practice)
RUN addgroup --system fitgenie && adduser --system --ingroup fitgenie fitgenie \
    && chown -R fitgenie:fitgenie /app
USER fitgenie

# AWS App Runner provides the PORT env var at runtime; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Container-level healthcheck (App Runner also performs its own HTTP health check)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f "http://localhost:${PORT}/api/health" || exit 1

# Use sh -c so ${PORT} is expanded at container start (App Runner sets it dynamically)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
