from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, StringConstraints

ChatMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: ChatMessage


class ChatRequest(BaseModel):
    conversation_id: UUID
    message: ChatMessage


class ChatResponse(BaseModel):
    message: str
    model: str
