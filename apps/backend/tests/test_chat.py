"""SA-36/37 — Ollama API and session memory, without the external model."""

import asyncio
from typing import Any

import httpx
import pytest

from app.core.config import Settings
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


def chat_route_module():
    from app.api.routes import chat

    return chat


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
    assert "Never present admissions rules" in body["messages"][0]["content"]
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


def test_chat_api_returns_generated_answer(api, monkeypatch: pytest.MonkeyPatch) -> None:
    chat_route = chat_route_module()

    async def generated_answer(*_: Any) -> str:
        return "Bonjour, comment puis-je vous aider ?"

    monkeypatch.setattr(chat_route, "reply", generated_answer)
    session = api.post("/api/v1/sessions")
    conversation_id = session.json()["id"]
    response = api.post(
        "/api/v1/chat",
        json={"conversation_id": conversation_id, "message": "Bonjour"},
    )

    assert session.status_code == 201
    assert response.status_code == 200
    assert response.json() == {
        "message": "Bonjour, comment puis-je vous aider ?",
        "model": "qwen3:4b",
    }


def test_chat_api_sends_recent_session_context(api, monkeypatch: pytest.MonkeyPatch) -> None:
    chat_route = chat_route_module()
    received: list[tuple[str, list[ChatTurn], str | None]] = []

    async def generated_answer(
        _settings: Settings,
        message: str,
        history: list[ChatTurn],
        summary: str | None,
    ) -> str:
        received.append((message, history, summary))
        return (
            "Première réponse"
            if len(received) == 1
            else "Je ne peux pas vérifier sa durée officielle. Consultez l'établissement."
        )

    monkeypatch.setattr(chat_route, "reply", generated_answer)
    session = api.post("/api/v1/sessions")
    conversation_id = session.json()["id"]

    first = api.post(
        "/api/v1/chat",
        json={"conversation_id": conversation_id, "message": "Je cherche une licence."},
    )
    second = api.post(
        "/api/v1/chat",
        json={"conversation_id": conversation_id, "message": "Et sa durée ?"},
    )

    assert first.status_code == second.status_code == 200
    assert received[0] == ("Je cherche une licence.", [], None)
    assert received[1] == (
        "Et sa durée ?",
        [
            ChatTurn(role="user", content="Je cherche une licence."),
            ChatTurn(role="assistant", content="Première réponse"),
        ],
        None,
    )


def test_chat_api_rejects_another_visitors_conversation(
    api, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_route = chat_route_module()
    calls = 0

    async def generated_answer(*_: Any) -> str:
        nonlocal calls
        calls += 1
        return "Réponse"

    monkeypatch.setattr(chat_route, "reply", generated_answer)
    first_conversation = api.post("/api/v1/sessions").json()["id"]
    assert (
        api.post(
            "/api/v1/chat",
            json={"conversation_id": first_conversation, "message": "Question privée"},
        ).status_code
        == 200
    )

    api.post("/api/v1/sessions")  # replaces the browser's visitor cookie
    response = api.post(
        "/api/v1/chat",
        json={"conversation_id": first_conversation, "message": "Autre question"},
    )

    assert response.status_code == 404
    assert calls == 1


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (chat_service.LLMUnavailableError(), 503),
        (chat_service.LLMResponseError(), 503),
        (chat_service.LLMTimeoutError(), 504),
    ],
)
def test_chat_api_returns_provider_errors(
    api, monkeypatch: pytest.MonkeyPatch, error: Exception, status_code: int
) -> None:
    chat_route = chat_route_module()

    async def failed_answer(*_: Any) -> str:
        raise error

    monkeypatch.setattr(chat_route, "reply", failed_answer)
    conversation_id = api.post("/api/v1/sessions").json()["id"]
    response = api.post(
        "/api/v1/chat",
        json={"conversation_id": conversation_id, "message": "Question"},
    )

    assert response.status_code == status_code
    assert response.json()["message"]
