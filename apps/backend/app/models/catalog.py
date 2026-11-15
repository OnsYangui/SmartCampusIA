"""SA-12 — Academic catalogue; SA-21 — tuition fees and admission provenance."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamped, uuid_pk
from app.models.enums import campaign_status, program_type, publication_status


class Institution(Timestamped, Base):
    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    website: Mapped[str | None] = mapped_column(String(255))


class Program(Timestamped, Base):
    __tablename__ = "programs"
    __table_args__ = (
        CheckConstraint("duration_years BETWEEN 1 AND 5", name="duration_years"),
        CheckConstraint("min_bac_average BETWEEN 0 AND 20", name="min_bac_average"),
        CheckConstraint(
            "(admission_source_url IS NULL) = (admission_verified_on IS NULL) "
            "AND NOT (admission_is_demo AND admission_source_url IS NOT NULL)",
            name="admission_provenance",
        ),
        CheckConstraint(
            "admission_status <> 'published' "
            "OR (admission_source_url IS NOT NULL AND admission_valid_from IS NOT NULL)",
            name="admission_publication",
        ),
        CheckConstraint(
            "admission_valid_until IS NULL OR (admission_valid_from IS NOT NULL "
            "AND admission_valid_until >= admission_valid_from)",
            name="admission_validity",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(program_type, index=True)
    field: Mapped[str | None] = mapped_column(String(100))
    duration_years: Mapped[int] = mapped_column(SmallInteger)
    admission_bac_sections: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    min_bac_average: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    description: Mapped[str | None] = mapped_column(Text)
    prerequisites: Mapped[str | None] = mapped_column(Text)
    career_outcomes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    # Official document the admission conditions were checked against (SA-21).
    admission_source_url: Mapped[str | None] = mapped_column(String(500))
    admission_verified_on: Mapped[date | None] = mapped_column(Date)
    admission_is_demo: Mapped[bool] = mapped_column(server_default=text("false"))
    admission_status: Mapped[str] = mapped_column(publication_status, server_default="draft")
    admission_valid_from: Mapped[date | None] = mapped_column(Date)
    admission_valid_until: Mapped[date | None] = mapped_column(Date)

    institution: Mapped[Institution] = relationship(lazy="raise")


class ProgramFee(Timestamped, Base):
    """Tuition fees of a program for one academic year (SA-21)."""

    __tablename__ = "program_fees"
    __table_args__ = (
        # One draft per fee and one pending revision per published fee; published versions of a
        # fee never overlap (trigger program_fees_published_overlap, migration 0007).
        Index(
            "uq_program_fees_one_draft",
            "program_id",
            "academic_year",
            "label",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
        Index(
            "uq_program_fees_one_revision",
            "replaces_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
        CheckConstraint(
            "CASE WHEN academic_year ~ '^[0-9]{4}-[0-9]{4}$' "
            "THEN right(academic_year, 4)::int = left(academic_year, 4)::int + 1 ELSE false END",
            name="academic_year_format",
        ),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        # Real fees always cite an official source; anything else must be flagged as demo data.
        CheckConstraint(
            "is_demo OR (source_url IS NOT NULL AND verified_on IS NOT NULL)",
            name="official_or_demo",
        ),
        CheckConstraint(
            "status <> 'published' OR (NOT is_demo AND valid_from IS NOT NULL)", name="publication"
        ),
        CheckConstraint(
            "valid_until IS NULL OR (valid_from IS NOT NULL AND valid_until >= valid_from)",
            name="validity",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), index=True
    )
    academic_year: Mapped[str] = mapped_column(CHAR(9))
    label: Mapped[str] = mapped_column(String(150))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="TND")
    is_demo: Mapped[bool] = mapped_column(server_default=text("false"))
    source_url: Mapped[str | None] = mapped_column(String(500))
    verified_on: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(publication_status, server_default="draft")
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("program_fees.id", ondelete="RESTRICT"), index=True
    )


class ProgramSpecialty(Timestamped, Base):
    """Track or specialisation of a program (SA-20), e.g. GLID in génie informatique."""

    __tablename__ = "program_specialties"
    __table_args__ = (
        UniqueConstraint("program_id", "code"),
        UniqueConstraint("id", "program_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Subject(Timestamped, Base):
    """Subject of a program's curriculum, common core or specific to one specialty (SA-20)."""

    __tablename__ = "subjects"
    __table_args__ = (
        # A specialty-specific subject must belong to a specialty of the same program.
        ForeignKeyConstraint(
            ["specialty_id", "program_id"],
            ["program_specialties.id", "program_specialties.program_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "program_id",
            "specialty_id",
            "study_year",
            "name",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("study_year BETWEEN 1 AND 6", name="study_year"),
        CheckConstraint("semester BETWEEN 1 AND 12", name="semester"),
        CheckConstraint("credits > 0", name="positive_credits"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), index=True
    )
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    study_year: Mapped[int] = mapped_column(SmallInteger)
    semester: Mapped[int | None] = mapped_column(SmallInteger)
    credits: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class ProgramPathway(Timestamped, Base):
    __tablename__ = "program_pathways"
    __table_args__ = (
        CheckConstraint("from_program_id <> to_program_id", name="distinct_programs"),
    )

    from_program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), primary_key=True
    )
    to_program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    conditions: Mapped[str | None] = mapped_column(Text)


class AdmissionCampaign(Timestamped, Base):
    __tablename__ = "admission_campaigns"
    __table_args__ = (
        CheckConstraint("academic_year ~ '^[0-9]{4}-[0-9]{4}$'", name="academic_year_format"),
        CheckConstraint("ends_on > starts_on", name="dates"),
        # One open campaign per institution at a time (SA-12).
        Index(
            "uq_admission_campaigns_one_open",
            "institution_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    academic_year: Mapped[str] = mapped_column(CHAR(9))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(campaign_status, server_default="draft")
