"""SA-13 — Users and applications."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, uuid_pk
from app.models.enums import (
    actor_type,
    application_status,
    appointment_status,
    candidate_status,
    delivery_status,
    interview_result,
    message_sender,
    notification_type,
    recommendation_status,
    template_kind,
    user_role,
)


def fk(target: str, ondelete: str = "RESTRICT") -> ForeignKey:
    return ForeignKey(target, ondelete=ondelete)


# Accounts and candidates
class User(Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Mandatory for the two manager roles, empty otherwise.
        CheckConstraint(
            "(role IN ('academic_manager', 'interview_manager')) = (institution_id IS NOT NULL)",
            name="institution_scope",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(user_role)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(fk("institutions.id"), index=True)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Candidate(Timestamped, Base):
    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint(
            "preferred_language IN ('fr', 'ar-TN', 'arabizi')", name="preferred_language"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # RESTRICT: on consent withdrawal the account is anonymised, never deleted (SA-13, RM-13).
    user_id: Mapped[uuid.UUID | None] = mapped_column(fk("users.id"), unique=True)
    session_id_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    status: Mapped[str] = mapped_column(candidate_status, server_default="VISITEUR")
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    preferred_language: Mapped[str | None] = mapped_column(String(10))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Profile(Timestamped, Base):
    __tablename__ = "profiles"
    __table_args__ = (CheckConstraint("bac_average BETWEEN 0 AND 20", name="bac_average"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    # CASCADE (C1): the anonymous row is deleted when a known candidate logs in on a new device.
    candidate_id: Mapped[uuid.UUID] = mapped_column(fk("candidates.id", "CASCADE"), unique=True)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    bac_section: Mapped[str | None] = mapped_column(String(50))
    bac_average: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    preferred_subjects: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    interests: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    career_goals: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)

    # The ORM increments version on every update.
    __mapper_args__ = {"version_id_col": version}


class Consent(Timestamped, Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(fk("candidates.id"), index=True)
    text_version: Mapped[str] = mapped_column(String(20))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Conversations
class Conversation(Timestamped, Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(fk("candidates.id"), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Timestamped, Base):
    __tablename__ = "messages"
    __table_args__ = (
        # transcription_reliable is filled only for a voice message (RM-12).
        CheckConstraint(
            "(audio_path IS NULL) = (transcription_reliable IS NULL)", name="voice_transcription"
        ),
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(fk("conversations.id", "CASCADE"))
    sender: Mapped[str] = mapped_column(message_sender)
    content: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(String(255))
    transcription_reliable: Mapped[bool | None]
    language: Mapped[str | None] = mapped_column(String(10))


class MessageCitation(Timestamped, Base):
    __tablename__ = "message_citations"

    message_id: Mapped[uuid.UUID] = mapped_column(fk("messages.id", "CASCADE"), primary_key=True)
    fragment_id: Mapped[uuid.UUID] = mapped_column(
        fk("document_fragments.id"), primary_key=True, index=True
    )


# Orientation and applications
class Recommendation(Timestamped, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score"),
        CheckConstraint("status = 'proposed' OR reviewed_by IS NOT NULL", name="reviewer"),
        CheckConstraint("(reviewed_by IS NULL) = (reviewed_at IS NULL)", name="reviewed_at"),
        Index(
            "ix_recommendations_candidate_id_active",
            "candidate_id",
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(fk("candidates.id"))
    program_id: Mapped[uuid.UUID] = mapped_column(fk("programs.id"), index=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    justification: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(recommendation_status, server_default="proposed")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(fk("users.id"), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Application(Timestamped, Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("candidate_id", "campaign_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(fk("candidates.id"))
    program_id: Mapped[uuid.UUID] = mapped_column(fk("programs.id"), index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(fk("admission_campaigns.id"), index=True)
    consent_id: Mapped[uuid.UUID] = mapped_column(fk("consents.id"), index=True)
    status: Mapped[str] = mapped_column(application_status, server_default="PREINSCRIT", index=True)


class StateTransition(Timestamped, Base):
    """Append-only (RM-10): smartcampus_app has no UPDATE / DELETE on this table."""

    __tablename__ = "state_transitions"
    __table_args__ = (
        CheckConstraint("actor_type <> 'human' OR actor_user_id IS NOT NULL", name="human_actor"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # CASCADE (C1): see Profile.candidate_id.
    candidate_id: Mapped[uuid.UUID] = mapped_column(fk("candidates.id", "CASCADE"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(fk("applications.id"), index=True)
    from_state: Mapped[str | None] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30))
    actor_type: Mapped[str] = mapped_column(actor_type)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(fk("users.id"), index=True)
    reason: Mapped[str | None] = mapped_column(Text)


# Quizzes and interviews
class Quiz(Timestamped, Base):
    __tablename__ = "quizzes"
    __table_args__ = (
        UniqueConstraint("application_id", "program_id"),
        CheckConstraint("score BETWEEN 0 AND 100", name="score"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(fk("applications.id"))
    program_id: Mapped[uuid.UUID] = mapped_column(fk("programs.id"), index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(fk("message_templates.id"), index=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    summary: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuizQuestion(Timestamped, Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (UniqueConstraint("quiz_id", "position"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    quiz_id: Mapped[uuid.UUID] = mapped_column(fk("quizzes.id"))
    position: Mapped[int] = mapped_column(SmallInteger)
    statement: Mapped[str] = mapped_column(Text)
    choices: Mapped[Any] = mapped_column(JSONB)
    correct_choice: Mapped[int] = mapped_column(SmallInteger)
    candidate_choice: Mapped[int | None] = mapped_column(SmallInteger)


class InterviewSlot(Timestamped, Base):
    __tablename__ = "interview_slots"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="dates"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    published_by: Mapped[uuid.UUID] = mapped_column(fk("users.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(150))
    is_published: Mapped[bool] = mapped_column(server_default=text("false"))


class Appointment(Timestamped, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("result IS NULL OR decided_by IS NOT NULL", name="decision_author"),
        # At most one accepted appointment per slot; declined ones stay recorded.
        Index(
            "uq_appointments_one_accepted_per_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status IN ('accepted', 'done')"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    slot_id: Mapped[uuid.UUID] = mapped_column(fk("interview_slots.id"), index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(fk("applications.id"), index=True)
    status: Mapped[str] = mapped_column(appointment_status, server_default="proposed")
    result: Mapped[str | None] = mapped_column(interview_result)
    observations: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(fk("users.id"), index=True)


# Communication and audit trail
class MessageTemplate(Timestamped, Base):
    __tablename__ = "message_templates"
    __table_args__ = (
        CheckConstraint("kind <> 'email' OR subject IS NOT NULL", name="email_subject"),
        CheckConstraint("(approved_by IS NULL) = (approved_at IS NULL)", name="approval"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(50), unique=True)
    kind: Mapped[str] = mapped_column(template_kind)
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(fk("users.id"), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Timestamped, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("follow_up_number BETWEEN 1 AND 3", name="follow_up_range"),
        # Filled only for a follow-up (RM-08).
        CheckConstraint(
            "(type = 'follow_up') = (follow_up_number IS NOT NULL)", name="follow_up_number"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(fk("candidates.id"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(fk("applications.id"), index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(fk("message_templates.id"), index=True)
    type: Mapped[str] = mapped_column(notification_type)
    follow_up_number: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(delivery_status, server_default="queued")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Timestamped, Base):
    """Append-only (RM-10): smartcampus_app has no UPDATE / DELETE on this table."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("actor_type <> 'human' OR actor_user_id IS NOT NULL", name="human_actor"),
        CheckConstraint("actor_type <> 'agent' OR agent_name IS NOT NULL", name="agent_actor"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID]
    action: Mapped[str] = mapped_column(String(50))
    actor_type: Mapped[str] = mapped_column(actor_type)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(fk("users.id"), index=True)
    agent_name: Mapped[str | None] = mapped_column(String(50))
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[Any | None] = mapped_column(JSONB)
