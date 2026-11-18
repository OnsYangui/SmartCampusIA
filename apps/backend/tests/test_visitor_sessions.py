"""SA-25 — sessions visiteurs : ouverture, cookie, expiration et isolation."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.core.config import get_settings
from app.main import app
from tests.factories import UNKNOWN_ID

SESSIONS = "/api/v1/sessions"


def test_open_session_sets_http_only_cookie(api: TestClient) -> None:
    response = api.post(SESSIONS)

    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("sc_session=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_open_session_returns_expiry_within_24_hours(api: TestClient) -> None:
    body = api.post(SESSIONS).json()

    remaining = datetime.fromisoformat(body["expires_at"]) - datetime.now(UTC)
    assert body["id"]
    assert timedelta(hours=23) < remaining <= timedelta(hours=24)


def test_open_session_creates_anonymous_visitor(api: TestClient, conn: Connection) -> None:
    response = api.post(SESSIONS)
    session_id = response.json()["id"]

    row = conn.execute(
        text(
            "SELECT c.status, c.user_id, c.session_id_hash "
            "FROM conversations v JOIN candidates c ON c.id = v.candidate_id "
            "WHERE v.id = :id"
        ),
        {"id": session_id},
    ).one()
    assert row.status == "VISITEUR"
    assert row.user_id is None
    # La base ne garde que l'empreinte SHA-256, jamais le jeton du cookie.
    assert len(row.session_id_hash) == 64
    assert row.session_id_hash != response.cookies["sc_session"]


def test_read_session_with_valid_cookie(api: TestClient) -> None:
    session_id = api.post(SESSIONS).json()["id"]

    response = api.get(f"{SESSIONS}/{session_id}")

    assert response.status_code == 200
    assert response.json()["id"] == session_id


def test_read_session_without_cookie_is_rejected(api: TestClient) -> None:
    api.post(SESSIONS)
    api.cookies.clear()

    response = api.get(f"{SESSIONS}/{UNKNOWN_ID}")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_read_session_with_unknown_token_is_rejected(api: TestClient) -> None:
    api.cookies.clear()

    response = api.get(f"{SESSIONS}/{UNKNOWN_ID}", headers={"Cookie": "sc_session=faux-jeton"})

    assert response.status_code == 401


def test_expired_session_is_rejected(api: TestClient) -> None:
    session_id = api.post(SESSIONS).json()["id"]
    # Durée d'inactivité à 0 minute : la session est expirée dès qu'on la relit.
    expired = get_settings().model_copy(update={"session_idle_ttl_minutes": 0})
    app.dependency_overrides[get_settings] = lambda: expired
    try:
        response = api.get(f"{SESSIONS}/{session_id}")
    finally:
        app.dependency_overrides.pop(get_settings)

    assert response.status_code == 401


def test_visitor_cannot_read_another_visitors_session(api: TestClient) -> None:
    first_session = api.post(SESSIONS).json()["id"]
    api.cookies.clear()
    api.post(SESSIONS)  # second visiteur : son cookie remplace le premier

    response = api.get(f"{SESSIONS}/{first_session}")

    assert response.status_code == 404
