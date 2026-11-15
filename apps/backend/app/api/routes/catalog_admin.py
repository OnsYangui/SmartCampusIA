"""SA-20 and SA-21 — catalogue management, reserved to academic managers and administrators.

Every route requires `require_catalog_manager`: without SA-28 authentication they all answer 401.
Out-of-scope resources answer 404, so their existence is not revealed (SA-5).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import StringConstraints

from app.api.pagination import Page, PageDep
from app.api.security import CatalogManagerDep, require_catalog_manager
from app.core.db import SessionDep
from app.models import Program, ProgramFee, ProgramSpecialty, Subject
from app.schemas.catalog import ProgramType
from app.schemas.catalog_admin import (
    FeeIn,
    FeeManaged,
    ProgramIn,
    ProgramManaged,
    RequirementsIn,
    RequirementsManaged,
    SpecialtyIn,
    SpecialtyManaged,
    SubjectIn,
    SubjectManaged,
)
from app.services import catalog_admin as admin
from app.services.catalog import ProgramFilters, SubjectFilters

router = APIRouter(
    prefix="/manage", tags=["catalog management"], dependencies=[Depends(require_catalog_manager)]
)

SearchTerm = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


def _found[T](resource: T | None, message: str) -> T:
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, message)
    return resource


def _program(session: SessionDep, principal: CatalogManagerDep, program_id: uuid.UUID) -> Program:
    return _found(admin.get_program(session, principal, program_id), "Formation introuvable")


ProgramDep = Annotated[Program, Depends(_program)]


# Programs
@router.get("/programs")
def list_programs(
    session: SessionDep,
    principal: CatalogManagerDep,
    page: PageDep,
    institution: Annotated[str | None, Query(max_length=10)] = None,
    program_type: Annotated[ProgramType | None, Query(alias="type")] = None,
    q: Annotated[SearchTerm | None, Query()] = None,
) -> Page[ProgramManaged]:
    """All programs in the manager's scope, including inactive ones."""
    filters = ProgramFilters(institution=institution, type=program_type, q=q)
    items, total = admin.list_programs(session, principal, filters, page.offset, page.size)
    return Page.of(ProgramManaged, items, total, page)


@router.post("/programs", status_code=status.HTTP_201_CREATED)
def create_program(
    session: SessionDep, principal: CatalogManagerDep, body: ProgramIn
) -> ProgramManaged:
    return ProgramManaged.model_validate(
        admin.create_program(session, principal, body.model_dump())
    )


@router.get("/programs/{program_id}")
def get_program(program: ProgramDep) -> ProgramManaged:
    return ProgramManaged.model_validate(program)


@router.put("/programs/{program_id}")
def update_program(
    session: SessionDep, principal: CatalogManagerDep, program: ProgramDep, body: ProgramIn
) -> ProgramManaged:
    return ProgramManaged.model_validate(
        admin.update_program(session, principal, program, body.model_dump())
    )


