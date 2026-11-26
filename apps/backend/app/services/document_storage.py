"""Storage of the PDF files of the official documents (SA-42).

Files live in one folder per institution; the database keeps only the relative path
(`documents.source_uri`) and the SHA-256 of the content (SA-14). A file is never overwritten:
every upload gets its own name, so a previous version stays on disk for the answers citing it.
"""

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

PDF_SIGNATURE = b"%PDF-"
CHUNK_SIZE = 1024 * 1024


class InvalidDocumentError(ValueError):
    """The file or its information is not acceptable (422)."""


@dataclass(frozen=True)
class StoredFile:
    source_uri: str  # path relative to the documents folder, e.g. "<institution id>/<uuid>.pdf"
    content_hash: str  # SHA-256 of the content, to detect a change later (SA-14)
    size: int


def save_pdf(upload: BinaryIO, root: Path, institution_id: uuid.UUID, max_bytes: int) -> StoredFile:
    """Streams the upload to disk while hashing it; refuses empty, oversized and non-PDF files."""
    folder = root / str(institution_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4()}.pdf"
    path = folder / name
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("wb") as target:
            while chunk := upload.read(CHUNK_SIZE):
                if size == 0 and not chunk.startswith(PDF_SIGNATURE):
                    raise InvalidDocumentError("Le fichier n'est pas un PDF valide")
                size += len(chunk)
                if size > max_bytes:
                    limit = max_bytes / (1024 * 1024)
                    raise InvalidDocumentError(
                        f"Le fichier dépasse la taille maximale de {limit:g} Mo"
                    )
                digest.update(chunk)
                target.write(chunk)
        if size == 0:
            raise InvalidDocumentError("Le fichier est vide")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return StoredFile(f"{institution_id}/{name}", digest.hexdigest(), size)


def remove_file(root: Path, source_uri: str) -> None:
    (root / source_uri).unlink(missing_ok=True)
