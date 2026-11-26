"""Request and response bodies of document management (SA-41)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.schemas.catalog import Schema

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class DocumentUpdate(BaseModel):
    title: Title
    program_id: uuid.UUID | None = None  # empty: the document concerns the whole institution


class DocumentOut(Schema):
    id: uuid.UUID
    institution_id: uuid.UUID
    program_id: uuid.UUID | None
    title: str
    source_type: str
    content_hash: str
    version: int
    status: str
    uploaded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
