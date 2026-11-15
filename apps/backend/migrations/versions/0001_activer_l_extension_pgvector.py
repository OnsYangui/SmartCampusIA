"""activer l'extension pgvector

Revision ID: 0001
Revises:
Create Date: 2026-11-11 16:48:08.828601

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Installed by infra/postgres/init (superuser): pgvector is not a trusted extension.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # The extension belongs to the superuser setup script; smartcampus_owner cannot drop it.
    pass
