"""frais de scolarite et provenance des conditions d'admission

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROGRAM_PROVENANCE = (
    "(admission_source_url IS NULL) = (admission_verified_on IS NULL) "
    "AND NOT (admission_is_demo AND admission_source_url IS NOT NULL)"
)
ACADEMIC_YEAR = (
    "CASE WHEN academic_year ~ '^[0-9]{4}-[0-9]{4}$' "
    "THEN right(academic_year, 4)::int = left(academic_year, 4)::int + 1 ELSE false END"
)


def upgrade() -> None:
    """Add tuition fees and the official source of admission conditions (SA-21)."""
    op.add_column("programs", sa.Column("admission_source_url", sa.String(length=500)))
    op.add_column("programs", sa.Column("admission_verified_on", sa.Date()))
    op.add_column(
        "programs",
        sa.Column(
            "admission_is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.execute(
        "UPDATE programs SET admission_is_demo = true WHERE prerequisites LIKE 'DÉMO FICTIVE%'"
    )
    op.create_check_constraint(
        op.f("ck_programs_admission_provenance"),
        "programs",
        PROGRAM_PROVENANCE,
    )

    op.create_table(
        "program_fees",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("academic_year", sa.CHAR(length=9), nullable=False),
        sa.Column("label", sa.String(length=150), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="TND", nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verified_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(ACADEMIC_YEAR, name=op.f("ck_program_fees_academic_year_format")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_program_fees_positive_amount")),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_program_fees_currency_code")),
        sa.CheckConstraint(
            "is_demo OR (source_url IS NOT NULL AND verified_on IS NOT NULL)",
            name=op.f("ck_program_fees_official_or_demo"),
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_program_fees_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_program_fees")),
        sa.UniqueConstraint(
            "program_id",
            "academic_year",
            "label",
            name=op.f("uq_program_fees_program_id_academic_year_label"),
        ),
    )
    op.create_index(op.f("ix_program_fees_program_id"), "program_fees", ["program_id"])


def downgrade() -> None:
    """Remove tuition fees and admission provenance."""
    op.drop_index(op.f("ix_program_fees_program_id"), table_name="program_fees")
    op.drop_table("program_fees")
    op.drop_constraint(op.f("ck_programs_admission_provenance"), "programs", type_="check")
    op.drop_column("programs", "admission_is_demo")
    op.drop_column("programs", "admission_verified_on")
    op.drop_column("programs", "admission_source_url")
