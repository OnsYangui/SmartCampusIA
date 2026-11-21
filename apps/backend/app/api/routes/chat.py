from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import reply

router = APIRouter(prefix="/chat", tags=["chat"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, settings: SettingsDep) -> ChatResponse:
    """Generate a single-turn orientation reply with the configured Ollama model."""
    try:
        content = await reply(settings, request.message, request.history)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            (
                "The AI assistant is temporarily unavailable. Check that Ollama is running "
                "and the model is pulled."
            ),
        ) from exc
    return ChatResponse(message=content, model=settings.ollama_model)
