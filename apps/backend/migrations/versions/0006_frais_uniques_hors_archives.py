"""frais uniques hors archives

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "uq_program_fees_program_id_academic_year_label"
COLUMNS = ["program_id", "academic_year", "label"]


def upgrade() -> None:
    """One current fee per program, year and label; archived fees no longer block a replacement."""
    op.drop_constraint(NAME, "program_fees", type_="unique")
    op.create_index(
        NAME,
        "program_fees",
        COLUMNS,
        unique=True,
        postgresql_where=sa.text("status <> 'archived'"),
    )


def downgrade() -> None:
    """Restore uniqueness across every status (fails if archived duplicates exist)."""
    op.drop_index(NAME, table_name="program_fees")
    op.create_unique_constraint(NAME, "program_fees", COLUMNS)
