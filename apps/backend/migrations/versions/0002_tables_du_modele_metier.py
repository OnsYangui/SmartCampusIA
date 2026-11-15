"""tables du modele metier

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12 15:23:52.226977

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

ENUMS = {
    "program_type": ["licence", "prepa", "ingenieur", "autre"],
    "campaign_status": ["draft", "open", "closed"],
    "user_role": ["candidate", "academic_manager", "interview_manager", "management", "admin"],
    "candidate_status": ["VISITEUR", "EN_PROFILAGE", "ORIENTE", "ABANDONNE"],
    "application_status": [
        "PREINSCRIT",
        "QCM_TERMINE",
        "ORIENTATION_VALIDEE",
        "ENTRETIEN_PLANIFIE",
        "ENTRETIEN_REALISE",
        "COMPLEMENT_DEMANDE",
        "ADMIS",
        "REFUSE",
        "INSCRIT",
        "ABANDONNE",
    ],
    "recommendation_status": ["proposed", "validated", "adjusted"],
    "appointment_status": ["proposed", "accepted", "declined", "cancelled", "done"],
    "interview_result": ["admitted", "refused", "more_info"],
    "message_sender": ["candidate", "assistant"],
    "actor_type": ["human", "agent", "system"],
    "template_kind": ["email", "quiz"],
    "notification_type": ["confirmation", "reminder", "follow_up", "invitation"],
    "delivery_status": ["queued", "sent", "failed"],
    "document_source": ["pdf", "web_page", "faq"],
    "document_status": ["active", "archived"],
    "sync_trigger": ["upload", "update", "scheduled", "model_change"],
    "sync_status": ["pending", "running", "succeeded", "failed"],
}

# Rules the database guarantees but a CHECK cannot express (they read other tables).
TRIGGERS_SQL = """
CREATE FUNCTION check_application_consent() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM consents c
                   WHERE c.id = NEW.consent_id AND c.candidate_id = NEW.candidate_id
                     AND c.withdrawn_at IS NULL) THEN
        RAISE EXCEPTION 'RM-03 : consentement absent, retiré ou d''un autre candidat'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER applications_check_consent BEFORE INSERT ON applications
    FOR EACH ROW EXECUTE FUNCTION check_application_consent();

CREATE FUNCTION check_application_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM candidates
               WHERE id = NEW.candidate_id AND (first_name IS NULL OR last_name IS NULL)) THEN
        RAISE EXCEPTION 'Nom et prénom du candidat obligatoires pour créer un dossier'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER applications_check_identity BEFORE INSERT ON applications
    FOR EACH ROW EXECUTE FUNCTION check_application_identity();

CREATE FUNCTION check_candidate_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.first_name IS NULL OR NEW.last_name IS NULL)
       AND EXISTS (SELECT 1 FROM applications a WHERE a.candidate_id = NEW.id)
       AND EXISTS (SELECT 1 FROM consents c WHERE c.candidate_id = NEW.id AND c.withdrawn_at IS NULL)
    THEN
        RAISE EXCEPTION 'Nom et prénom obligatoires tant que le dossier existe et que le consentement est actif'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER candidates_check_identity BEFORE UPDATE OF first_name, last_name ON candidates
    FOR EACH ROW EXECUTE FUNCTION check_candidate_identity();

CREATE FUNCTION check_quiz_template() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.template_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM message_templates WHERE id = NEW.template_id AND kind = 'quiz') THEN
        RAISE EXCEPTION 'Le modèle d''un QCM doit être de type quiz' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER quizzes_check_template BEFORE INSERT OR UPDATE OF template_id ON quizzes
    FOR EACH ROW EXECUTE FUNCTION check_quiz_template();

CREATE FUNCTION check_citation_sender() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM messages WHERE id = NEW.message_id AND sender = 'assistant') THEN
        RAISE EXCEPTION 'RM-01 : seuls les messages de l''assistant ont des citations'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER message_citations_check_sender BEFORE INSERT OR UPDATE ON message_citations
    FOR EACH ROW EXECUTE FUNCTION check_citation_sender();