@router.delete("/programs/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_program(session: SessionDep, program: ProgramDep) -> Response:
    """Closes the program (is_active = false); it is never physically deleted (SA-12)."""
    admin.deactivate_program(session, program)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Specialties
@router.get("/programs/{program_id}/specialties")
def list_specialties(session: SessionDep, program: ProgramDep) -> list[SpecialtyManaged]:
    return [SpecialtyManaged.model_validate(s) for s in admin.list_specialties(session, program)]


@router.post("/programs/{program_id}/specialties", status_code=status.HTTP_201_CREATED)
def create_specialty(
    session: SessionDep, program: ProgramDep, body: SpecialtyIn
) -> SpecialtyManaged:
    return SpecialtyManaged.model_validate(
        admin.create_specialty(session, program, body.model_dump())
    )


def _specialty(
    session: SessionDep, principal: CatalogManagerDep, specialty_id: uuid.UUID
) -> ProgramSpecialty:
    return _found(admin.get_specialty(session, principal, specialty_id), "Spécialité introuvable")


SpecialtyDep = Annotated[ProgramSpecialty, Depends(_specialty)]


@router.get("/specialties/{specialty_id}")
def get_specialty(specialty: SpecialtyDep) -> SpecialtyManaged:
    return SpecialtyManaged.model_validate(specialty)


@router.put("/specialties/{specialty_id}")
def update_specialty(
    session: SessionDep, specialty: SpecialtyDep, body: SpecialtyIn
) -> SpecialtyManaged:
    return SpecialtyManaged.model_validate(
        admin.update_specialty(session, specialty, body.model_dump())
    )


@router.delete("/specialties/{specialty_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_specialty(session: SessionDep, specialty: SpecialtyDep) -> Response:
    admin.deactivate_specialty(session, specialty)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Subjects
@router.get("/programs/{program_id}/subjects")
def list_subjects(
    session: SessionDep,
    program: ProgramDep,
    page: PageDep,
    study_year: Annotated[int | None, Query(ge=1, le=6)] = None,
    specialty_id: uuid.UUID | None = None,
    q: Annotated[SearchTerm | None, Query()] = None,
) -> Page[SubjectManaged]:
    filters = SubjectFilters(study_year=study_year, specialty_id=specialty_id, q=q)
    items, total = admin.list_subjects(session, program, filters, page.offset, page.size)
    return Page.of(SubjectManaged, items, total, page)


@router.post("/programs/{program_id}/subjects", status_code=status.HTTP_201_CREATED)
def create_subject(session: SessionDep, program: ProgramDep, body: SubjectIn) -> SubjectManaged:
    return SubjectManaged.model_validate(admin.create_subject(session, program, body.model_dump()))


def _subject(session: SessionDep, principal: CatalogManagerDep, subject_id: uuid.UUID) -> Subject:
    return _found(admin.get_subject(session, principal, subject_id), "Matière introuvable")


SubjectDep = Annotated[Subject, Depends(_subject)]


@router.get("/subjects/{subject_id}")
def get_subject(subject: SubjectDep) -> SubjectManaged:
    return SubjectManaged.model_validate(subject)


@router.put("/subjects/{subject_id}")
def update_subject(session: SessionDep, subject: SubjectDep, body: SubjectIn) -> SubjectManaged:
    return SubjectManaged.model_validate(admin.update_subject(session, subject, body.model_dump()))


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_subject(session: SessionDep, subject: SubjectDep) -> Response:
    admin.deactivate_subject(session, subject)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Fees
@router.get("/programs/{program_id}/fees")
def list_fees(session: SessionDep, program: ProgramDep) -> list[FeeManaged]:
    """Every fee of the program, whatever its status."""
    return [FeeManaged.model_validate(fee) for fee in admin.list_fees(session, program)]


@router.post("/programs/{program_id}/fees", status_code=status.HTTP_201_CREATED)
def create_fee(session: SessionDep, program: ProgramDep, body: FeeIn) -> FeeManaged:
    """Creates a draft; it is public only once published."""
    return FeeManaged.model_validate(admin.create_fee(session, program, body.model_dump()))


def _fee(session: SessionDep, principal: CatalogManagerDep, fee_id: uuid.UUID) -> ProgramFee:
    return _found(admin.get_fee(session, principal, fee_id), "Frais introuvable")


FeeDep = Annotated[ProgramFee, Depends(_fee)]


@router.get("/fees/{fee_id}")
def get_fee(fee: FeeDep) -> FeeManaged:
    return FeeManaged.model_validate(fee)


@router.put("/fees/{fee_id}")
def update_fee(session: SessionDep, fee: FeeDep, body: FeeIn) -> FeeManaged:
    """Edits a draft; a published fee is changed through a revision."""
    return FeeManaged.model_validate(admin.update_fee(session, fee, body.model_dump()))


@router.post("/fees/{fee_id}/revisions", status_code=status.HTTP_201_CREATED)
def revise_fee(session: SessionDep, fee: FeeDep, body: FeeIn) -> FeeManaged:
    """Drafts the next version; the published fee stays public until the revision is published."""
    return FeeManaged.model_validate(admin.revise_fee(session, fee, body.model_dump()))


@router.post("/fees/{fee_id}/publish")
def publish_fee(session: SessionDep, fee: FeeDep) -> FeeManaged:
    """Requires an official source and a start of validity; demonstration data is refused."""
    return FeeManaged.model_validate(admin.publish_fee(session, fee))


@router.post("/fees/{fee_id}/archive")
def archive_fee(session: SessionDep, fee: FeeDep) -> FeeManaged:
    return FeeManaged.model_validate(admin.archive_fee(session, fee))


# Admission conditions
def _requirements(program: Program) -> RequirementsManaged:
    return RequirementsManaged(**admin.requirements_of(program))


@router.get("/programs/{program_id}/admission-requirements")
def get_requirements(program: ProgramDep) -> RequirementsManaged:
    return _requirements(program)


@router.put("/programs/{program_id}/admission-requirements")
def save_requirements(
    session: SessionDep, program: ProgramDep, body: RequirementsIn
) -> RequirementsManaged:
    """Replaces the conditions and returns them to draft until they are published again."""
    return _requirements(admin.save_requirements(session, program, body.model_dump()))


@router.post("/programs/{program_id}/admission-requirements/publish")
def publish_requirements(session: SessionDep, program: ProgramDep) -> RequirementsManaged:
    return _requirements(admin.publish_requirements(session, program))


@router.post("/programs/{program_id}/admission-requirements/archive")
def archive_requirements(session: SessionDep, program: ProgramDep) -> RequirementsManaged:
    return _requirements(admin.archive_requirements(session, program))
