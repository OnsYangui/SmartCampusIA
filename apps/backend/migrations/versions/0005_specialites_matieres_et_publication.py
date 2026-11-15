"""specialites, matieres et publication des frais et conditions d'admission

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

publication_status = postgresql.ENUM(
    "draft", "published", "archived", name="publication_status", create_type=False
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def _validity(prefix: str) -> str:
    return (
        f"{prefix}valid_until IS NULL OR ({prefix}valid_from IS NOT NULL "
        f"AND {prefix}valid_until >= {prefix}valid_from)"
    )


def upgrade() -> None:
    """Add specialties and subjects (SA-20) and the publication of fees and conditions (SA-21)."""
    publication_status.create(op.get_bind())

    op.add_column(
        "programs",
        sa.Column("admission_status", publication_status, server_default="draft", nullable=False),
    )
    op.add_column("programs", sa.Column("admission_valid_from", sa.Date()))
    op.add_column("programs", sa.Column("admission_valid_until", sa.Date()))
    op.execute(
        "UPDATE programs SET admission_status = 'published', "
        "admission_valid_from = admission_verified_on WHERE admission_source_url IS NOT NULL"
    )
    op.create_check_constraint(
        op.f("ck_programs_admission_publication"),
        "programs",
        "admission_status <> 'published' "
        "OR (admission_source_url IS NOT NULL AND admission_valid_from IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_programs_admission_validity"), "programs", _validity("admission_")
    )

    op.add_column("program_fees", sa.Column("payment_terms", sa.Text()))
    op.add_column(
        "program_fees",
        sa.Column("status", publication_status, server_default="draft", nullable=False),
    )
    op.add_column("program_fees", sa.Column("valid_from", sa.Date()))
    op.add_column("program_fees", sa.Column("valid_until", sa.Date()))
    op.create_check_constraint(
        op.f("ck_program_fees_publication"),
        "program_fees",
        "status <> 'published' OR (NOT is_demo AND valid_from IS NOT NULL)",
    )
    op.create_check_constraint(op.f("ck_program_fees_validity"), "program_fees", _validity(""))

    op.create_table(
        "program_specialties",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_program_specialties_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_program_specialties")),
        sa.UniqueConstraint("id", "program_id", name=op.f("uq_program_specialties_id_program_id")),
        sa.UniqueConstraint(
            "program_id", "code", name=op.f("uq_program_specialties_program_id_code")
        ),
    )
    op.create_index(
        op.f("ix_program_specialties_program_id"), "program_specialties", ["program_id"]
    )

    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("specialty_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("study_year", sa.SmallInteger(), nullable=False),
        sa.Column("semester", sa.SmallInteger(), nullable=True),
        sa.Column("credits", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("credits > 0", name=op.f("ck_subjects_positive_credits")),
        sa.CheckConstraint("semester BETWEEN 1 AND 12", name=op.f("ck_subjects_semester")),
        sa.CheckConstraint("study_year BETWEEN 1 AND 6", name=op.f("ck_subjects_study_year")),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_subjects_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["specialty_id", "program_id"],
            ["program_specialties.id", "program_specialties.program_id"],
            name=op.f("fk_subjects_specialty_id_program_specialties"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subjects")),
        sa.UniqueConstraint(
            "program_id",
            "specialty_id",
            "study_year",
            "name",
            name=op.f("uq_subjects_program_id_specialty_id_study_year_name"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(op.f("ix_subjects_program_id"), "subjects", ["program_id"])
    op.create_index(op.f("ix_subjects_specialty_id"), "subjects", ["specialty_id"])


def downgrade() -> None:
    """Remove specialties, subjects and publication data."""
    op.drop_index(op.f("ix_subjects_specialty_id"), table_name="subjects")
    op.drop_index(op.f("ix_subjects_program_id"), table_name="subjects")
    op.drop_table("subjects")
    op.drop_index(op.f("ix_program_specialties_program_id"), table_name="program_specialties")
    op.drop_table("program_specialties")

    op.drop_constraint(op.f("ck_program_fees_validity"), "program_fees", type_="check")
    op.drop_constraint(op.f("ck_program_fees_publication"), "program_fees", type_="check")
    for column in ("valid_until", "valid_from", "status", "payment_terms"):
        op.drop_column("program_fees", column)

    op.drop_constraint(op.f("ck_programs_admission_validity"), "programs", type_="check")
    op.drop_constraint(op.f("ck_programs_admission_publication"), "programs", type_="check")
    for column in ("admission_valid_until", "admission_valid_from", "admission_status"):
        op.drop_column("programs", column)

    publication_status.drop(op.get_bind())
