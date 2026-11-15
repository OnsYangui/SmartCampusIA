"""SQLAlchemy models of SA-12, SA-13 and SA-14 (24 tables)."""

from app.models.base import Base
from app.models.catalog import AdmissionCampaign, Institution, Program, ProgramPathway
from app.models.documents import Document, DocumentFragment, DocumentSync
from app.models.people import (
    Application,
    Appointment,
    AuditLog,
    Candidate,
    Consent,
    Conversation,
    InterviewSlot,
    Message,
    MessageCitation,
    MessageTemplate,
    Notification,
    Profile,
    Quiz,
    QuizQuestion,
    Recommendation,
    StateTransition,
    User,
)

__all__ = [
    "AdmissionCampaign",
    "Application",
    "Appointment",
    "AuditLog",
    "Base",
    "Candidate",
    "Consent",
    "Conversation",
    "Document",
    "DocumentFragment",
    "DocumentSync",
    "Institution",
    "InterviewSlot",
    "Message",
    "MessageCitation",
    "MessageTemplate",
    "Notification",
    "Profile",
    "Program",
    "ProgramPathway",
    "Quiz",
    "QuizQuestion",
    "Recommendation",
    "StateTransition",
    "User",
]
