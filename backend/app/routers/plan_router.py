"""
POST /api/generate-plan

Streams the fitness plan back to the client as Server-Sent Events (SSE):

  1. A single `metrics` event — deterministic BMI/BMR/TDEE/calorie/water
     data, computed instantly (no AI call), so the frontend can render
     those dashboard cards immediately.
  2. A sequence of `plan_chunk` events — the AI-generated workout + meal
     plan text.
  3. A final `done` event once streaming completes, or an `error` event
     if generation fails partway through.

Equipment validation (No Equipment users only):
  Real-time token streaming can't be "un-sent" once delivered, so it can't
  be validated mid-stream. For users who selected NO EQUIPMENT, the full
  plan is instead generated server-side first, scanned for forbidden
  equipment-based exercises (see prompt_builder.equipment_violation_terms),
  and regenerated once with a stricter prompt if a violation is found. The
  approved text is then sent to the client as a sequence of `plan_chunk`
  events (chunked, not token-by-token) so the frontend's progressive
  rendering still works. If the second attempt still violates the
  constraint, it is returned anyway rather than retrying indefinitely.
  Users with actual equipment selected are unaffected and keep the
  original real-time token-by-token streaming path.
"""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.plan_schema import GeneratePlanRequest
from app.services import gemini_service, metrics_service
from app.services.prompt_builder import build_plan_prompt, equipment_violation_terms
from app.utils.exceptions import AIServiceError

logger = logging.getLogger("fitgenie.plan_router")

router = APIRouter(prefix="/api", tags=["Fitness Plan"])


def _sse(event: str, data: dict | str) -> str:
    """Format a single Server-Sent Event frame."""
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


async def _generate_full_plan(prompt: str) -> str:
    """Consume the AI stream fully and return the assembled plan text.

    Used only for the No Equipment validation path below, where the full
    text must be inspected before anything is sent to the client.
    """
    parts = []
    async for token in gemini_service.stream_plan_generation(prompt):
        parts.append(token)
    return "".join(parts)


def _chunk_text(text: str, size: int = 40):
    """Split text into fixed-size pieces for SSE delivery after server-side
    validation, so the frontend still receives a sequence of `plan_chunk`
    events rather than one giant blob."""
    for i in range(0, len(text), size):
        yield text[i : i + size]


async def _plan_event_stream(request: GeneratePlanRequest):
    user = request.user

    # 1. Deterministic metrics — instant, no AI call required.
    metrics = metrics_service.build_metrics_payload(user)
    yield _sse("metrics", metrics.model_dump())

    # 2. AI-generated workout + meal plan.
    prompt = build_plan_prompt(user, metrics)
    try:
        if user.has_no_equipment:
            # Validate-then-stream path: buffer the full generation, scan
            # for forbidden equipment terms, and regenerate once (stricter
            # prompt) if a violation is found. Return the second attempt
            # regardless of outcome rather than looping.
            plan_text = await _generate_full_plan(prompt)
            violations = equipment_violation_terms(plan_text)

            if violations:
                logger.warning(
                    "No-equipment plan for %s violated equipment constraint "
                    "(found: %s) — regenerating once with a stricter prompt.",
                    user.full_name,
                    violations,
                )
                retry_prompt = build_plan_prompt(
                    user, metrics, strict_retry=True, previous_violations=violations
                )
                plan_text = await _generate_full_plan(retry_prompt)
                remaining = equipment_violation_terms(plan_text)
                if remaining:
                    logger.warning(
                        "No-equipment plan for %s still violated the equipment "
                        "constraint after retry (found: %s) — returning it anyway.",
                        user.full_name,
                        remaining,
                    )

            for chunk in _chunk_text(plan_text):
                yield _sse("plan_chunk", json.dumps({"text": chunk}))
        else:
            # Original real-time token-by-token streaming path, unchanged.
            async for token in gemini_service.stream_plan_generation(prompt):
                yield _sse("plan_chunk", json.dumps({"text": token}))
    except AIServiceError as exc:
        logger.warning("Plan generation failed for %s: %s", user.full_name, exc.message)
        yield _sse("error", {"code": "AI_SERVICE_ERROR", "message": exc.message})
        return

    yield _sse("done", {"status": "complete"})


@router.post("/generate-plan", summary="Generate a personalized fitness plan (streamed)")
async def generate_plan(request: GeneratePlanRequest):
    return StreamingResponse(
        _plan_event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering (e.g. nginx) for real streaming
        },
    )
