"""Request and response bodies of catalogue management (SA-20, SA-21)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.schemas.catalog import AcademicYear, ProgramType, Schema

Code = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]*$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OfficialUrl = Annotated[str, StringConstraints(pattern=r"^https://", max_length=500)]
PublicationStatus = Literal["draft", "published", "archived"]


class Provenance(BaseModel):
    """Official source of fees or conditions; demonstration data never cites one."""

    source_url: OfficialUrl | None = None
    verified_on: date | None = None
    is_demo: bool = False
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.source_url is None) != (self.verified_on is None):
            raise ValueError("source_url and verified_on go together")
        if self.is_demo and self.source_url:
            raise ValueError("demonstration data cannot cite an official source")
        if self.valid_until and (not self.valid_from or self.valid_until < self.valid_from):
            raise ValueError("valid_until must follow valid_from")
        return self


class ProgramIn(BaseModel):
    institution_id: uuid.UUID
    code: Annotated[Code, Field(max_length=30)]
    name: Annotated[Name, Field(max_length=200)]
    type: ProgramType
    field: Annotated[str, Field(max_length=100)] | None = None
    duration_years: Annotated[int, Field(ge=1, le=5)]
    description: str | None = None
    career_outcomes: str | None = None
    is_active: bool = True


class ProgramManaged(Schema):
    id: uuid.UUID
    institution_id: uuid.UUID
    code: str
    name: str
    type: str
    field: str | None
    duration_years: int
    description: str | None
    career_outcomes: str | None
    is_active: bool


class SpecialtyIn(BaseModel):
    code: Annotated[Code, Field(max_length=20)]
    name: Annotated[Name, Field(max_length=150)]
    description: str | None = None
    is_active: bool = True


class SpecialtyManaged(Schema):
    id: uuid.UUID
    program_id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool


class SubjectIn(BaseModel):
    name: Annotated[Name, Field(max_length=200)]
    study_year: Annotated[int, Field(ge=1, le=6)]
    semester: Annotated[int, Field(ge=1, le=12)] | None = None
    credits: Annotated[Decimal, Field(gt=0, max_digits=4, decimal_places=1)] | None = None
    specialty_id: uuid.UUID | None = None
    is_active: bool = True


class SubjectManaged(Schema):
    id: uuid.UUID
    program_id: uuid.UUID
    specialty_id: uuid.UUID | None
    name: str
    study_year: int
    semester: int | None
    credits: Decimal | None
    is_active: bool


class FeeIn(Provenance):
    academic_year: AcademicYear
    label: Annotated[Name, Field(max_length=150)]
    amount: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] = "TND"
    payment_terms: Annotated[str, Field(max_length=1000)] | None = None

    @model_validator(mode="after")
    def _official_or_demo(self) -> Self:
        if not self.is_demo and self.source_url is None:
            raise ValueError("a fee cites an official source unless it is demonstration data")
        return self


class FeeManaged(Schema):
    id: uuid.UUID
    program_id: uuid.UUID
    academic_year: str
    label: str
    amount: Decimal
    currency: str
    payment_terms: str | None
    is_demo: bool
    source_url: str | None
    verified_on: date | None
    valid_from: date | None
    valid_until: date | None
    status: PublicationStatus
    replaces_id: uuid.UUID | None


class RequirementsIn(Provenance):
    bac_sections: list[Annotated[Name, Field(max_length=100)]] | None = None
    min_bac_average: (
        Annotated[Decimal, Field(ge=0, le=20, max_digits=4, decimal_places=2)] | None
    ) = None
    prerequisites: str | None = None


class RequirementsManaged(BaseModel):
    bac_sections: list[str] | None
    min_bac_average: Decimal | None
    prerequisites: str | None
    source_url: str | None
    verified_on: date | None
    is_demo: bool
    valid_from: date | None
    valid_until: date | None
    status: PublicationStatus
