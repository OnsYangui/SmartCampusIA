"""SA-41 — management of the official documents of the RAG corpus.

Reserved to academic managers (their own institution) and administrators (SA-5 §3). Without
SA-28 authentication every route answers 401; a document outside the manager's institution
answers 404 so its existence is not revealed.
"""

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.api.pagination import Page, PageDep
from app.api.security import CatalogManagerDep, SettingsDep, require_catalog_manager
from app.core.db import SessionDep
from app.models import Document
from app.schemas.documents import DocumentOut, DocumentUpdate
from app.services import documents as service
from app.services.document_storage import InvalidDocumentError
from app.services.documents import DocumentFilters, StorageConfig

router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(require_catalog_manager)]
)

DocumentStatus = Annotated[str, Query(pattern="^(active|archived)$")]
PdfFile = Annotated[UploadFile, File(description="Fichier PDF officiel")]


def _storage(settings: SettingsDep) -> StorageConfig:
    return StorageConfig(
        root=settings.documents_dir,
        max_bytes=settings.document_max_bytes,
        embedding_model=settings.embedding_model,
    )


StorageDep = Annotated[StorageConfig, Depends(_storage)]


def _document(
    session: SessionDep, principal: CatalogManagerDep, document_id: uuid.UUID
) -> Document:
    document = service.get_document(session, principal, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document introuvable")
    return document


DocumentDep = Annotated[Document, Depends(_document)]


def _unprocessable(error: InvalidDocumentError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_document(
    session: SessionDep,
    principal: CatalogManagerDep,
    storage: StorageDep,
    file: PdfFile,
    title: Annotated[str, Form(min_length=1, max_length=200)],
    institution_id: Annotated[uuid.UUID | None, Form()] = None,
    program_id: Annotated[uuid.UUID | None, Form()] = None,
) -> DocumentOut:
    """Stores a PDF and queues its indexing. An administrator must give `institution_id`."""
    target = institution_id or principal.institution_id
    if target is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "institution_id est obligatoire")
    try:
        document = service.create_document(
            session,
            principal,
            storage,
            upload=file.file,
            title=title,
            institution_id=target,
            program_id=program_id,
        )
    except InvalidDocumentError as error:
        raise _unprocessable(error) from None
    return DocumentOut.model_validate(document)


@router.get("")
def list_documents(
    session: SessionDep,
    principal: CatalogManagerDep,
    page: PageDep,
    institution_id: Annotated[uuid.UUID | None, Query()] = None,
    program_id: Annotated[uuid.UUID | None, Query()] = None,
    document_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
) -> Page[DocumentOut]:
    filters = DocumentFilters(institution_id, program_id, document_status)
    items, total = service.list_documents(session, principal, filters, page.offset, page.size)
    return Page.of(DocumentOut, items, total, page)


@router.get("/{document_id}")
def get_document(document: DocumentDep) -> DocumentOut:
    return DocumentOut.model_validate(document)


@router.put("/{document_id}")
def update_document(
    session: SessionDep, principal: CatalogManagerDep, document: DocumentDep, body: DocumentUpdate
) -> DocumentOut:
    try:
        updated = service.update_document(session, principal, document, body.title, body.program_id)
    except InvalidDocumentError as error:
        raise _unprocessable(error) from None
    return DocumentOut.model_validate(updated)


@router.post("/{document_id}/versions", status_code=status.HTTP_201_CREATED)
def publish_new_version(
    session: SessionDep,
    principal: CatalogManagerDep,
    storage: StorageDep,
    document: DocumentDep,
    file: PdfFile,
) -> DocumentOut:
    """Replaces the file by a new version and queues its indexing."""
    try:
        updated = service.publish_new_version(
            session, principal, storage, document, upload=file.file
        )
    except InvalidDocumentError as error:
        raise _unprocessable(error) from None
    return DocumentOut.model_validate(updated)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_document(session: SessionDep, document: DocumentDep) -> Response:
    """Archives the document (status = archived); it is never physically deleted (SA-14)."""
    service.archive_document(session, document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
