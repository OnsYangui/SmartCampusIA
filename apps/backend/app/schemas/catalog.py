"""Public response bodies of the catalogue API (SA-20, SA-21) and shared field types."""

import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from app.models.enums import program_type
from app.services.catalog import Eligibility, EligibilityStatus, Requirements

ProgramType = StrEnum("ProgramType", {value: value for value in program_type.enums})
DataStatus = Literal["verified", "unavailable"]


def _consecutive_years(value: str) -> str:
    start, end = value.split("-")
    if int(end) != int(start) + 1:
        raise ValueError("an academic year spans two consecutive years, e.g. 2026-2027")
    return value


AcademicYear = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{4}-[0-9]{4}$"),
    AfterValidator(_consecutive_years),
]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InstitutionSummary(Schema):
    id: uuid.UUID
    code: str
    name: str


class InstitutionOut(InstitutionSummary):
    website: str | None


class ProgramRef(Schema):
    id: uuid.UUID
    code: str
    name: str


class ProgramSummary(ProgramRef):
    type: str
    field: str | None
    duration_years: int
    institution: InstitutionSummary


class PathwayOut(BaseModel):
    program: ProgramRef
    conditions: str | None


class ProgramDetail(ProgramSummary):
    description: str | None
    prerequisites: str | None
    career_outcomes: str | None
    pathways: list[PathwayOut] = []


class SpecialtyOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None


class SubjectOut(Schema):
    id: uuid.UUID
    name: str
    specialty_id: uuid.UUID | None
    study_year: int
    semester: int | None
    credits: Decimal | None


class FeeOut(Schema):
    academic_year: str
    label: str
    amount: Decimal
    currency: str
    payment_terms: str | None
    source_url: str | None
    verified_on: date | None
    valid_from: date | None
    valid_until: date | None


class FeeListOut(BaseModel):
    data_status: DataStatus
    items: list[FeeOut]


class AdmissionRequirementsOut(BaseModel):
    data_status: DataStatus
    bac_sections: list[str] | None = None
    min_bac_average: Decimal | None = None
    prerequisites: str | None = None
    source_url: str | None = None
    verified_on: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None

    @classmethod
    def from_requirements(cls, requirements: Requirements | None) -> "AdmissionRequirementsOut":
        if requirements is None:
            return cls(data_status="unavailable")
        return cls(data_status="verified", **asdict(requirements))


class EligibilityCheckOut(Schema):
    criterion: str
    met: bool


class EligibilityOut(BaseModel):
    status: EligibilityStatus
    data_status: DataStatus
    checks: list[EligibilityCheckOut]
    prerequisites: str | None

    @classmethod
    def from_assessment(
        cls, requirements: Requirements | None, eligibility: Eligibility
    ) -> "EligibilityOut":
        return cls(
            status=eligibility.status,
            data_status="unavailable" if requirements is None else "verified",
            checks=[EligibilityCheckOut.model_validate(check) for check in eligibility.checks],
            prerequisites=requirements.prerequisites if requirements else None,
        )
