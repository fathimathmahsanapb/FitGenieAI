"""
Centralized Google Gemini (google-genai) API client.

Every call to the AI provider goes through this module so routers never talk
to the SDK directly. This keeps API-key handling, model selection, and
streaming logic in one auditable place.

Public interface (`get_client`, `stream_plan_generation`,
`stream_chat_response`) is a thin async-generator streaming API consumed
directly by `plan_router.py` and `chat_router.py`.
"""

import asyncio
import logging
from typing import AsyncGenerator, List, Optional, Tuple

from google import genai
from google.genai import errors, types

from app.config import get_settings
from app.services.prompt_builder import BASE_SYSTEM_PROMPT
from app.utils.exceptions import AIServiceError

logger = logging.getLogger("fitgenie.gemini_service")

settings = get_settings()

# Gemini occasionally returns 503 UNAVAILABLE ("high demand") — a transient,
# self-resolving overload rather than a real failure. We retry a couple of
# times with a short backoff before giving up, but ONLY if no content has
# been yielded yet for this attempt: once tokens have already reached the
# caller, restarting would duplicate/garble what the client has seen, so a
# mid-stream failure at that point is treated as terminal instead.
_MAX_OVERLOAD_RETRIES = 2
_RETRY_BASE_DELAY_SECONDS = 2.0

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Lazily construct a singleton Gemini client.

    Raising here (instead of at import time) means the app can still start
    and serve /api/health even if GEMINI_API_KEY is temporarily unset —
    only AI-dependent routes will fail, with a clear error.
    """
    global _client
    if not settings.gemini_api_key:
        raise AIServiceError(
            "GEMINI_API_KEY is not configured on the server. "
            "Set it as an environment variable before calling AI endpoints."
        )
    if _client is None:
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=settings.gemini_request_timeout * 1000  # ms
            ),
        )
    return _client


def _messages_to_gemini(
    messages: List[dict],
) -> Tuple[Optional[str], List[types.Content]]:
    """
    Convert a standard chat-style `messages` array (list of {"role", "content"}
    dicts, as built by prompt_builder.build_chat_messages) into Gemini's
    format: a single `system_instruction` string plus a list of
    `types.Content` turns, with "assistant" mapped to Gemini's "model" role.
    """
    system_parts: List[str] = []
    contents: List[types.Content] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            contents.append(
                types.Content(role="model", parts=[types.Part.from_text(text=content)])
            )
        else:  # "user" (and any unexpected role defaults to user turn)
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(text=content)])
            )

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return system_instruction, contents


def _raise_for_gemini_error(exc: Exception, context: str) -> None:
    """Translate a Gemini SDK exception into the shared AIServiceError,
    preserving the same rate-limit / timeout / generic-error distinctions
    a consistent, provider-agnostic contract for AIServiceError."""
    if isinstance(exc, errors.ClientError):
        if getattr(exc, "code", None) == 429:
            exc_text = str(exc)
            if "PerDay" in exc_text or "per day" in exc_text.lower():
                # A daily quota (e.g. free-tier "20 requests/day/model") won't
                # recover from a short retry — it only resets on Google's
                # daily quota window. Say so plainly instead of implying a
                # quick retry will help.
                logger.warning("Gemini daily quota exhausted during %s: %s", context, exc)
                raise AIServiceError(
                    "You've reached today's free-tier request limit for this AI model "
                    "on your Google account. It resets daily — try again later, or "
                    "switch to a different Gemini model with available quota."
                ) from exc
            logger.warning("Gemini rate limit hit during %s: %s", context, exc)
            raise AIServiceError(
                "The AI service is currently busy. Please wait a moment and try again."
            ) from exc
        logger.error("Gemini client error during %s: %s", context, exc)
        raise AIServiceError("The AI service returned an error. Please try again later.") from exc
    if isinstance(exc, errors.ServerError):
        logger.error("Gemini server error during %s: %s", context, exc)
        raise AIServiceError("The AI service returned an error. Please try again later.") from exc
    if isinstance(exc, TimeoutError):
        logger.warning("Gemini timeout during %s: %s", context, exc)
        raise AIServiceError("The AI service took too long to respond. Please try again.") from exc
    if isinstance(exc, errors.APIError):
        logger.error("Gemini API error during %s: %s", context, exc)
        raise AIServiceError("The AI service returned an error. Please try again later.") from exc
    # Fallback for anything unexpected (network errors, etc.)
    logger.error("Unexpected error calling Gemini during %s: %s", context, exc)
    raise AIServiceError("The AI service returned an error. Please try again later.") from exc


async def _stream_with_retry(
    model: str, contents, config: "types.GenerateContentConfig", context: str
) -> AsyncGenerator[str, None]:
    """
    Call Gemini's streaming endpoint, automatically retrying transient 503
    "high demand" overload errors (with a short backoff) as long as nothing
    has been yielded to the caller yet for the current attempt. All other
    errors (and any failure that occurs after streaming has already started)
    are translated via `_raise_for_gemini_error` and propagated immediately.
    """
    client = get_client()
    attempt = 0

    while True:
        yielded_any = False
        try:
            stream = await client.aio.models.generate_content_stream(
                model=model, contents=contents, config=config
            )
            async for chunk in stream:
                token = getattr(chunk, "text", None)
                if token:
                    yielded_any = True
                    yield token
            return  # completed successfully
        except AIServiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - translate any SDK/network error
            is_overload = isinstance(exc, errors.ServerError)
            if is_overload and not yielded_any and attempt < _MAX_OVERLOAD_RETRIES:
                attempt += 1
                delay = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Gemini overloaded (503) during %s \u2014 retrying in %.0fs "
                    "(attempt %d/%d): %s",
                    context, delay, attempt, _MAX_OVERLOAD_RETRIES, exc,
                )
                await asyncio.sleep(delay)
                continue  # retry the whole request fresh
            _raise_for_gemini_error(exc, context)


async def stream_plan_generation(prompt: str) -> AsyncGenerator[str, None]:
    """
    Stream the AI-generated workout + meal plan token-by-token.

    Yields plain text chunks as they arrive from Gemini. Callers (the
    router) are responsible for wrapping these chunks in the transport
    format (e.g. Server-Sent Events). Transient 503 overload errors are
    retried automatically before any content is yielded (see
    `_stream_with_retry`).
    """
    config = types.GenerateContentConfig(
        system_instruction=BASE_SYSTEM_PROMPT,
        temperature=settings.gemini_temperature_plan,
        max_output_tokens=settings.gemini_max_tokens_plan,
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    async for token in _stream_with_retry(
        settings.gemini_model, contents, config, "plan generation"
    ):
        yield token


async def stream_chat_response(messages: List[dict]) -> AsyncGenerator[str, None]:
    """Stream an AI chat reply token-by-token, given a full messages array
    in the same chat-style shape produced by prompt_builder.build_chat_messages.
    Transient 503 overload errors are retried automatically before any
    content is yielded (see `_stream_with_retry`)."""
    system_instruction, contents = _messages_to_gemini(messages)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=settings.gemini_temperature_chat,
        max_output_tokens=settings.gemini_max_tokens_chat,
    )
    async for token in _stream_with_retry(
        settings.gemini_chat_model, contents, config, "chat"
    ):
        yield token
