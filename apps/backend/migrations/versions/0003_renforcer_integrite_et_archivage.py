"""renforcer l'integrite des dossiers et l'archivage des documents

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply cross-table checks on updates and enforce document archival."""
    op.execute("DROP TRIGGER applications_check_consent ON applications")
    op.execute(
        """
        CREATE TRIGGER applications_check_consent
        BEFORE INSERT OR UPDATE OF candidate_id, consent_id ON applications
        FOR EACH ROW EXECUTE FUNCTION check_application_consent()
        """
    )

    op.execute("DROP TRIGGER applications_check_identity ON applications")
    op.execute(
        """
        CREATE TRIGGER applications_check_identity
        BEFORE INSERT OR UPDATE OF candidate_id ON applications
        FOR EACH ROW EXECUTE FUNCTION check_application_identity()
        """
    )

    # Physical deletion is restricted to the two SA-13 retention workflows.
    op.execute("REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM smartcampus_app")
    op.execute("GRANT DELETE ON candidates, conversations TO smartcampus_app")
    op.execute(
        "REVOKE ALL PRIVILEGES ON alembic_version FROM smartcampus_app, smartcampus_readonly"
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE smartcampus_owner IN SCHEMA public
        REVOKE DELETE ON TABLES FROM smartcampus_app
        """
    )


def downgrade() -> None:
    """Restore the original insert-only checks and document permissions."""
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE smartcampus_owner IN SCHEMA public
        GRANT DELETE ON TABLES TO smartcampus_app
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON alembic_version TO smartcampus_app")
    op.execute("GRANT SELECT ON alembic_version TO smartcampus_readonly")
    op.execute("GRANT DELETE ON ALL TABLES IN SCHEMA public TO smartcampus_app")
    op.execute("REVOKE DELETE ON audit_logs, state_transitions FROM smartcampus_app")

    op.execute("DROP TRIGGER applications_check_identity ON applications")
    op.execute(
        """
        CREATE TRIGGER applications_check_identity
        BEFORE INSERT ON applications
        FOR EACH ROW EXECUTE FUNCTION check_application_identity()
        """
    )

    op.execute("DROP TRIGGER applications_check_consent ON applications")
    op.execute(
        """
        CREATE TRIGGER applications_check_consent
        BEFORE INSERT ON applications
        FOR EACH ROW EXECUTE FUNCTION check_application_consent()
        """
    )