-- RM-10: append-only for the backend account.
REVOKE UPDATE, DELETE ON audit_logs, state_transitions FROM smartcampus_app;
"""

TRIGGER_FUNCTIONS = [
    "check_application_consent",
    "check_application_identity",
    "check_candidate_identity",
    "check_quiz_template",
    "check_citation_sender",
]

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the 17 enumerated types, then the 24 tables, triggers and grants."""
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(op.get_bind())
    op.create_table(
        "institutions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("website", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_institutions")),
        sa.UniqueConstraint("code", name=op.f("uq_institutions_code")),
    )
    op.create_table(
        "admission_campaigns",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("academic_year", sa.CHAR(length=9), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="campaign_status", create_type=False),
            server_default="draft",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "academic_year ~ '^[0-9]{4}-[0-9]{4}$'",
            name=op.f("ck_admission_campaigns_academic_year_format"),
        ),
        sa.CheckConstraint("ends_on > starts_on", name=op.f("ck_admission_campaigns_dates")),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_admission_campaigns_institution_id_institutions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admission_campaigns")),
    )
    op.create_index(
        op.f("ix_admission_campaigns_institution_id"),
        "admission_campaigns",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        "uq_admission_campaigns_one_open",
        "admission_campaigns",
        ["institution_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "programs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", postgresql.ENUM(name="program_type", create_type=False), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=True),
        sa.Column("duration_years", sa.SmallInteger(), nullable=False),
        sa.Column("admission_bac_sections", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("min_bac_average", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prerequisites", sa.Text(), nullable=True),
        sa.Column("career_outcomes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint(
            "duration_years BETWEEN 1 AND 5", name=op.f("ck_programs_duration_years")
        ),
        sa.CheckConstraint(
            "min_bac_average BETWEEN 0 AND 20", name=op.f("ck_programs_min_bac_average")
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_programs_institution_id_institutions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_programs")),
        sa.UniqueConstraint("code", name=op.f("uq_programs_code")),
    )
    op.create_index(
        op.f("ix_programs_institution_id"), "programs", ["institution_id"], unique=False
    )
    op.create_index(op.f("ix_programs_type"), "programs", ["type"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", postgresql.ENUM(name="user_role", create_type=False), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint(
            "(role IN ('academic_manager', 'interview_manager')) = (institution_id IS NOT NULL)",
            name=op.f("ck_users_institution_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_users_institution_id_institutions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_institution_id"), "users", ["institution_id"], unique=False)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column(
            "actor_type", postgresql.ENUM(name="actor_type", create_type=False), nullable=False
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("agent_name", sa.String(length=50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.CheckConstraint(
            "actor_type <> 'agent' OR agent_name IS NOT NULL",
            name=op.f("ck_audit_logs_agent_actor"),
        ),
        sa.CheckConstraint(
            "actor_type <> 'human' OR actor_user_id IS NOT NULL",
            name=op.f("ck_audit_logs_human_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"], unique=False
    )
    op.create_table(
        "candidates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id_hash", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="candidate_status", create_type=False),
            server_default="VISITEUR",
            nullable=False,
        ),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("preferred_language", sa.String(length=10), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "preferred_language IN ('fr', 'ar-TN', 'arabizi')",
            name=op.f("ck_candidates_preferred_language"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_candidates_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidates")),
        sa.UniqueConstraint("session_id_hash", name=op.f("uq_candidates_session_id_hash")),
        sa.UniqueConstraint("user_id", name=op.f("uq_candidates_user_id")),
    )
    op.create_index(
        op.f("ix_candidates_last_activity_at"), "candidates", ["last_activity_at"], unique=False
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM(name="document_source", create_type=False),
            nullable=False,
        ),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="document_status", create_type=False),
            server_default="active",
            nullable=False,
        ),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_documents_institution_id_institutions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_documents_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_documents_uploaded_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint(
            "institution_id", "source_uri", name=op.f("uq_documents_institution_id_source_uri")
        ),
    )
    op.create_index(op.f("ix_documents_program_id"), "documents", ["program_id"], unique=False)
    op.create_index(op.f("ix_documents_uploaded_by"), "documents", ["uploaded_by"], unique=False)
    op.create_table(
        "interview_slots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("published_by", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=150), nullable=True),
        sa.Column("is_published", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_interview_slots_dates")),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["users.id"],
            name=op.f("fk_interview_slots_published_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_slots")),
    )
    op.create_index(
        op.f("ix_interview_slots_published_by"), "interview_slots", ["published_by"], unique=False
    )
    op.create_table(
        "message_templates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="template_kind", create_type=False), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "kind <> 'email' OR subject IS NOT NULL",
            name=op.f("ck_message_templates_email_subject"),
        ),
        sa.CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)",
            name=op.f("ck_message_templates_approval"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name=op.f("fk_message_templates_approved_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_templates")),
        sa.UniqueConstraint("code", name=op.f("uq_message_templates_code")),
    )
    op.create_index(
        op.f("ix_message_templates_approved_by"), "message_templates", ["approved_by"], unique=False
    )
    op.create_table(
        "program_pathways",
        sa.Column("from_program_id", sa.Uuid(), nullable=False),
        sa.Column("to_program_id", sa.Uuid(), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "from_program_id <> to_program_id", name=op.f("ck_program_pathways_distinct_programs")
        ),
        sa.ForeignKeyConstraint(
            ["from_program_id"],
            ["programs.id"],
            name=op.f("fk_program_pathways_from_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_program_id"],
            ["programs.id"],
            name=op.f("fk_program_pathways_to_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "from_program_id", "to_program_id", name=op.f("pk_program_pathways")
        ),
    )
    op.create_index(
        op.f("ix_program_pathways_to_program_id"),
        "program_pathways",
        ["to_program_id"],
        unique=False,
    )
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("text_version", sa.String(length=20), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_consents_candidate_id_candidates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
    )
    op.create_index(op.f("ix_consents_candidate_id"), "consents", ["candidate_id"], unique=False)
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_conversations_candidate_id_candidates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        op.f("ix_conversations_candidate_id"), "conversations", ["candidate_id"], unique=False
    )
    op.create_table(
        "document_fragments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column(
            "content_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, content)", persisted=True),
            nullable=False,
        ),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_fragments_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_fragments")),
        sa.UniqueConstraint(
            "document_id",
            "document_version",
            "position",
            name=op.f("uq_document_fragments_document_id_document_version_position"),
        ),
    )
    op.create_index(
        "ix_document_fragments_content_tsv",
        "document_fragments",
        ["content_tsv"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_fragments_embedding_hnsw",
        "document_fragments",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "ix_document_fragments_institution_id_program_id",
        "document_fragments",
        ["institution_id", "program_id"],
        unique=False,
    )
    op.create_table(
        "document_syncs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column(
            "trigger_type", postgresql.ENUM(name="sync_trigger", create_type=False), nullable=False
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="sync_status", create_type=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("fragments_count", sa.Integer(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "status <> 'failed' OR error_message IS NOT NULL",
            name=op.f("ck_document_syncs_error_message"),
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR fragments_count IS NOT NULL",
            name=op.f("ck_document_syncs_fragments_count"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_syncs_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_document_syncs_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_syncs")),
    )
    op.create_index(
        op.f("ix_document_syncs_document_id"), "document_syncs", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_syncs_requested_by"), "document_syncs", ["requested_by"], unique=False
    )
    op.create_index(
        "uq_document_syncs_one_in_progress",
        "document_syncs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("bac_section", sa.String(length=50), nullable=True),
        sa.Column("bac_average", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("preferred_subjects", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("interests", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("career_goals", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
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
        sa.CheckConstraint("bac_average BETWEEN 0 AND 20", name=op.f("ck_profiles_bac_average")),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_profiles_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profiles")),
        sa.UniqueConstraint("candidate_id", name=op.f("uq_profiles_candidate_id")),
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="recommendation_status", create_type=False),
            server_default="proposed",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint(
            "status = 'proposed' OR reviewed_by IS NOT NULL",
            name=op.f("ck_recommendations_reviewer"),
        ),
        sa.CheckConstraint(
            "(reviewed_by IS NULL) = (reviewed_at IS NULL)",
            name=op.f("ck_recommendations_reviewed_at"),
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name=op.f("ck_recommendations_score")),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_recommendations_candidate_id_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_recommendations_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_recommendations_reviewed_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendations")),
    )
    op.create_index(
        "ix_recommendations_candidate_id_active",
        "recommendations",
        ["candidate_id"],
        unique=False,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        op.f("ix_recommendations_program_id"), "recommendations", ["program_id"], unique=False
    )
    op.create_index(
        op.f("ix_recommendations_reviewed_by"), "recommendations", ["reviewed_by"], unique=False
    )
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("consent_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="application_status", create_type=False),
            server_default="PREINSCRIT",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["admission_campaigns.id"],
            name=op.f("fk_applications_campaign_id_admission_campaigns"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_applications_candidate_id_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consent_id"],
            ["consents.id"],
            name=op.f("fk_applications_consent_id_consents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_applications_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint(
            "candidate_id", "campaign_id", name=op.f("uq_applications_candidate_id_campaign_id")
        ),
    )
    op.create_index(
        op.f("ix_applications_campaign_id"), "applications", ["campaign_id"], unique=False
    )
    op.create_index(
        op.f("ix_applications_consent_id"), "applications", ["consent_id"], unique=False
    )
    op.create_index(
        op.f("ix_applications_program_id"), "applications", ["program_id"], unique=False
    )
    op.create_index(op.f("ix_applications_status"), "applications", ["status"], unique=False)
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "sender", postgresql.ENUM(name="message_sender", create_type=False), nullable=False
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("audio_path", sa.String(length=255), nullable=True),
        sa.Column("transcription_reliable", sa.Boolean(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
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
        sa.CheckConstraint(
            "(audio_path IS NULL) = (transcription_reliable IS NULL)",
            name=op.f("ck_messages_voice_transcription"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slot_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="appointment_status", create_type=False),
            server_default="proposed",
            nullable=False,
        ),
        sa.Column(
            "result", postgresql.ENUM(name="interview_result", create_type=False), nullable=True
        ),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "result IS NULL OR decided_by IS NOT NULL", name=op.f("ck_appointments_decision_author")
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_appointments_application_id_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_appointments_decided_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["slot_id"],
            ["interview_slots.id"],
            name=op.f("fk_appointments_slot_id_interview_slots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
    )
    op.create_index(
        op.f("ix_appointments_application_id"), "appointments", ["application_id"], unique=False
    )
    op.create_index(
        op.f("ix_appointments_decided_by"), "appointments", ["decided_by"], unique=False
    )
    op.create_index(op.f("ix_appointments_slot_id"), "appointments", ["slot_id"], unique=False)
    op.create_index(
        "uq_appointments_one_accepted_per_slot",
        "appointments",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('accepted', 'done')"),
    )
    op.create_table(
        "message_citations",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("fragment_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["fragment_id"],
            ["document_fragments.id"],
            name=op.f("fk_message_citations_fragment_id_document_fragments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_citations_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id", "fragment_id", name=op.f("pk_message_citations")),
    )
    op.create_index(
        op.f("ix_message_citations_fragment_id"), "message_citations", ["fragment_id"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type", postgresql.ENUM(name="notification_type", create_type=False), nullable=False
        ),
        sa.Column("follow_up_number", sa.SmallInteger(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="delivery_status", create_type=False),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "(type = 'follow_up') = (follow_up_number IS NOT NULL)",
            name=op.f("ck_notifications_follow_up_number"),
        ),
        sa.CheckConstraint(
            "follow_up_number BETWEEN 1 AND 3", name=op.f("ck_notifications_follow_up_range")
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_notifications_application_id_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_notifications_candidate_id_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["message_templates.id"],
            name=op.f("fk_notifications_template_id_message_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        op.f("ix_notifications_application_id"), "notifications", ["application_id"], unique=False
    )
    op.create_index(
        op.f("ix_notifications_candidate_id"), "notifications", ["candidate_id"], unique=False
    )
    op.create_index(
        op.f("ix_notifications_template_id"), "notifications", ["template_id"], unique=False
    )
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("score BETWEEN 0 AND 100", name=op.f("ck_quizzes_score")),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_quizzes_application_id_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_quizzes_program_id_programs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["message_templates.id"],
            name=op.f("fk_quizzes_template_id_message_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quizzes")),
        sa.UniqueConstraint(
            "application_id", "program_id", name=op.f("uq_quizzes_application_id_program_id")
        ),
    )
    op.create_index(op.f("ix_quizzes_program_id"), "quizzes", ["program_id"], unique=False)
    op.create_index(op.f("ix_quizzes_template_id"), "quizzes", ["template_id"], unique=False)
    op.create_table(
        "state_transitions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("from_state", sa.String(length=30), nullable=True),
        sa.Column("to_state", sa.String(length=30), nullable=False),
        sa.Column(
            "actor_type", postgresql.ENUM(name="actor_type", create_type=False), nullable=False
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "actor_type <> 'human' OR actor_user_id IS NOT NULL",
            name=op.f("ck_state_transitions_human_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_state_transitions_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_state_transitions_application_id_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_state_transitions_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_state_transitions")),
    )
    op.create_index(
        op.f("ix_state_transitions_actor_user_id"),
        "state_transitions",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_state_transitions_application_id"),
        "state_transitions",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_state_transitions_candidate_id"),
        "state_transitions",
        ["candidate_id"],
        unique=False,
    )
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("quiz_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("choices", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correct_choice", sa.SmallInteger(), nullable=False),
        sa.Column("candidate_choice", sa.SmallInteger(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
            name=op.f("fk_quiz_questions_quiz_id_quizzes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_questions")),
        sa.UniqueConstraint("quiz_id", "position", name=op.f("uq_quiz_questions_quiz_id_position")),
    )
    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    """Drop tables (and their triggers), trigger functions and enumerated types."""
    op.drop_table("quiz_questions")
    op.drop_index(op.f("ix_state_transitions_candidate_id"), table_name="state_transitions")
    op.drop_index(op.f("ix_state_transitions_application_id"), table_name="state_transitions")
    op.drop_index(op.f("ix_state_transitions_actor_user_id"), table_name="state_transitions")
    op.drop_table("state_transitions")
    op.drop_index(op.f("ix_quizzes_template_id"), table_name="quizzes")
    op.drop_index(op.f("ix_quizzes_program_id"), table_name="quizzes")
    op.drop_table("quizzes")
    op.drop_index(op.f("ix_notifications_template_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_candidate_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_application_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_message_citations_fragment_id"), table_name="message_citations")
    op.drop_table("message_citations")
    op.drop_index(
        "uq_appointments_one_accepted_per_slot",
        table_name="appointments",
        postgresql_where=sa.text("status IN ('accepted', 'done')"),
    )
    op.drop_index(op.f("ix_appointments_slot_id"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_decided_by"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_application_id"), table_name="appointments")
    op.drop_table("appointments")
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_applications_status"), table_name="applications")
    op.drop_index(op.f("ix_applications_program_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_consent_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_campaign_id"), table_name="applications")
    op.drop_table("applications")
    op.drop_index(op.f("ix_recommendations_reviewed_by"), table_name="recommendations")
    op.drop_index(op.f("ix_recommendations_program_id"), table_name="recommendations")
    op.drop_index(
        "ix_recommendations_candidate_id_active",
        table_name="recommendations",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("recommendations")
    op.drop_table("profiles")
    op.drop_index(
        "uq_document_syncs_one_in_progress",
        table_name="document_syncs",
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.drop_index(op.f("ix_document_syncs_requested_by"), table_name="document_syncs")
    op.drop_index(op.f("ix_document_syncs_document_id"), table_name="document_syncs")
    op.drop_table("document_syncs")
    op.drop_index(
        "ix_document_fragments_institution_id_program_id", table_name="document_fragments"
    )
    op.drop_index(
        "ix_document_fragments_embedding_hnsw",
        table_name="document_fragments",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("is_current"),
    )
    op.drop_index(
        "ix_document_fragments_content_tsv", table_name="document_fragments", postgresql_using="gin"
    )
    op.drop_table("document_fragments")
    op.drop_index(op.f("ix_conversations_candidate_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(op.f("ix_consents_candidate_id"), table_name="consents")
    op.drop_table("consents")
    op.drop_index(op.f("ix_program_pathways_to_program_id"), table_name="program_pathways")
    op.drop_table("program_pathways")
    op.drop_index(op.f("ix_message_templates_approved_by"), table_name="message_templates")
    op.drop_table("message_templates")
    op.drop_index(op.f("ix_interview_slots_published_by"), table_name="interview_slots")
    op.drop_table("interview_slots")
    op.drop_index(op.f("ix_documents_uploaded_by"), table_name="documents")
    op.drop_index(op.f("ix_documents_program_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_candidates_last_activity_at"), table_name="candidates")
    op.drop_table("candidates")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_users_institution_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_programs_type"), table_name="programs")
    op.drop_index(op.f("ix_programs_institution_id"), table_name="programs")
    op.drop_table("programs")
    op.drop_index(
        "uq_admission_campaigns_one_open",
        table_name="admission_campaigns",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index(op.f("ix_admission_campaigns_institution_id"), table_name="admission_campaigns")
    op.drop_table("admission_campaigns")
    op.drop_table("institutions")
    for function in TRIGGER_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(op.get_bind())
