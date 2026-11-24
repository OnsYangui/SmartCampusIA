"""SA-41 — management API of the official documents: access, upload, versions and archiving."""

import hashlib
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.api.security import Principal, get_principal
from app.core.config import get_settings
from app.main import app
from tests.factories import UNKNOWN_ID, insert

DOCUMENTS = "/api/v1/documents"
EMBEDDING = "[1," + ",".join(["0"] * 1023) + "]"
PDF = b"%PDF-1.4\n% premiere version\n"
PDF_V2 = b"%PDF-1.4\n% seconde version\n"


@pytest.fixture
def login() -> Iterator[Callable[..., None]]:
    def as_user(
        role: str, institution: uuid.UUID | None = None, user: uuid.UUID | None = None
    ) -> None:
        principal = Principal(user_id=user or uuid.uuid4(), role=role, institution_id=institution)
        app.dependency_overrides[get_principal] = lambda: principal

    yield as_user
    app.dependency_overrides.pop(get_principal, None)


@pytest.fixture
def uploader(conn: Connection) -> uuid.UUID:
    return insert(conn, "users", email="depot@test.tn", password_hash="x", role="admin")


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sends the uploaded files to a temporary folder, with a 1 KB limit."""
    settings = get_settings()
    monkeypatch.setattr(settings, "documents_dir", tmp_path)
    monkeypatch.setattr(settings, "document_max_bytes", 1024)
    return tmp_path


def make_document(
    conn: Connection, institution: uuid.UUID, uploader: uuid.UUID, title: str = "Guide", **values
) -> uuid.UUID:
    return insert(
        conn,
        "documents",
        institution_id=institution,
        title=title,
        source_type="pdf",
        source_uri=f"{institution}/{uuid.uuid4()}.pdf",
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        uploaded_by=uploader,
        **values,
    )


def add_current_fragment(conn: Connection, document: uuid.UUID, institution: uuid.UUID) -> None:
    conn.execute(
        text(
            "INSERT INTO document_fragments "
            "(document_id, institution_id, document_version, position, content, embedding, "
            "is_current) VALUES (:document, :institution, 1, 0, 'Texte', "
            "CAST(:embedding AS vector), true)"
        ),
        {"document": document, "institution": institution, "embedding": EMBEDDING},
    )


def current_fragments(conn: Connection, document: uuid.UUID) -> int:
    return conn.execute(
        text("SELECT count(*) FROM document_fragments WHERE document_id = :d AND is_current"),
        {"d": document},
    ).scalar_one()


def syncs(conn: Connection, document: str | uuid.UUID) -> list[tuple]:
    rows = conn.execute(
        text(
            "SELECT document_version, trigger_type, status FROM document_syncs "
            "WHERE document_id = :d ORDER BY document_version"
        ),
        {"d": str(document)},
    )
    return [tuple(row) for row in rows]


def upload(api: TestClient, content: bytes = PDF, title: str = "Guide d'admission", **data):
    return api.post(
        DOCUMENTS,
        files={"file": ("guide.pdf", content, "application/pdf")},
        data={"title": title, **{name: str(value) for name, value in data.items()}},
    )


def new_version(api: TestClient, document: str, content: bytes = PDF_V2):
    return api.post(
        f"{DOCUMENTS}/{document}/versions",
        files={"file": ("guide.pdf", content, "application/pdf")},
    )


def pdf_files(folder: Path) -> list[Path]:
    return list(folder.rglob("*.pdf"))


# Authorization
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", ""),
        ("post", ""),
        ("get", f"/{UNKNOWN_ID}"),
        ("put", f"/{UNKNOWN_ID}"),
        ("post", f"/{UNKNOWN_ID}/versions"),
        ("delete", f"/{UNKNOWN_ID}"),
    ],
)
def test_documents_require_authentication(api: TestClient, method: str, path: str) -> None:
    response = api.request(method, DOCUMENTS + path, json={})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


@pytest.mark.parametrize("role", ["candidate", "interview_manager", "management"])
def test_documents_are_reserved_to_catalogue_managers(
    api: TestClient, login, catalog, role: str
) -> None:
    login(role, catalog["iit"] if role == "interview_manager" else None)

    assert api.get(DOCUMENTS).status_code == 403


# Listing
def test_a_manager_lists_only_the_documents_of_their_institution(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    mine = make_document(conn, catalog["iit"], uploader, "Guide IIT")
    make_document(conn, catalog["isb"], uploader, "Guide ISB")
    login("academic_manager", catalog["iit"])

    body = api.get(DOCUMENTS).json()

    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(mine)]


def test_an_admin_lists_every_institution_and_can_filter(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    make_document(conn, catalog["iit"], uploader)
    isb = make_document(conn, catalog["isb"], uploader)
    make_document(conn, catalog["isb"], uploader, status="archived")
    login("admin")

    assert api.get(DOCUMENTS).json()["total"] == 3
    only_isb = api.get(DOCUMENTS, params={"institution_id": str(catalog["isb"])}).json()
    assert only_isb["total"] == 2
    active_isb = api.get(
        DOCUMENTS, params={"institution_id": str(catalog["isb"]), "status": "active"}
    ).json()
    assert [item["id"] for item in active_isb["items"]] == [str(isb)]


def test_the_list_is_paginated(api: TestClient, login, conn: Connection, catalog, uploader) -> None:
    for number in range(3):
        make_document(conn, catalog["iit"], uploader, f"Document {number}")
    login("admin")

    first = api.get(DOCUMENTS, params={"size": 2}).json()
    second = api.get(DOCUMENTS, params={"size": 2, "page": 2}).json()

    assert (first["total"], len(first["items"])) == (3, 2)
    assert len(second["items"]) == 1


def test_the_status_filter_refuses_unknown_values(api: TestClient, login) -> None:
    login("admin")

    assert api.get(DOCUMENTS, params={"status": "deleted"}).status_code == 422


# Reading
def test_a_document_is_returned_without_its_storage_path(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    document = make_document(conn, catalog["iit"], uploader, "Brochure 2026")
    login("academic_manager", catalog["iit"])

    response = api.get(f"{DOCUMENTS}/{document}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Brochure 2026"
    assert body["source_type"] == "pdf"
    assert body["status"] == "active"
    assert body["version"] == 0
    assert "source_uri" not in body


def test_a_document_of_another_institution_answers_404(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    foreign = make_document(conn, catalog["isb"], uploader)
    login("academic_manager", catalog["iit"])

    assert api.get(f"{DOCUMENTS}/{foreign}").status_code == 404
    assert api.put(f"{DOCUMENTS}/{foreign}", json={"title": "X"}).status_code == 404
    assert api.delete(f"{DOCUMENTS}/{foreign}").status_code == 404


def test_an_unknown_document_answers_404(api: TestClient, login) -> None:
    login("admin")

    assert api.get(f"{DOCUMENTS}/{UNKNOWN_ID}").status_code == 404


# Adding a document
def test_a_manager_uploads_a_pdf_for_their_institution(
    api: TestClient, login, conn: Connection, catalog, uploader, storage: Path
) -> None:
    login("academic_manager", catalog["iit"], uploader)

    response = upload(api, program_id=catalog["info"])

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Guide d'admission"
    assert body["institution_id"] == str(catalog["iit"])
    assert body["program_id"] == str(catalog["info"])
    assert body["status"] == "active"
    assert body["version"] == 0
    assert body["content_hash"] == hashlib.sha256(PDF).hexdigest()
    assert body["uploaded_by"] == str(uploader)
    assert "source_uri" not in body
    source_uri = conn.execute(
        text("SELECT source_uri FROM documents WHERE id = :d"), {"d": body["id"]}
    ).scalar_one()
    assert (storage / source_uri).read_bytes() == PDF
    assert syncs(conn, body["id"]) == [(1, "upload", "pending")]


def test_an_admin_must_name_the_institution(
    api: TestClient, login, catalog, uploader, storage: Path
) -> None:
    login("admin", user=uploader)

    assert upload(api).status_code == 422
    response = upload(api, institution_id=catalog["iit"])

    assert response.status_code == 201
    assert response.json()["institution_id"] == str(catalog["iit"])


def test_a_manager_cannot_upload_for_another_institution(
    api: TestClient, login, catalog, uploader, storage: Path
) -> None:
    login("academic_manager", catalog["iit"], uploader)

    response = upload(api, institution_id=catalog["isb"])

    assert response.status_code == 403
    assert pdf_files(storage) == []


def test_the_program_must_belong_to_the_institution(
    api: TestClient, login, catalog, uploader, storage: Path
) -> None:
    login("academic_manager", catalog["iit"], uploader)

    response = upload(api, program_id=catalog["gestion"])

    assert response.status_code == 422
    assert pdf_files(storage) == []


@pytest.mark.parametrize(
    "content",
    [b"", b"ceci n'est pas un pdf", PDF + b"0" * 2000],
    ids=["empty", "not-a-pdf", "too-large"],
)
def test_an_unacceptable_file_is_refused(
    api: TestClient, login, catalog, uploader, storage: Path, content: bytes
) -> None:
    login("academic_manager", catalog["iit"], uploader)

    response = upload(api, content)

    assert response.status_code == 422
    assert pdf_files(storage) == []


def test_the_same_file_cannot_be_registered_twice(
    api: TestClient, login, catalog, uploader, storage: Path
) -> None:
    login("academic_manager", catalog["iit"], uploader)
    upload(api)

    response = upload(api, title="Autre titre")

    assert response.status_code == 409
    assert len(pdf_files(storage)) == 1


# Publishing a new version
def test_a_new_version_replaces_the_file_and_the_pending_synchronisation(
    api: TestClient, login, conn: Connection, catalog, uploader, storage: Path
) -> None:
    login("academic_manager", catalog["iit"], uploader)
    first = upload(api).json()

    response = new_version(api, first["id"])

    assert response.status_code == 201
    assert response.json()["content_hash"] == hashlib.sha256(PDF_V2).hexdigest()
    assert syncs(conn, first["id"]) == [(1, "upload", "failed"), (2, "update", "pending")]
    assert len(pdf_files(storage)) == 2  # the previous file is kept


def test_an_identical_file_is_not_a_new_version(
    api: TestClient, login, catalog, uploader, storage: Path
) -> None:
    login("academic_manager", catalog["iit"], uploader)
    first = upload(api).json()

    response = new_version(api, first["id"], PDF)

    assert response.status_code == 409
    assert len(pdf_files(storage)) == 1


def test_a_new_version_waits_for_a_running_indexing(
    api: TestClient, login, conn: Connection, catalog, uploader, storage: Path
) -> None:
    login("academic_manager", catalog["iit"], uploader)
    first = upload(api).json()
    conn.execute(
        text(
            "UPDATE document_syncs SET status = 'running', started_at = now() "
            "WHERE document_id = :d"
        ),
        {"d": first["id"]},
    )

    response = new_version(api, first["id"])

    assert response.status_code == 409
    assert len(pdf_files(storage)) == 1


def test_an_archived_document_receives_no_new_version(
    api: TestClient, login, catalog, uploader, storage: Path
) -> None:
    login("academic_manager", catalog["iit"], uploader)
    first = upload(api).json()
    api.delete(f"{DOCUMENTS}/{first['id']}")

    assert new_version(api, first["id"]).status_code == 409


# Modifying a document
def test_updating_a_document_changes_its_title_and_its_fragments_program(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    document = make_document(conn, catalog["iit"], uploader)
    add_current_fragment(conn, document, catalog["iit"])
    login("academic_manager", catalog["iit"])

    response = api.put(
        f"{DOCUMENTS}/{document}",
        json={"title": "  Nouveau titre  ", "program_id": str(catalog["info"])},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Nouveau titre"
    assert response.json()["program_id"] == str(catalog["info"])
    fragment_program = conn.execute(
        text("SELECT program_id FROM document_fragments WHERE document_id = :d"), {"d": document}
    ).scalar_one()
    assert fragment_program == catalog["info"]


def test_updating_refuses_a_program_of_another_institution(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    document = make_document(conn, catalog["iit"], uploader)
    login("academic_manager", catalog["iit"])

    response = api.put(
        f"{DOCUMENTS}/{document}", json={"title": "Titre", "program_id": str(catalog["gestion"])}
    )

    assert response.status_code == 422


def test_updating_refuses_a_blank_title(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    document = make_document(conn, catalog["iit"], uploader)
    login("admin")

    assert api.put(f"{DOCUMENTS}/{document}", json={"title": "   "}).status_code == 422


def test_an_archived_document_cannot_be_updated(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    document = make_document(conn, catalog["iit"], uploader, status="archived")
    login("admin")

    assert api.put(f"{DOCUMENTS}/{document}", json={"title": "Titre"}).status_code == 409


# Removing a document
def test_deleting_a_document_archives_it_and_removes_it_from_the_search(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    document = make_document(conn, catalog["iit"], uploader)
    add_current_fragment(conn, document, catalog["iit"])
    login("academic_manager", catalog["iit"])

    response = api.delete(f"{DOCUMENTS}/{document}")

    assert response.status_code == 204
    assert api.get(f"{DOCUMENTS}/{document}").json()["status"] == "archived"
    assert current_fragments(conn, document) == 0
    kept = conn.execute(
        text("SELECT count(*) FROM document_fragments WHERE document_id = :d"), {"d": document}
    ).scalar_one()
    assert kept == 1


def test_archiving_twice_is_a_conflict(
    api: TestClient, login, conn: Connection, catalog, uploader
) -> None:
    document = make_document(conn, catalog["iit"], uploader)
    login("admin")
    api.delete(f"{DOCUMENTS}/{document}")

    response = api.delete(f"{DOCUMENTS}/{document}")

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
