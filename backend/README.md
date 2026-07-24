# FitGenie AI — Backend

Python FastAPI backend for FitGenie AI: computes fitness metrics instantly, generates
AI-personalized workout + meal plans, and powers a context-aware AI fitness chat
assistant — all with streaming Gemini (Google GenAI) responses.

This is a **backend-only** package. It does not serve or modify the frontend; it is
designed to be called from the FitGenie AI frontend (`fetch()` + `EventSource`/stream
reader against the endpoints below).

## Folder structure

```
backend/
├── app/
│   ├── main.py                    # FastAPI app entrypoint, CORS, routers, startup
│   ├── config.py                  # Environment-based settings (pydantic-settings)
│   ├── routers/
│   │   ├── health_router.py       # GET /api/health
│   │   ├── plan_router.py         # POST /api/generate-plan (streamed)
│   │   └── chat_router.py         # POST /api/chat (streamed)
│   ├── services/
│   │   ├── metrics_service.py     # BMI / BMR / TDEE / calories / water (pure functions)
│   │   ├── prompt_builder.py      # All prompt engineering + safety rules
│   │   └── gemini_service.py      # Centralized Gemini client + streaming
│   ├── models/
│   │   ├── user_schema.py         # UserProfile + enums (matches frontend form)
│   │   ├── plan_schema.py         # Plan request/metrics response schemas
│   │   └── chat_schema.py         # Chat request/message schemas
│   └── utils/
│       ├── exceptions.py          # Custom errors + global exception handlers
│       └── logging_config.py      # Structured logging setup
├── tests/
│   ├── test_metrics_service.py
│   └── test_api.py
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── docker-compose.yml
├── apprunner.yaml
└── .env.example
```

## Setup (local)

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set a real GEMINI_API_KEY
```

## Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

- API docs (Swagger UI): http://localhost:8000/api/docs
- Health check: http://localhost:8000/api/health

## Run with Docker

```bash
docker build -t fitgenie-ai-backend .
docker run --env-file .env -p 8000:8000 fitgenie-ai-backend
```

Or with Docker Compose:

```bash
docker compose up --build
```

## Run tests

```bash
pytest -v
```

Tests do not call the real Gemini API — only deterministic logic (metrics
calculations) and request validation are exercised, so they run free and fast.

## API Endpoints

| Method | Endpoint | Description | Streaming |
|---|---|---|---|
| GET | `/api/health` | Liveness/readiness check | No |
| POST | `/api/generate-plan` | Generate BMI/calorie/water metrics + AI workout & meal plan | Yes (SSE) |
| POST | `/api/chat` | Ask the AI fitness assistant a context-aware question | Yes (SSE) |

Both streaming endpoints return `Content-Type: text/event-stream`. See each router's
docstring for the exact event sequence (`metrics` → `plan_chunk`* → `done`, or
`message_chunk`* → `done`, with an `error` event on failure).

## Environment variables

See `.env.example` for the full list. At minimum you must set `GEMINI_API_KEY` for
the AI endpoints to work; `/api/health` and `/` will respond even without it.

**Never commit a real `.env` file.** In production, inject secrets via your platform's
secret manager (e.g. AWS App Runner environment variables / AWS Secrets Manager),
not via the Docker image.

## Deploying to AWS App Runner

**Option A — Container image (recommended)**
1. Build and push the image to Amazon ECR:
   ```bash
   aws ecr create-repository --repository-name fitgenie-ai-backend
   docker build -t fitgenie-ai-backend .
   docker tag fitgenie-ai-backend:latest <account-id>.dkr.ecr.<region>.amazonaws.com/fitgenie-ai-backend:latest
   docker push <account-id>.dkr.ecr.<region>.amazonaws.com/fitgenie-ai-backend:latest
   ```
2. Create an App Runner service pointing at that ECR image.
3. Set `GEMINI_API_KEY` and the other variables from `.env.example` as environment
   variables/secrets in the App Runner service configuration.
4. App Runner injects `PORT` automatically — the Dockerfile's `CMD` already respects it.
5. Point App Runner's health check at `/api/health`.

**Option B — Source-based deploy**
Connect this repo directly to App Runner; it will use `apprunner.yaml` to build and
run the service without a container image.

## Security notes

- API keys are never hardcoded — loaded exclusively from environment variables via
  `pydantic-settings` / `python-dotenv`.
- CORS is restricted to the origins listed in `ALLOWED_ORIGINS` (never `*` in production).
- The container runs as a non-root user.
- All error responses follow a consistent `{"success": false, "error": {...}}` shape and
  never leak stack traces to the client.
