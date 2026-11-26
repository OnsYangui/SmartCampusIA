"""SA-42 — storage of the PDF files: hash, naming, limits and cleanup."""

import hashlib
import io
import uuid

import pytest

from app.services.document_storage import InvalidDocumentError, remove_file, save_pdf

PDF = b"%PDF-1.4\n% contenu de test\n"


def test_a_pdf_is_stored_with_its_hash_and_size(tmp_path) -> None:
    institution = uuid.uuid4()

    stored = save_pdf(io.BytesIO(PDF), tmp_path, institution, 1024)

    assert stored.size == len(PDF)
    assert stored.content_hash == hashlib.sha256(PDF).hexdigest()
    assert stored.source_uri.startswith(f"{institution}/")
    assert stored.source_uri.endswith(".pdf")
    assert (tmp_path / stored.source_uri).read_bytes() == PDF


def test_two_uploads_never_share_a_file(tmp_path) -> None:
    institution = uuid.uuid4()

    first = save_pdf(io.BytesIO(PDF), tmp_path, institution, 1024)
    second = save_pdf(io.BytesIO(PDF), tmp_path, institution, 1024)

    assert first.source_uri != second.source_uri
    assert len(list(tmp_path.rglob("*.pdf"))) == 2


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "vide"),
        (b"ceci n'est pas un pdf", "PDF valide"),
        (PDF + b"0" * 2000, "taille maximale"),
    ],
    ids=["empty", "not-a-pdf", "too-large"],
)
def test_an_unacceptable_file_is_refused_and_leaves_nothing_on_disk(
    tmp_path, content: bytes, message: str
) -> None:
    with pytest.raises(InvalidDocumentError, match=message):
        save_pdf(io.BytesIO(content), tmp_path, uuid.uuid4(), 1024)

    assert list(tmp_path.rglob("*.pdf")) == []


def test_removing_a_file_twice_is_harmless(tmp_path) -> None:
    stored = save_pdf(io.BytesIO(PDF), tmp_path, uuid.uuid4(), 1024)

    remove_file(tmp_path, stored.source_uri)
    remove_file(tmp_path, stored.source_uri)

    assert not (tmp_path / stored.source_uri).exists()
