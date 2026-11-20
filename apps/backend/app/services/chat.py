import httpx

from app.core.config import Settings
from app.schemas.chat import ChatTurn

SYSTEM_PROMPT = """You are SmartCampus AI, a helpful university orientation assistant for IIT and ISB in Tunisia.
Reply in the language and style used by the student, including French, Tunisian Arabic, or Arabizi.
Be concise, ask clarifying questions when useful, and never invent admission rules, fees, deadlines,
or program details. Explain that official university sources must verify those details."""


async def reply(settings: Settings, message: str, history: list[ChatTurn]) -> str:
    timeout = httpx.Timeout(settings.ollama_timeout_seconds, connect=5.0)
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
                "options": {"temperature": 0.3},
            },
        )
        response.raise_for_status()
        content = response.json()["message"]["content"].strip()
        if not content:
            raise ValueError("Ollama returned an empty response")
        return content
