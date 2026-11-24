"""Official documents of the RAG corpus (SA-41, SA-42).

The file is stored on disk (document_storage), its information in the `documents` table.
An upload or a new version queues a synchronisation (SA-14 §3) for the indexing pipeline.
A document is never physically deleted: removing it archives it and takes its fragments out of
the search, because older answers may still cite them (SA-14 §4).
"""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError
from app.core.security import ADMIN, Principal
from app.models import Document, DocumentFragment, DocumentSync, Institution, Program
from app.services.catalog import paginate
from app.services.document_storage import InvalidDocumentError, remove_file, save_pdf


@dataclass(frozen=True)
class StorageConfig:
    root: Path
    max_bytes: int
    embedding_model: str


@dataclass(frozen=True)
class DocumentFilters:
    institution_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    status: str | None = None


# Reading
def _documents_query(principal: Principal, filters: DocumentFilters) -> Select[tuple[Document]]:
    query = select(Document).order_by(Document.created_at.desc(), Document.id)
    if principal.role != ADMIN:
        query = query.where(Document.institution_id == principal.institution_id)
    elif filters.institution_id is not None:
        query = query.where(Document.institution_id == filters.institution_id)
    if filters.program_id is not None:
        query = query.where(Document.program_id == filters.program_id)
    if filters.status is not None:
        query = query.where(Document.status == filters.status)
    return query


def list_documents(
    session: Session, principal: Principal, filters: DocumentFilters, offset: int, limit: int
) -> tuple[list[Document], int]:
    return paginate(session, _documents_query(principal, filters), offset, limit)


def get_document(session: Session, principal: Principal, document_id: uuid.UUID) -> Document | None:
    """None when absent or outside the manager's institution (404, RM-09)."""
    document = session.get(Document, document_id)
    return document if document and principal.can_manage(document.institution_id) else None


# Rules shared by the writes
def _check_scope(
    session: Session, principal: Principal, institution_id: uuid.UUID, program_id: uuid.UUID | None
) -> None:
    if not principal.can_manage(institution_id):
        raise ForbiddenError("Établissement hors de votre périmètre")
    if session.get(Institution, institution_id) is None:
        raise InvalidDocumentError("Établissement inconnu")
    if program_id is not None:
        program = session.get(Program, program_id)
        if program is None or program.institution_id != institution_id:
            raise InvalidDocumentError("La formation n'appartient pas à cet établissement")


def _refuse_duplicate(
    session: Session, institution_id: uuid.UUID, content_hash: str, document_id: uuid.UUID | None
) -> None:
    existing = session.scalar(
        select(Document.id).where(
            Document.institution_id == institution_id,
            Document.content_hash == content_hash,
            Document.status == "active",
        )
    )
    if existing is None:
        return
    if existing == document_id:
        raise ConflictError("Ce fichier est identique à la version actuelle")
    raise ConflictError("Ce document est déjà enregistré pour cet établissement")


def _queue_sync(
    session: Session,
    document: Document,
    *,
    version: int,
    trigger: str,
    requested_by: uuid.UUID,
    embedding_model: str,
) -> None:
    session.add(
        DocumentSync(
            document_id=document.id,
            document_version=version,
            trigger_type=trigger,
            status="pending",
            embedding_model=embedding_model,
            requested_by=requested_by,
        )
    )


# Writing
def create_document(
    session: Session,
    principal: Principal,
    storage: StorageConfig,
    *,
    upload: BinaryIO,
    title: str,
    institution_id: uuid.UUID,
    program_id: uuid.UUID | None,
) -> Document:
    """Stores the file, records the document and queues its first synchronisation."""
    title = title.strip()
    if not title:
        raise InvalidDocumentError("Le titre est obligatoire")
    _check_scope(session, principal, institution_id, program_id)

    stored = save_pdf(upload, storage.root, institution_id, storage.max_bytes)
    try:
        _refuse_duplicate(session, institution_id, stored.content_hash, None)
        document = Document(
            institution_id=institution_id,
            program_id=program_id,
            title=title,
            source_type="pdf",
            source_uri=stored.source_uri,
            content_hash=stored.content_hash,
            uploaded_by=principal.user_id,
        )
        session.add(document)
        session.flush()
        _queue_sync(
            session,
            document,
            version=1,
            trigger="upload",
            requested_by=principal.user_id,
            embedding_model=storage.embedding_model,
        )
        session.commit()
    except BaseException:
        session.rollback()
        remove_file(storage.root, stored.source_uri)
        raise
    session.refresh(document)
    return document


def update_document(
    session: Session,
    principal: Principal,
    document: Document,
    title: str,
    program_id: uuid.UUID | None,
) -> Document:
    """Changes the title and the program; the fragments follow so the search filters stay right."""
    if document.status == "archived":
        raise ConflictError("Un document archivé ne peut plus être modifié")
    _check_scope(session, principal, document.institution_id, program_id)
    document.title = title
    document.program_id = program_id
    session.execute(
        update(DocumentFragment)
        .where(DocumentFragment.document_id == document.id)
        .values(program_id=program_id)
    )
    session.commit()
    session.refresh(document)
    return document


def publish_new_version(
    session: Session,
    principal: Principal,
    storage: StorageConfig,
    document: Document,
    *,
    upload: BinaryIO,
) -> Document:
    """Replaces the file and queues the indexing of the next version.

    The previous file stays on disk. A synchronisation not started yet is replaced by the new
    one; one already running must finish first (one synchronisation at a time, SA-14).
    """
    if document.status == "archived":
        raise ConflictError("Un document archivé ne peut pas recevoir de nouvelle version")
    running = session.scalar(
        select(DocumentSync.id).where(
            DocumentSync.document_id == document.id, DocumentSync.status == "running"
        )
    )
    if running is not None:
        raise ConflictError("Une indexation est en cours pour ce document, réessayez plus tard")

    stored = save_pdf(upload, storage.root, document.institution_id, storage.max_bytes)
    try:
        _refuse_duplicate(session, document.institution_id, stored.content_hash, document.id)
        last_requested = session.scalar(
            select(func.max(DocumentSync.document_version)).where(
                DocumentSync.document_id == document.id
            )
        )
        session.execute(
            update(DocumentSync)
            .where(DocumentSync.document_id == document.id, DocumentSync.status == "pending")
            .values(
                status="failed",
                error_message="Remplacée par une version plus récente",
                finished_at=func.now(),
            )
        )
        document.source_uri = stored.source_uri
        document.content_hash = stored.content_hash
        _queue_sync(
            session,
            document,
            version=max(document.version, last_requested or 0) + 1,
            trigger="update",
            requested_by=principal.user_id,
            embedding_model=storage.embedding_model,
        )
        session.commit()
    except BaseException:
        session.rollback()
        remove_file(storage.root, stored.source_uri)
        raise
    session.refresh(document)
    return document


def archive_document(session: Session, document: Document) -> Document:
    """Archives the document and removes its fragments from the search; nothing is deleted."""
    if document.status == "archived":
        raise ConflictError("Document déjà archivé")
    document.status = "archived"
    session.execute(
        update(DocumentFragment)
        .where(DocumentFragment.document_id == document.id)
        .values(is_current=False)
    )
    session.commit()
    session.refresh(document)
    return document
