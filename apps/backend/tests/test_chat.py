"""SA-36 — API et communication Ollama, sans dépendance au modèle externe."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import register_error_handlers
from app.api.routes import chat as chat_route
from app.core.config import Settings, get_settings
from app.schemas.chat import ChatTurn
from app.services import chat as chat_service


class StubResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class StubClient:
    def __init__(
        self,
        *,
        response: StubResponse | None = None,
        error: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        self.response = response
        self.error = error
        self.options = kwargs
        self.request: dict[str, Any] | None = None

    async def __aenter__(self) -> "StubClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, path: str, *, json: dict[str, Any]) -> StubResponse:
        self.request = {"path": path, "json": json}
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def test_reply_sends_configured_ollama_request(monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[StubClient] = []

    def create_client(**kwargs: Any) -> StubClient:
        client = StubClient(
            response=StubResponse({"message": {"content": "Bonjour !"}}), **kwargs
        )
        clients.append(client)
        return client

    monkeypatch.setattr(chat_service.httpx, "AsyncClient", create_client)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://app:secret@localhost/smartcampus",
        ollama_base_url="http://ollama.test:11434",
        ollama_model="qwen3:4b",
        ollama_timeout_seconds=45,
        ollama_temperature=0.2,
    )

    answer = asyncio.run(
        chat_service.reply(
            settings,
            "Bonjour",
            [ChatTurn(role="user", content="Salut"), ChatTurn(role="assistant", content="Bonjour")],
        )
    )

    assert answer == "Bonjour !"
    assert len(clients) == 1
    client = clients[0]
    assert client.options["base_url"] == "http://ollama.test:11434"
    assert client.options["timeout"].read == 45
    assert client.request is not None
    assert client.request["path"] == "/api/chat"
    body = client.request["json"]
    assert body["model"] == "qwen3:4b"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.2
    assert [message["role"] for message in body["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ConnectError("unavailable"), chat_service.LLMUnavailableError),
        (httpx.ReadTimeout("slow"), chat_service.LLMTimeoutError),
    ],
)
def test_reply_maps_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: type[Exception],
) -> None:
    client = StubClient(error=error)
    monkeypatch.setattr(chat_service.httpx, "AsyncClient", lambda **_: client)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://app:secret@localhost/smartcampus",
    )

    with pytest.raises(expected):
        asyncio.run(chat_service.reply(settings, "Question", []))


@pytest.mark.parametrize("payload", [{}, {"message": {"content": "  "}}, {"message": []}])
def test_reply_rejects_invalid_ollama_payloads(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    client = StubClient(response=StubResponse(payload))
    monkeypatch.setattr(chat_service.httpx, "AsyncClient", lambda **_: client)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://app:secret@localhost/smartcampus",
    )

    with pytest.raises(chat_service.LLMResponseError):
        asyncio.run(chat_service.reply(settings, "Question", []))


def api_client(monkeypatch: pytest.MonkeyPatch, reply: Callable[..., Any]) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(chat_route.router)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        database_url="postgresql+psycopg://app:secret@localhost/smartcampus",
        ollama_model="qwen3:4b",
    )
    monkeypatch.setattr(chat_route, "reply", reply)
    return TestClient(app)


def test_chat_api_returns_generated_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    async def generated_answer(*_: Any) -> str:
        return "Bonjour, comment puis-je vous aider ?"

    with api_client(monkeypatch, generated_answer) as client:
        response = client.post("/chat", json={"message": "Bonjour"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "Bonjour, comment puis-je vous aider ?",
        "model": "qwen3:4b",
    }


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (chat_service.LLMUnavailableError(), 503),
        (chat_service.LLMResponseError(), 503),
        (chat_service.LLMTimeoutError(), 504),
    ],
)
def test_chat_api_returns_provider_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status_code: int
) -> None:
    async def failed_answer(*_: Any) -> str:
        raise error

    with api_client(monkeypatch, failed_answer) as client:
        response = client.post("/chat", json={"message": "Question"})

    assert response.status_code == status_code
    assert response.json()["message"]
