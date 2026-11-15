"""Academic catalogue queries (SA-20) and admission rules (SA-21), shared by the API and agents.

Candidates and agents only ever receive published fees and conditions that are valid on the day.
"""

import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Institution, Program, ProgramFee, ProgramPathway, ProgramSpecialty, Subject

EligibilityStatus = Literal["eligible", "not_eligible", "undetermined"]


@dataclass(frozen=True)
class ProgramFilters:
    institution: str | None = None
    type: str | None = None
    q: str | None = None


@dataclass(frozen=True)
class SubjectFilters:
    study_year: int | None = None
    specialty_id: uuid.UUID | None = None
    q: str | None = None


@dataclass(frozen=True)
class Requirements:
    bac_sections: list[str] | None
    min_bac_average: Decimal | None
    prerequisites: str | None
    source_url: str | None = None
    verified_on: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None


@dataclass(frozen=True)
class EligibilityCheck:
    criterion: str
    met: bool


@dataclass(frozen=True)
class Eligibility:
    status: EligibilityStatus
    checks: list[EligibilityCheck]


def paginate[T](
    session: Session, query: Select[tuple[T]], offset: int, limit: int
) -> tuple[list[T], int]:
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = session.scalars(query.offset(offset).limit(limit)).all()
    return list(items), total or 0


def _contains(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _normalized(section: str) -> str:
    decomposed = unicodedata.normalize("NFKD", section.strip().casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _published_on(status, valid_from, valid_until, on: date) -> ColumnElement[bool]:
    return (
        (status == "published") & (valid_from <= on) & or_(valid_until.is_(None), valid_until >= on)
    )


def list_institutions(session: Session, offset: int, limit: int) -> tuple[list[Institution], int]:
    return paginate(session, select(Institution).order_by(Institution.code), offset, limit)


def get_institution(session: Session, institution_id: uuid.UUID) -> Institution | None:
    return session.get(Institution, institution_id)


def programs_query(
    filters: ProgramFilters,
    *,
    active_only: bool = True,
    institution_id: uuid.UUID | None = None,
) -> Select[tuple[Program]]:
    query = (
        select(Program)
        .join(Program.institution)
        .options(joinedload(Program.institution))
        .order_by(Institution.code, Program.name, Program.code)
    )
    if active_only:
        query = query.where(Program.is_active)
    if institution_id:
        query = query.where(Program.institution_id == institution_id)
    if filters.institution:
        query = query.where(func.upper(Institution.code) == filters.institution.upper())
    if filters.type:
        query = query.where(Program.type == filters.type)
    if filters.q:
        pattern = _contains(filters.q)
        query = query.where(
            or_(
                Program.name.ilike(pattern, escape="\\"),
                Program.code.ilike(pattern, escape="\\"),
                Program.field.ilike(pattern, escape="\\"),
            )
        )
    return query


def list_programs(
    session: Session, filters: ProgramFilters, offset: int, limit: int
) -> tuple[list[Program], int]:
    return paginate(session, programs_query(filters), offset, limit)


def get_active_program(session: Session, program_id: uuid.UUID) -> Program | None:
    return session.scalar(
        select(Program)
        .options(joinedload(Program.institution))
        .where(Program.id == program_id, Program.is_active)
    )


def list_pathways(session: Session, program_id: uuid.UUID) -> list[tuple[Program, str | None]]:
    rows = session.execute(
        select(Program, ProgramPathway.conditions)
        .join(ProgramPathway, ProgramPathway.to_program_id == Program.id)
        .where(ProgramPathway.from_program_id == program_id, Program.is_active)
        .order_by(Program.name)
    )
    return [(program, conditions) for program, conditions in rows]


def specialties_query(program_id: uuid.UUID, *, active_only: bool = True) -> Select:
    query = (
        select(ProgramSpecialty)
        .where(ProgramSpecialty.program_id == program_id)
        .order_by(ProgramSpecialty.code)
    )
    return query.where(ProgramSpecialty.is_active) if active_only else query


def list_specialties(session: Session, program_id: uuid.UUID) -> list[ProgramSpecialty]:
    return list(session.scalars(specialties_query(program_id)))


def subjects_query(
    program_id: uuid.UUID, filters: SubjectFilters, *, active_only: bool = True
) -> Select[tuple[Subject]]:
    query = (
        select(Subject)
        .where(Subject.program_id == program_id)
        .order_by(Subject.study_year, Subject.semester.nulls_first(), Subject.name)
    )
    if active_only:
        query = query.where(Subject.is_active)
    if filters.study_year:
        query = query.where(Subject.study_year == filters.study_year)
    if filters.specialty_id:
        query = query.where(Subject.specialty_id == filters.specialty_id)
    if filters.q:
        query = query.where(Subject.name.ilike(_contains(filters.q), escape="\\"))
    return query


def list_subjects(
    session: Session, program_id: uuid.UUID, filters: SubjectFilters, offset: int, limit: int
) -> tuple[list[Subject], int]:
    return paginate(session, subjects_query(program_id, filters), offset, limit)


def list_published_fees(
    session: Session, program_id: uuid.UUID, on: date, academic_year: str | None = None
) -> list[ProgramFee]:
    query = (
        select(ProgramFee)
        .where(
            ProgramFee.program_id == program_id,
            _published_on(ProgramFee.status, ProgramFee.valid_from, ProgramFee.valid_until, on),
        )
        .order_by(ProgramFee.academic_year.desc(), ProgramFee.label)
    )
    if academic_year:
        query = query.where(ProgramFee.academic_year == academic_year)
    return list(session.scalars(query))


def published_requirements(program: Program, on: date) -> Requirements | None:
    published = (
        program.admission_status == "published"
        and program.admission_valid_from is not None
        and program.admission_valid_from <= on
        and (program.admission_valid_until is None or program.admission_valid_until >= on)
    )
    if not published:
        return None
    return Requirements(
        bac_sections=program.admission_bac_sections,
        min_bac_average=program.min_bac_average,
        prerequisites=program.prerequisites,
        source_url=program.admission_source_url,
        verified_on=program.admission_verified_on,
        valid_from=program.admission_valid_from,
        valid_until=program.admission_valid_until,
    )


def assess_eligibility(
    requirements: Requirements | None, bac_section: str, bac_average: Decimal
) -> Eligibility:
    """Compares a baccalaureate with published conditions; the admission decision stays human.

    Without published, measurable conditions the result is undetermined.
    """
    if requirements is None:
        return Eligibility("undetermined", [])
    checks = []
    if requirements.bac_sections:
        accepted = {_normalized(section) for section in requirements.bac_sections}
        checks.append(EligibilityCheck("bac_section", _normalized(bac_section) in accepted))
    if requirements.min_bac_average is not None:
        checks.append(
            EligibilityCheck("min_bac_average", bac_average >= requirements.min_bac_average)
        )
    if not checks:
        return Eligibility("undetermined", checks)
    return Eligibility("eligible" if all(c.met for c in checks) else "not_eligible", checks)
