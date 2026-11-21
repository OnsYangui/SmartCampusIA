import httpx

from app.core.config import Settings
from app.schemas.chat import ChatTurn

SYSTEM_PROMPT = (
    "You are SmartCampus AI, a helpful university orientation assistant "
    "for IIT and ISB in Tunisia.\n"
    "Reply in the language and style used by the student, including French, Tunisian Arabic, "
    "or Arabizi.\n"
    "Be concise, ask clarifying questions when useful, and never invent admission rules, fees, "
    "deadlines,\n"
    "or program details. Explain that official university sources must verify those details."
)


class LLMUnavailableError(Exception):
    """Ollama could not be reached or rejected the configured model request."""


class LLMTimeoutError(Exception):
    """Ollama did not complete the request before the configured timeout."""


class LLMResponseError(Exception):
    """Ollama returned a response that does not match its chat API contract."""


async def reply(settings: Settings, message: str, history: list[ChatTurn]) -> str:
    timeout = httpx.Timeout(
        settings.ollama_timeout_seconds,
        connect=min(5.0, settings.ollama_timeout_seconds),
    )
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=timeout) as client:
            response = await client.post(
                "/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "think": False,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *[turn.model_dump() for turn in history],
                        {"role": "user", "content": message},
                    ],
                    "options": {"temperature": settings.ollama_temperature},
                },
            )
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError from exc
    except httpx.HTTPError as exc:
        raise LLMUnavailableError from exc

    try:
        payload = response.json()
        content = payload["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMResponseError from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMResponseError("Ollama returned an empty or invalid message")
    return content.strip()
