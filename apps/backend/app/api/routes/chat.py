from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.visitor import VisitorDep
from app.core.config import Settings, get_settings
from app.core.db import SessionDep
from app.models import Conversation
from app.schemas.chat import ChatRequest, ChatResponse, ChatTurn
from app.services.chat import (
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
    reply,
)
from app.services.memory import (
    EmptyMessageError,
    MessageLimitReachedError,
    MessageTooLongError,
    add_message,
    get_context,
)

router = APIRouter(prefix="/chat", tags=["chat"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    settings: SettingsDep,
    db: SessionDep,
    visitor: VisitorDep,
) -> ChatResponse:
    """Generate a reply using only the authenticated visitor's conversation memory."""
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == request.conversation_id,
            Conversation.candidate_id == visitor.id,
        )
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable")

    context = get_context(db, conversation, settings)
    try:
        add_message(db, conversation, visitor, "candidate", request.message, settings)
    except (EmptyMessageError, MessageTooLongError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except MessageLimitReachedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc

    try:
        history = [ChatTurn.model_validate(turn) for turn in context["messages"]]
        content = await reply(settings, request.message, history, context["summary"])
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
    add_message(db, conversation, visitor, "assistant", content, settings)
    return ChatResponse(message=content, model=settings.ollama_model)
