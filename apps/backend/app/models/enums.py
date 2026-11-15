"""PostgreSQL enumerated types of SA-12 to SA-14, created by the migration before the tables."""

from sqlalchemy import Enum


def _enum(name: str, *values: str) -> Enum:
    return Enum(*values, name=name, create_type=False)


# SA-12
program_type = _enum("program_type", "licence", "prepa", "ingenieur", "autre")
campaign_status = _enum("campaign_status", "draft", "open", "closed")

# SA-13 — states keep the SA-3 names
user_role = _enum(
    "user_role", "candidate", "academic_manager", "interview_manager", "management", "admin"
)
candidate_status = _enum("candidate_status", "VISITEUR", "EN_PROFILAGE", "ORIENTE", "ABANDONNE")
application_status = _enum(
    "application_status",
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
)
recommendation_status = _enum("recommendation_status", "proposed", "validated", "adjusted")
appointment_status = _enum(
    "appointment_status", "proposed", "accepted", "declined", "cancelled", "done"
)
interview_result = _enum("interview_result", "admitted", "refused", "more_info")
message_sender = _enum("message_sender", "candidate", "assistant")
actor_type = _enum("actor_type", "human", "agent", "system")
template_kind = _enum("template_kind", "email", "quiz")
notification_type = _enum(
    "notification_type", "confirmation", "reminder", "follow_up", "invitation"
)
delivery_status = _enum("delivery_status", "queued", "sent", "failed")

# SA-14
document_source = _enum("document_source", "pdf", "web_page", "faq")
document_status = _enum("document_status", "active", "archived")
sync_trigger = _enum("sync_trigger", "upload", "update", "scheduled", "model_change")
sync_status = _enum("sync_status", "pending", "running", "succeeded", "failed")

ALL_ENUMS = [
    program_type,
    campaign_status,
    user_role,
    candidate_status,
    application_status,
    recommendation_status,
    appointment_status,
    interview_result,
    message_sender,
    actor_type,
    template_kind,
    notification_type,
    delivery_status,
    document_source,
    document_status,
    sync_trigger,
    sync_status,
]
