"""revisions des frais publies

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY = ["program_id", "academic_year", "label"]
DRAFT = sa.text("status = 'draft'")


def upgrade() -> None:
    """Revise published fees without withdrawing them, and forbid overlapping published fees."""
    op.add_column("program_fees", sa.Column("replaces_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_program_fees_replaces_id_program_fees"),
        "program_fees",
        "program_fees",
        ["replaces_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_program_fees_replaces_id"), "program_fees", ["replaces_id"])

    op.drop_index("uq_program_fees_program_id_academic_year_label", table_name="program_fees")
    op.create_index(
        "uq_program_fees_one_draft", "program_fees", KEY, unique=True, postgresql_where=DRAFT
    )
    op.create_index(
        "uq_program_fees_one_revision",
        "program_fees",
        ["replaces_id"],
        unique=True,
        postgresql_where=DRAFT,
    )

    op.execute(
        """
        CREATE FUNCTION check_published_fee_overlap() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.status <> 'published' THEN
                RETURN NEW;
            END IF;
            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.program_id::text || NEW.academic_year || NEW.label, 0)
            );
            IF EXISTS (
                SELECT 1 FROM program_fees AS other
                WHERE other.id <> NEW.id
                  AND other.status = 'published'
                  AND other.program_id = NEW.program_id
                  AND other.academic_year = NEW.academic_year
                  AND other.label = NEW.label
                  AND daterange(other.valid_from, other.valid_until, '[]')
                      && daterange(NEW.valid_from, NEW.valid_until, '[]')
            ) THEN
                RAISE EXCEPTION 'program_fees_published_overlap: % overlaps another published fee',
                    NEW.label USING ERRCODE = 'exclusion_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER program_fees_published_overlap
        BEFORE INSERT OR UPDATE OF status, program_id, academic_year, label, valid_from, valid_until
        ON program_fees FOR EACH ROW EXECUTE FUNCTION check_published_fee_overlap()
        """
    )


def downgrade() -> None:
    """Back to one non-archived fee per program, year and label (fails if versions coexist)."""
    op.execute("DROP TRIGGER program_fees_published_overlap ON program_fees")
    op.execute("DROP FUNCTION check_published_fee_overlap()")
    op.drop_index("uq_program_fees_one_revision", table_name="program_fees")
    op.drop_index("uq_program_fees_one_draft", table_name="program_fees")
    op.create_index(
        "uq_program_fees_program_id_academic_year_label",
        "program_fees",
        KEY,
        unique=True,
        postgresql_where=sa.text("status <> 'archived'"),
    )
    op.drop_index(op.f("ix_program_fees_replaces_id"), table_name="program_fees")
    op.drop_constraint(
        op.f("fk_program_fees_replaces_id_program_fees"), "program_fees", type_="foreignkey"
    )
    op.drop_column("program_fees", "replaces_id")
