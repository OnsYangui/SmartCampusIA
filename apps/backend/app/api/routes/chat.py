from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import (
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
    reply,
)

router = APIRouter(prefix="/chat", tags=["chat"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, settings: SettingsDep) -> ChatResponse:
    """Generate a single-turn orientation reply with the configured Ollama model."""
    try:
        content = await reply(settings, request.message, request.history)
    except LLMTimeoutError as exc:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "Le modèle IA n'a pas répondu dans le délai imparti.",
        ) from exc
    except (LLMUnavailableError, LLMResponseError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "L'assistant IA est temporairement indisponible.",
        ) from exc
    return ChatResponse(message=content, model=settings.ollama_model)
