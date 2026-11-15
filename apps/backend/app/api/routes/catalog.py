"""SA-20 and SA-21 — public, read-only catalogue (SA-5: GET /programs for every role).

Fees and admission conditions are only returned once published and while valid.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import StringConstraints

from app.api.pagination import Page, PageDep
from app.core.db import SessionDep
from app.models import Program
from app.schemas.catalog import (
    AcademicYear,
    AdmissionRequirementsOut,
    EligibilityOut,
    FeeListOut,
    FeeOut,
    InstitutionOut,
    PathwayOut,
    ProgramDetail,
    ProgramRef,
    ProgramSummary,
    ProgramType,
    SpecialtyOut,
    SubjectOut,
)
from app.services import catalog

router = APIRouter(tags=["catalog"])

SearchTerm = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
BacSection = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
BacAverage = Annotated[Decimal, Query(ge=0, le=20, max_digits=4, decimal_places=2)]
StudyYear = Annotated[int | None, Query(ge=1, le=6)]

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Ressource inexistante ou inactive"}}


def _active_program(session: SessionDep, program_id: uuid.UUID) -> Program:
    program = catalog.get_active_program(session, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Formation introuvable")
    return program


@router.get("/institutions")
def list_institutions(session: SessionDep, page: PageDep) -> Page[InstitutionOut]:
    items, total = catalog.list_institutions(session, page.offset, page.size)
    return Page.of(InstitutionOut, items, total, page)


@router.get("/institutions/{institution_id}", responses=NOT_FOUND)
def get_institution(session: SessionDep, institution_id: uuid.UUID) -> InstitutionOut:
    institution = catalog.get_institution(session, institution_id)
    if institution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Établissement introuvable")
    return InstitutionOut.model_validate(institution)


@router.get("/programs")
def list_programs(
    session: SessionDep,
    page: PageDep,
    institution: Annotated[str | None, Query(max_length=10)] = None,
    program_type: Annotated[ProgramType | None, Query(alias="type")] = None,
    q: Annotated[SearchTerm | None, Query()] = None,
) -> Page[ProgramSummary]:
    """Active programs, filtered by institution code, type or a search term."""
    filters = catalog.ProgramFilters(institution=institution, type=program_type, q=q)
    items, total = catalog.list_programs(session, filters, page.offset, page.size)
    return Page.of(ProgramSummary, items, total, page)


@router.get("/programs/{program_id}", responses=NOT_FOUND)
def get_program(session: SessionDep, program_id: uuid.UUID) -> ProgramDetail:
    program = _active_program(session, program_id)
    pathways = [
        PathwayOut(program=ProgramRef.model_validate(target), conditions=conditions)
        for target, conditions in catalog.list_pathways(session, program_id)
    ]
    return ProgramDetail.model_validate(program).model_copy(update={"pathways": pathways})


@router.get("/programs/{program_id}/specialties", responses=NOT_FOUND)
def list_specialties(session: SessionDep, program_id: uuid.UUID) -> list[SpecialtyOut]:
    _active_program(session, program_id)
    return [SpecialtyOut.model_validate(s) for s in catalog.list_specialties(session, program_id)]


@router.get("/programs/{program_id}/subjects", responses=NOT_FOUND)
def list_subjects(
    session: SessionDep,
    program_id: uuid.UUID,
    page: PageDep,
    study_year: StudyYear = None,
    specialty_id: uuid.UUID | None = None,
    q: Annotated[SearchTerm | None, Query()] = None,
) -> Page[SubjectOut]:
    _active_program(session, program_id)
    filters = catalog.SubjectFilters(study_year=study_year, specialty_id=specialty_id, q=q)
    items, total = catalog.list_subjects(session, program_id, filters, page.offset, page.size)
    return Page.of(SubjectOut, items, total, page)


@router.get("/programs/{program_id}/fees", responses=NOT_FOUND)
def list_program_fees(
    session: SessionDep,
    program_id: uuid.UUID,
    academic_year: Annotated[AcademicYear | None, Query()] = None,
) -> FeeListOut:
    """Published fees valid today, latest academic year first; `unavailable` when there is none."""
    _active_program(session, program_id)
    fees = catalog.list_published_fees(session, program_id, date.today(), academic_year)
    return FeeListOut(
        data_status="verified" if fees else "unavailable",
        items=[FeeOut.model_validate(fee) for fee in fees],
    )


@router.get("/programs/{program_id}/admission-requirements", responses=NOT_FOUND)
def get_admission_requirements(
    session: SessionDep, program_id: uuid.UUID
) -> AdmissionRequirementsOut:
    """Published conditions valid today; `unavailable` otherwise."""
    program = _active_program(session, program_id)
    return AdmissionRequirementsOut.from_requirements(
        catalog.published_requirements(program, date.today())
    )


@router.get("/programs/{program_id}/eligibility", responses=NOT_FOUND)
def check_eligibility(
    session: SessionDep,
    program_id: uuid.UUID,
    bac_section: Annotated[BacSection, Query()],
    bac_average: BacAverage,
) -> EligibilityOut:
    """Compares a baccalaureate with the published conditions; it is not an admission decision.

    `undetermined` whenever no published condition applies or none can be measured.
    """
    program = _active_program(session, program_id)
    requirements = catalog.published_requirements(program, date.today())
    assessment = catalog.assess_eligibility(requirements, bac_section, bac_average)
    return EligibilityOut.from_assessment(requirements, assessment)
