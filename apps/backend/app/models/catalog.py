"""SA-12 — Academic catalogue."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, uuid_pk
from app.models.enums import campaign_status, program_type


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
