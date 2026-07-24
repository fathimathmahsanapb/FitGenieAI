"""
POST /api/chat

Streams an AI fitness-assistant reply as Server-Sent Events. The assistant
receives the user's profile, their previously generated workout/meal plan,
and the conversation history, so answers stay grounded in the user's
specific context rather than generic advice.
"""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.chat_schema import ChatRequest
from app.services import gemini_service
from app.services.prompt_builder import build_chat_messages
from app.utils.exceptions import AIServiceError

logger = logging.getLogger("fitgenie.chat_router")

router = APIRouter(prefix="/api", tags=["AI Chat"])


def _sse(event: str, data) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


async def _chat_event_stream(request: ChatRequest):
    messages = build_chat_messages(
        user=request.user,
        workout_plan=request.workout_plan,
        meal_plan=request.meal_plan,
        message=request.message,
        history=request.history,
    )
    try:
        async for token in gemini_service.stream_chat_response(messages):
            yield _sse("message_chunk", json.dumps({"text": token}))
    except AIServiceError as exc:
        logger.warning("Chat generation failed: %s", exc.message)
        yield _sse("error", {"code": "AI_SERVICE_ERROR", "message": exc.message})
        return

    yield _sse("done", {"status": "complete"})


@router.post("/chat", summary="Ask the AI fitness assistant a question (streamed)")
async def chat(request: ChatRequest):
    return StreamingResponse(
        _chat_event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
