"""SA-14 — Documents and synchronisation."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, uuid_pk
from app.models.enums import document_source, document_status, sync_status, sync_trigger

EMBEDDING_DIMENSION = 1024  # bge-m3; a change of model dimension needs a migration (SA-14)


class Document(Timestamped, Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("institution_id", "source_uri"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT")
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(document_source)
    source_uri: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(CHAR(64))
    # Last version indexed successfully; 0 until the first indexing succeeds.
    version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    status: Mapped[str] = mapped_column(document_status, server_default="active")
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class DocumentFragment(Timestamped, Base):
    __tablename__ = "document_fragments"
    __table_args__ = (
        UniqueConstraint("document_id", "document_version", "position"),
        # Search only sees the current version (SA-14 §4).
        Index(
            "ix_document_fragments_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("is_current"),
        ),
        Index("ix_document_fragments_content_tsv", "content_tsv", postgresql_using="gin"),
        Index("ix_document_fragments_institution_id_program_id", "institution_id", "program_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    # Copies of the document's columns, so search filters without a join (no foreign key).
    institution_id: Mapped[uuid.UUID]
    program_id: Mapped[uuid.UUID | None]
    document_version: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))
    # 'simple': the corpus mixes French, Arabic and Arabizi.
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple'::regconfig, content)", persisted=True)
    )
    is_current: Mapped[bool] = mapped_column(server_default=text("false"))


class DocumentSync(Timestamped, Base):
    __tablename__ = "document_syncs"
    __table_args__ = (
        CheckConstraint(
            "status <> 'succeeded' OR fragments_count IS NOT NULL", name="fragments_count"
        ),
        CheckConstraint("status <> 'failed' OR error_message IS NOT NULL", name="error_message"),
        # One synchronisation in progress per document.
        Index(
            "uq_document_syncs_one_in_progress",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), index=True
    )
    document_version: Mapped[int] = mapped_column(Integer)
    trigger_type: Mapped[str] = mapped_column(sync_trigger)
    status: Mapped[str] = mapped_column(sync_status, server_default="pending")
    embedding_model: Mapped[str] = mapped_column(String(100))
    fragments_count: Mapped[int | None] = mapped_column(Integer)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
