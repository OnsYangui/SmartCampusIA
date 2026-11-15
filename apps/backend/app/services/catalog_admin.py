"""Catalogue management for academic managers and administrators (SA-20, SA-21).

Nothing is physically deleted: programs, specialties and subjects are deactivated, fees and
admission conditions archived (the backend role has no DELETE privilege, migration 0003).
Any change to fees or conditions returns them to draft, so only reviewed data is published.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError
from app.core.security import Principal
from app.models import Program, ProgramFee, ProgramSpecialty, Subject
from app.services.catalog import (
    ProgramFilters,
    SubjectFilters,
    paginate,
    programs_query,
    specialties_query,
    subjects_query,
)

REQUIREMENT_COLUMNS = {
    "bac_sections": "admission_bac_sections",
    "min_bac_average": "min_bac_average",
    "prerequisites": "prerequisites",
    "source_url": "admission_source_url",
    "verified_on": "admission_verified_on",
    "is_demo": "admission_is_demo",
    "valid_from": "admission_valid_from",
    "valid_until": "admission_valid_until",
    "status": "admission_status",
}


def _save[T](session: Session, entity: T) -> T:
    session.add(entity)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise
    session.refresh(entity)
    return entity


def _assign[T](entity: T, values: dict[str, Any]) -> T:
    for name, value in values.items():
        setattr(entity, name, value)
    return entity


def _published(
    status: str, *, official: bool, valid_from: date | None, valid_until: date | None
) -> str:
    if status != "draft":
        raise ConflictError("Seul un brouillon peut être publié")
    if not official or valid_from is None:
        raise ConflictError(
            "Publication réservée aux données officielles vérifiées, avec un début de validité"
        )
    if valid_until is not None and valid_until < date.today():
        raise ConflictError("La période de validité est déjà terminée")
    return "published"


def _archived(status: str) -> str:
    if status == "archived":
        raise ConflictError("Déjà archivé")
    return "archived"


# Programs
def list_programs(
    session: Session, principal: Principal, filters: ProgramFilters, offset: int, limit: int
) -> tuple[list[Program], int]:
    scope = None if principal.role == "admin" else principal.institution_id
    query = programs_query(filters, active_only=False, institution_id=scope)
    return paginate(session, query, offset, limit)


def get_program(session: Session, principal: Principal, program_id: uuid.UUID) -> Program | None:
    program = session.get(Program, program_id)
    return program if program and principal.can_manage(program.institution_id) else None


def _check_institution(principal: Principal, institution_id: uuid.UUID) -> None:
    if not principal.can_manage(institution_id):
        raise ForbiddenError("Établissement hors de votre périmètre")


def create_program(session: Session, principal: Principal, values: dict[str, Any]) -> Program:
    _check_institution(principal, values["institution_id"])
    return _save(session, Program(**values))


def update_program(
    session: Session, principal: Principal, program: Program, values: dict[str, Any]
) -> Program:
    _check_institution(principal, values["institution_id"])
    return _save(session, _assign(program, values))


def deactivate_program(session: Session, program: Program) -> None:
    _save(session, _assign(program, {"is_active": False}))


# Specialties
def list_specialties(session: Session, program: Program) -> list[ProgramSpecialty]:
    return list(session.scalars(specialties_query(program.id, active_only=False)))


def get_specialty(
    session: Session, principal: Principal, specialty_id: uuid.UUID
) -> ProgramSpecialty | None:
    specialty = session.get(ProgramSpecialty, specialty_id)
    if specialty and get_program(session, principal, specialty.program_id):
        return specialty
    return None


def create_specialty(
    session: Session, program: Program, values: dict[str, Any]
) -> ProgramSpecialty:
    return _save(session, ProgramSpecialty(program_id=program.id, **values))


def update_specialty(
    session: Session, specialty: ProgramSpecialty, values: dict[str, Any]
) -> ProgramSpecialty:
    return _save(session, _assign(specialty, values))


def deactivate_specialty(session: Session, specialty: ProgramSpecialty) -> None:
    _save(session, _assign(specialty, {"is_active": False}))


# Subjects
def list_subjects(
    session: Session, program: Program, filters: SubjectFilters, offset: int, limit: int
) -> tuple[list[Subject], int]:
    return paginate(session, subjects_query(program.id, filters, active_only=False), offset, limit)


def get_subject(session: Session, principal: Principal, subject_id: uuid.UUID) -> Subject | None:
    subject = session.get(Subject, subject_id)
    return subject if subject and get_program(session, principal, subject.program_id) else None


def create_subject(session: Session, program: Program, values: dict[str, Any]) -> Subject:
    return _save(session, Subject(program_id=program.id, **values))


def update_subject(session: Session, subject: Subject, values: dict[str, Any]) -> Subject:
    return _save(session, _assign(subject, values))


def deactivate_subject(session: Session, subject: Subject) -> None:
    _save(session, _assign(subject, {"is_active": False}))


# Fees
def list_fees(session: Session, program: Program) -> list[ProgramFee]:
    query = (
        select(ProgramFee)
        .where(ProgramFee.program_id == program.id)
        .order_by(ProgramFee.academic_year.desc(), ProgramFee.label)
    )
    return list(session.scalars(query))


def get_fee(session: Session, principal: Principal, fee_id: uuid.UUID) -> ProgramFee | None:
    fee = session.get(ProgramFee, fee_id)
    return fee if fee and get_program(session, principal, fee.program_id) else None


def create_fee(session: Session, program: Program, values: dict[str, Any]) -> ProgramFee:
    return _save(session, ProgramFee(program_id=program.id, status="draft", **values))


def update_fee(session: Session, fee: ProgramFee, values: dict[str, Any]) -> ProgramFee:
    if fee.status != "draft":
        raise ConflictError("Seul un brouillon est modifiable ; révisez le frais publié")
    return _save(session, _assign(fee, values))


def revise_fee(session: Session, fee: ProgramFee, values: dict[str, Any]) -> ProgramFee:
    """Drafts the next version; the published one stays public until the revision replaces it."""
    if fee.status != "published":
        raise ConflictError("Seul un frais publié peut être révisé")
    revision = ProgramFee(program_id=fee.program_id, status="draft", replaces_id=fee.id, **values)
    return _save(session, revision)


def _overlaps_published_fee(session: Session, fee: ProgramFee) -> bool:
    period = func.daterange(ProgramFee.valid_from, ProgramFee.valid_until, "[]")
    query = select(ProgramFee.id).where(
        ProgramFee.status == "published",
        ProgramFee.id.not_in([fee.id, fee.replaces_id or fee.id]),
        ProgramFee.program_id == fee.program_id,
        ProgramFee.academic_year == fee.academic_year,
        ProgramFee.label == fee.label,
        period.op("&&")(func.daterange(fee.valid_from, fee.valid_until, "[]")),
    )
    return session.scalar(query.limit(1)) is not None


def _supersede(replaced: ProgramFee, starts: date) -> None:
    """Ends the replaced version the day before its revision starts, or archives it."""
    last_day = starts - timedelta(days=1)
    if last_day < max(date.today(), replaced.valid_from):
        replaced.status = "archived"
    else:
        replaced.valid_until = min(replaced.valid_until or last_day, last_day)


def publish_fee(session: Session, fee: ProgramFee) -> ProgramFee:
    status = _published(
        fee.status,
        official=not fee.is_demo,
        valid_from=fee.valid_from,
        valid_until=fee.valid_until,
    )
    if _overlaps_published_fee(session, fee):
        raise ConflictError(
            "Un frais publié couvre déjà cette période pour ce libellé et cette année"
        )
    replaced = session.get(ProgramFee, fee.replaces_id) if fee.replaces_id else None
    if replaced and replaced.status == "published":
        _supersede(replaced, fee.valid_from)
        session.flush()
    return _save(session, _assign(fee, {"status": status}))


def archive_fee(session: Session, fee: ProgramFee) -> ProgramFee:
    return _save(session, _assign(fee, {"status": _archived(fee.status)}))


# Admission conditions
def requirements_of(program: Program) -> dict[str, Any]:
    return {field: getattr(program, column) for field, column in REQUIREMENT_COLUMNS.items()}


def save_requirements(session: Session, program: Program, values: dict[str, Any]) -> Program:
    columns = {REQUIREMENT_COLUMNS[field]: value for field, value in values.items()}
    return _save(session, _assign(program, columns | {"admission_status": "draft"}))


def publish_requirements(session: Session, program: Program) -> Program:
    status = _published(
        program.admission_status,
        official=program.admission_source_url is not None and not program.admission_is_demo,
        valid_from=program.admission_valid_from,
        valid_until=program.admission_valid_until,
    )
    return _save(session, _assign(program, {"admission_status": status}))


def archive_requirements(session: Session, program: Program) -> Program:
    status = _archived(program.admission_status)
    return _save(session, _assign(program, {"admission_status": status}))
