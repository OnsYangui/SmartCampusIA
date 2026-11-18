"""SA-28 — authentication, cookies, CSRF and role enforcement."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.api.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE
from app.core.config import Settings, get_settings
from app.core.passwords import hash_password, needs_rehash, verify_password
from app.core.security import Principal
from app.core.tokens import (
    ALGORITHM,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    csrf_token_for,
    decode_token,
)
from tests.factories import insert

PASSWORD = "Un-mot-de-passe-solide-42"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
MANAGE_PROGRAMS = "/api/v1/manage/programs"


def make_user(
    conn: Connection,
    email: str = "resp@example.com",
    role: str = "admin",
    institution: uuid.UUID | None = None,
    **values,
) -> uuid.UUID:
    return insert(
        conn,
        "users",
        email=email,
        password_hash=values.pop("password_hash", hash_password(PASSWORD)),
        role=role,
        institution_id=institution,
        **values,
    )


def sign_in(api: TestClient, email: str = "resp@example.com", password: str = PASSWORD):
    return api.post(LOGIN, json={"email": email, "password": password})


def csrf(api: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: api.cookies[CSRF_COOKIE]}


# Passwords
def test_password_round_trip_uses_argon2id() -> None:
    hashed = hash_password(PASSWORD)

    assert hashed.startswith("$argon2id$")
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("autre", hashed)
    assert not needs_rehash(hashed)


@pytest.mark.parametrize("stored", ["!disabled:demo-login-not-configured", "", "plaintext"])
def test_a_value_that_is_not_an_argon2_hash_never_matches(stored: str) -> None:
    assert not verify_password(stored, stored)
    assert not verify_password(PASSWORD, stored)


# Login
def test_login_returns_the_account_and_sets_the_three_cookies(
    api: TestClient, conn: Connection
) -> None:
    user_id = make_user(conn, role="admin")

    response = sign_in(api)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user_id),
        "email": "resp@example.com",
        "role": "admin",
        "institution_id": None,
    }
    assert "password" not in response.text
    cookies = {c.split("=", 1)[0]: c for c in response.headers.get_list("set-cookie")}
    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE}
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        assert "httponly" in cookies[name].lower()
    assert "httponly" not in cookies[CSRF_COOKIE].lower()
    assert all("samesite=lax" in c.lower() for c in cookies.values())
    assert "path=/api/v1/auth" in cookies[REFRESH_COOKIE].lower()


def test_login_ignores_email_case_and_surrounding_spaces(api: TestClient, conn: Connection) -> None:
    make_user(conn, email="resp@example.com")

    assert sign_in(api, "  RESP@Example.COM ").status_code == 200


def test_the_token_carries_the_role_and_the_institution(
    api: TestClient, conn: Connection, catalog
) -> None:
    make_user(conn, role="academic_manager", institution=catalog["iit"])

    sign_in(api)
    claims = decode_token(get_settings(), api.cookies[ACCESS_COOKIE], "access")

    assert claims.role == "academic_manager"
    assert claims.institution_id == catalog["iit"]


@pytest.mark.parametrize(
    ("email", "password", "active"),
    [
        ("resp@example.com", "mauvais", True),
        ("inconnu@example.com", PASSWORD, True),
        ("resp@example.com", PASSWORD, False),
    ],
    ids=["wrong password", "unknown e-mail", "disabled account"],
)
def test_every_login_failure_looks_the_same(
    api: TestClient, conn: Connection, email: str, password: str, active: bool
) -> None:
    make_user(conn, is_active=active)

    response = sign_in(api, email, password)

    assert response.status_code == 401
    assert response.json() == {
        "code": "unauthenticated",
        "message": "E-mail ou mot de passe incorrect",
    }
    assert not response.headers.get_list("set-cookie")


def test_a_demonstration_account_without_password_cannot_log_in(
    api: TestClient, conn: Connection
) -> None:
    make_user(conn, password_hash="!disabled:demo-login-not-configured")

    assert sign_in(api, password="!disabled:demo-login-not-configured").status_code == 401


def test_an_outdated_hash_is_replaced_by_a_current_one(api: TestClient, conn: Connection) -> None:
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    make_user(conn, password_hash=weak)

    assert sign_in(api).status_code == 200

    stored = conn.execute(text("SELECT password_hash FROM users")).scalar_one()
    assert stored != weak
    assert not needs_rehash(stored)


@pytest.mark.parametrize("body", [{}, {"email": "a@b.c"}, {"email": "a@b.c", "password": ""}])
def test_login_validates_its_body(api: TestClient, body: dict) -> None:
    assert api.post(LOGIN, json=body).status_code == 422


# Current account
def test_me_requires_a_session(api: TestClient) -> None:
    response = api.get(ME)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_me_describes_the_signed_in_account(api: TestClient, conn: Connection) -> None:
    make_user(conn, role="management")
    sign_in(api)

    body = api.get(ME).json()

    assert body["email"] == "resp@example.com"
    assert body["role"] == "management"


def test_me_rejects_an_account_disabled_after_login(api: TestClient, conn: Connection) -> None:
    make_user(conn)
    sign_in(api)
    conn.execute(text("UPDATE users SET is_active = false"))

    assert api.get(ME).status_code == 401


# Tokens
def settings() -> Settings:
    return get_settings()


def principal() -> Principal:
    return Principal(user_id=uuid.uuid4(), role="admin", institution_id=None)


def test_a_tampered_token_is_refused(api: TestClient) -> None:
    token = create_access_token(settings(), principal(), "sid")
    api.cookies.set(ACCESS_COOKIE, token[:-3] + "abc")

    assert api.get(ME).status_code == 401


def test_an_expired_token_is_refused(api: TestClient) -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    api.cookies.set(ACCESS_COOKIE, create_access_token(settings(), principal(), "sid", now=past))

    assert api.get(ME).status_code == 401


def test_a_token_signed_with_another_secret_is_refused(api: TestClient) -> None:
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "sid": "sid",
            "role": "admin",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "x" * 40,
        algorithm=ALGORITHM,
    )
    api.cookies.set(ACCESS_COOKIE, forged)

    assert api.get(ME).status_code == 401


def test_the_none_algorithm_is_refused(api: TestClient) -> None:
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "sid": "s",
            "role": "admin",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        None,
        algorithm="none",
    )
    api.cookies.set(ACCESS_COOKIE, forged)

    assert api.get(ME).status_code == 401


def test_a_refresh_token_cannot_be_used_as_an_access_token() -> None:
    token = create_refresh_token(settings(), uuid.uuid4(), "sid")

    with pytest.raises(InvalidTokenError):
        decode_token(settings(), token, "access")


def test_an_access_token_cannot_be_used_to_refresh() -> None:
    token = create_access_token(settings(), principal(), "sid")

    with pytest.raises(InvalidTokenError):
        decode_token(settings(), token, "refresh")


def test_a_token_with_an_unknown_role_is_refused() -> None:
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "sid": "s",
            "role": "root",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings().jwt_secret,
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidTokenError):
        decode_token(settings(), forged, "access")


# CSRF
def test_a_state_changing_request_needs_the_csrf_header(api: TestClient, conn: Connection) -> None:
    make_user(conn, role="admin")
    sign_in(api)

    missing = api.post(MANAGE_PROGRAMS, json={})
    wrong = api.post(MANAGE_PROGRAMS, json={}, headers={CSRF_HEADER: "0" * 64})
    valid = api.post(MANAGE_PROGRAMS, json={}, headers=csrf(api))

    assert missing.status_code == 403
    assert missing.json()["code"] == "forbidden"
    assert wrong.status_code == 403
    assert valid.status_code == 422  # past authentication, rejected by body validation


def test_reading_does_not_need_the_csrf_header(api: TestClient, conn: Connection) -> None:
    make_user(conn, role="admin")
    sign_in(api)

    assert api.get(MANAGE_PROGRAMS).status_code == 200


def test_the_csrf_token_of_another_session_is_refused(api: TestClient, conn: Connection) -> None:
    make_user(conn, role="admin")
    sign_in(api)

    other = csrf_token_for(settings(), "another-session")

    assert api.post(MANAGE_PROGRAMS, json={}, headers={CSRF_HEADER: other}).status_code == 403


# Roles
@pytest.mark.parametrize(
    ("role", "status"),
    [
        ("candidate", 403),
        ("interview_manager", 403),
        ("management", 403),
        ("academic_manager", 200),
        ("admin", 200),
    ],
)
def test_catalog_management_is_limited_to_the_right_roles(
    api: TestClient, conn: Connection, catalog, role: str, status: int
) -> None:
    institution = catalog["iit"] if role in ("academic_manager", "interview_manager") else None
    make_user(conn, role=role, institution=institution)
    sign_in(api)

    assert api.get(MANAGE_PROGRAMS).status_code == status


def test_without_a_session_protected_routes_answer_401(api: TestClient) -> None:
    assert api.get(MANAGE_PROGRAMS).status_code == 401


def test_require_roles_rejects_unknown_roles() -> None:
    from app.api.security import require_roles

    with pytest.raises(ValueError, match="inconnus"):
        require_roles("root")
    with pytest.raises(ValueError):
        require_roles()


def test_require_roles_lets_only_the_listed_roles_through(
    api: TestClient, conn: Connection
) -> None:
    from fastapi import Depends

    from app.api.security import require_roles
    from app.main import app

    @app.get("/_test/management-only", dependencies=[Depends(require_roles("management"))])
    def management_only() -> dict[str, bool]:
        return {"ok": True}

    try:
        make_user(conn, role="management", email="dir@example.com")
        make_user(conn, role="candidate", email="cand@example.com")
        sign_in(api, "cand@example.com")
        assert api.get("/_test/management-only").status_code == 403
        sign_in(api, "dir@example.com")
        assert api.get("/_test/management-only").status_code == 200
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", "") != "/_test/management-only"
        ]


# Refresh
def test_refresh_issues_new_cookies_for_the_same_session(api: TestClient, conn: Connection) -> None:
    make_user(conn)
    sign_in(api)
    first_csrf = api.cookies[CSRF_COOKIE]
    sid = decode_token(settings(), api.cookies[REFRESH_COOKIE], "refresh").session_id

    response = api.post(REFRESH, headers={CSRF_HEADER: first_csrf})

    assert response.status_code == 200
    assert decode_token(settings(), api.cookies[ACCESS_COOKIE], "access").session_id == sid
    assert api.cookies[CSRF_COOKIE] == first_csrf


def test_refresh_needs_a_refresh_cookie(api: TestClient) -> None:
    assert api.post(REFRESH).status_code == 401


def test_refresh_needs_the_csrf_header(api: TestClient, conn: Connection) -> None:
    make_user(conn)
    sign_in(api)

    assert api.post(REFRESH).status_code == 403


def test_refresh_picks_up_a_role_change(api: TestClient, conn: Connection) -> None:
    make_user(conn, role="admin")
    sign_in(api)
    conn.execute(text("UPDATE users SET role = 'management'"))

    api.post(REFRESH, headers=csrf(api))

    assert decode_token(settings(), api.cookies[ACCESS_COOKIE], "access").role == "management"


def test_refresh_refuses_an_account_disabled_since_login(api: TestClient, conn: Connection) -> None:
    make_user(conn)
    sign_in(api)
    conn.execute(text("UPDATE users SET is_active = false"))

    response = api.post(REFRESH, headers=csrf(api))

    assert response.status_code == 401


def test_refresh_refuses_an_expired_refresh_token(api: TestClient, conn: Connection) -> None:
    user_id = make_user(conn)
    past = datetime.now(UTC) - timedelta(days=30)
    api.cookies.set(REFRESH_COOKIE, create_refresh_token(settings(), user_id, "sid", now=past))

    headers = {CSRF_HEADER: csrf_token_for(settings(), "sid")}

    assert api.post(REFRESH, headers=headers).status_code == 401


# Logout
def test_logout_removes_the_cookies(api: TestClient, conn: Connection) -> None:
    make_user(conn)
    sign_in(api)

    response = api.post(LOGOUT)

    assert response.status_code == 204
    assert not api.cookies.get(ACCESS_COOKIE)
    assert api.get(ME).status_code == 401


def test_logout_without_a_session_is_harmless(api: TestClient) -> None:
    assert api.post(LOGOUT).status_code == 204
