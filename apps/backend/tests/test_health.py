from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "SmartCampus AI API"
    assert body["database"] == "ok"


def test_health_is_exposed_under_api_v1() -> None:
    # The Next.js proxy forwards /api/v1/* to the backend.
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cors_allows_frontend_origin() -> None:
    response = client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin() -> None:
    response = client.get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_health_reports_unavailable_database() -> None:
    from sqlalchemy.exc import OperationalError

    from app.core.db import get_session

    class BrokenSession:
        def execute(self, *_args: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_session] = lambda: BrokenSession()
    try:
        response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


def test_app_role_cannot_create_tables(conn) -> None:
    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    with pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("CREATE TABLE sa16_should_fail (id int)"))


def test_app_role_cannot_modify_alembic_revision(conn) -> None:
    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    with pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("UPDATE alembic_version SET version_num = version_num"))
