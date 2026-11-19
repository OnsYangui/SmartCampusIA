"""SA-25 — sessions visiteurs : ouverture, cookie, expiration et isolation.
SA-29 — rattachement d'une session visiteur à un compte candidat.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.core.config import get_settings
from app.core.passwords import hash_password  # adapte le nom si besoin
from app.main import app
from tests.factories import UNKNOWN_ID, insert

SESSIONS = "/api/v1/sessions"


# ---------------------------------------------------------------- SA-25


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


# ---------------------------------------------------------------- SA-29

PASSWORD = "motdepasse-test-1"


def make_user(conn: Connection, role: str = "candidate") -> tuple[uuid.UUID, str]:
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    user_id = insert(conn, "users", email=email, password_hash=hash_password(PASSWORD), role=role)
    return user_id, email


def login(api: TestClient, email: str) -> dict[str, str]:
    """Connecte le compte et renvoie l'en-tête CSRF à joindre aux requêtes POST."""
    response = api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"X-CSRF-Token": api.cookies.get("csrf_token")}


def link(api: TestClient, session_id: str, headers: dict[str, str] | None, consent: bool = True):
    return api.post(f"{SESSIONS}/{session_id}/link", json={"consent": consent}, headers=headers)


def visitor_row(conn: Connection, session_id: str):
    return conn.execute(
        text(
            "SELECT c.id, c.user_id, c.status FROM conversations v "
            "JOIN candidates c ON c.id = v.candidate_id WHERE v.id = :id"
        ),
        {"id": session_id},
    ).one()


def test_link_session_to_candidate_account(api: TestClient, conn: Connection) -> None:
    session_id = api.post(SESSIONS).json()["id"]
    user_id, email = make_user(conn)
    headers = login(api, email)

    response = link(api, session_id, headers)

    assert response.status_code == 200
    row = visitor_row(conn, session_id)
    assert row.user_id == user_id
    assert row.status == "EN_PROFILAGE"
    consents = conn.execute(
        text("SELECT count(*) FROM consents WHERE candidate_id = :id"), {"id": row.id}
    ).scalar_one()
    assert consents == 1


def test_link_without_consent_is_rejected(api: TestClient, conn: Connection) -> None:
    session_id = api.post(SESSIONS).json()["id"]
    _, email = make_user(conn)
    headers = login(api, email)

    response = link(api, session_id, headers, consent=False)

    assert response.status_code == 422
    assert visitor_row(conn, session_id).user_id is None


def test_link_requires_login(api: TestClient) -> None:
    session_id = api.post(SESSIONS).json()["id"]

    assert link(api, session_id, None).status_code == 401


def test_link_requires_csrf_header(api: TestClient, conn: Connection) -> None:
    session_id = api.post(SESSIONS).json()["id"]
    _, email = make_user(conn)
    login(api, email)

    assert link(api, session_id, None).status_code == 403


def test_link_rejects_non_candidate_account(api: TestClient, conn: Connection) -> None:
    session_id = api.post(SESSIONS).json()["id"]
    _, email = make_user(conn, role="admin")
    headers = login(api, email)

    assert link(api, session_id, headers).status_code == 403


def test_link_cannot_use_another_visitors_session(api: TestClient, conn: Connection) -> None:
    first_session = api.post(SESSIONS).json()["id"]
    api.cookies.clear()
    api.post(SESSIONS)  # second visiteur
    _, email = make_user(conn)
    headers = login(api, email)

    response = link(api, first_session, headers)

    assert response.status_code == 404
    assert visitor_row(conn, first_session).user_id is None


def test_link_twice_is_rejected(api: TestClient, conn: Connection) -> None:
    session_id = api.post(SESSIONS).json()["id"]
    _, email = make_user(conn)
    headers = login(api, email)
    assert link(api, session_id, headers).status_code == 200

    # Le cookie visiteur a été supprimé : la session n'est plus une session anonyme.
    assert link(api, session_id, headers).status_code == 401


def test_link_moves_conversation_to_existing_candidate(api: TestClient, conn: Connection) -> None:
    session_id = api.post(SESSIONS).json()["id"]
    anonymous_id = visitor_row(conn, session_id).id
    user_id, email = make_user(conn)
    existing_id = insert(conn, "candidates", user_id=user_id, session_id_hash="a" * 64)
    headers = login(api, email)

    response = link(api, session_id, headers)

    assert response.status_code == 200
    assert visitor_row(conn, session_id).id == existing_id
    gone = conn.execute(
        text("SELECT count(*) FROM candidates WHERE id = :id"), {"id": anonymous_id}
    ).scalar_one()
    assert gone == 0
