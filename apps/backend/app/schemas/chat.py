from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

ChatMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: ChatMessage


class ChatRequest(BaseModel):
    message: ChatMessage
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)


class ChatResponse(BaseModel):
    message: str
    model: str
