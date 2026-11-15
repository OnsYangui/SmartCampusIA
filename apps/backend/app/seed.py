"""SA-18 — Reference data (SA-12 §4) and demonstration data.

Replayable without duplicates: every row has a deterministic id (uuid5 of a stable name) and every
insert is ON CONFLICT DO NOTHING. No real person; no document fragment (created later by the
synchronisation, SA-14, with real embeddings).

    uv run python -m app.seed                   # reference + demonstration
    uv run python -m app.seed --reference-only  # reference only
"""

import argparse
import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Table, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.models import (
    AdmissionCampaign,
    Application,
    Appointment,
    Candidate,
    Consent,
    Institution,
    InterviewSlot,
    MessageTemplate,
    Profile,
    Program,
    ProgramPathway,
    Quiz,
    QuizQuestion,
    Recommendation,
    StateTransition,
    User,
)

NAMESPACE = uuid.UUID("5c1e5a4e-0f6b-4c2a-9a51-2e1d0b7a6f10")

# Not a valid Argon2 hash, so no password can ever match: demo accounts cannot log in until SA-5
# provides a demo password from the environment. The previous hash was published and is revoked.
DEMO_PASSWORD_HASH = "!disabled:demo-login-not-configured"
CONSENT_TEXT_VERSION = "2026-1"
T0 = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)


def uid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, ":".join(parts))


def ensure_seed_allowed(settings: Settings, *, allow_test_database: bool) -> None:
    if settings.environment == "development":
        return

    database = make_url(settings.database_url).database or ""
    if allow_test_database and database.endswith("_test"):
        return
    if allow_test_database:
        raise RuntimeError("--allow-test-database requires a database name ending in '_test'")
    raise RuntimeError("Seeding is restricted to the development environment")


def insert_if_missing(conn: Connection, model: type, *rows: dict[str, Any]) -> None:
    table: Table = model.__table__
    # One statement per row: a multi-row INSERT keeps only the first row's columns.
    for row in rows:
        conn.execute(insert(table).values(row).on_conflict_do_nothing())


# Reference data (SA-12 §4).
# Provisional catalogue; replace it after academic managers confirm the official IIT/ISB lists.
PROGRAMS = [
    (
        "IIT",
        "IIT-PREPA",
        "Cycle préparatoire intégré",
        "prepa",
        "Mathématiques et physique",
        2,
        "DÉMO FICTIVE — Baccalauréat scientifique ou technique ; admission sur dossier.",
    ),
    (
        "IIT",
        "IIT-LIC-INFO",
        "Licence en informatique",
        "licence",
        "Informatique",
        3,
        "DÉMO FICTIVE — Baccalauréat ou diplôme équivalent ; admission sur dossier.",
    ),
    (
        "IIT",
        "IIT-ING-GL",
        "Ingénieur en génie logiciel",
        "ingenieur",
        "Génie logiciel",
        3,
        "DÉMO FICTIVE — Cycle préparatoire ou diplôme équivalent ; admission sur dossier.",
    ),
    (
        "ISB",
        "ISB-LIC-GEST",
        "Licence en gestion",
        "licence",
        "Gestion",
        3,
        "DÉMO FICTIVE — Baccalauréat ou diplôme équivalent ; admission sur dossier.",
    ),
]


def seed_reference(conn: Connection) -> None:
    insert_if_missing(
        conn,
        Institution,
        {
            "id": uid("institution", "IIT"),
            "code": "IIT",
            "name": "Institut International de Technologie",
        },
        # Full name of the ISB to confirm with the academic managers (SA-12 §4).
        {"id": uid("institution", "ISB"), "code": "ISB", "name": "ISB"},
    )
    insert_if_missing(
        conn,
        AdmissionCampaign,
        *(
            {
                "id": uid("campaign", code, "2026-2027"),
                "institution_id": uid("institution", code),
                "name": f"Admissions {code} 2026-2027",
                "academic_year": "2026-2027",
                "starts_on": date(2026, 6, 1),
                "ends_on": date(2026, 9, 30),
                "status": "draft",
            }
            for code in ("IIT", "ISB")
        ),
    )
    insert_if_missing(
        conn,
        Program,
        *(
            {
                "id": uid("program", code),
                "institution_id": uid("institution", inst),
                "code": code,
                "name": name,
                "type": kind,
                "field": field,
                "duration_years": years,
                "prerequisites": prerequisites,
            }
            for inst, code, name, kind, field, years, prerequisites in PROGRAMS
        ),
    )
    for _, code, _, _, _, _, prerequisites in PROGRAMS:
        conn.execute(
            update(Program.__table__)
            .where(Program.__table__.c.id == uid("program", code))
            .where(Program.__table__.c.prerequisites.is_(None))
            .values(prerequisites=prerequisites)
        )
    insert_if_missing(
        conn,
        ProgramPathway,
        {
            "from_program_id": uid("program", "IIT-PREPA"),
            "to_program_id": uid("program", "IIT-ING-GL"),
            "conditions": "Validation des deux années du cycle préparatoire",
        },
    )


# Demonstration data.
STAFF = [
    # role, email, institution
    ("academic_manager", "resp.academique.iit@example.com", "IIT"),
    ("interview_manager", "resp.entretien.iit@example.com", "IIT"),
    ("management", "direction@example.com", None),
    ("admin", "admin@example.com", None),
]

# Candidate path through the SA-3 lifecycle; each demo candidate stops at one state.
PATH = [
    "VISITEUR",
    "EN_PROFILAGE",
    "ORIENTE",
    "PREINSCRIT",
    "QCM_TERMINE",
    "ORIENTATION_VALIDEE",
    "ENTRETIEN_PLANIFIE",
    "ENTRETIEN_REALISE",
]
FINAL_STEPS = {
    "COMPLEMENT_DEMANDE": ["COMPLEMENT_DEMANDE"],
    "ADMIS": ["ADMIS"],
    "REFUSE": ["REFUSE"],
    "INSCRIT": ["ADMIS", "INSCRIT"],
}
# (key, first name, target state); last names are all "Exemple": fictitious people.
CANDIDATES = [
    ("c01", "Amine", "VISITEUR"),
    ("c02", "Salma", "EN_PROFILAGE"),
    ("c03", "Karim", "ORIENTE"),
    ("c04", "Nour", "PREINSCRIT"),
    ("c05", "Youssef", "QCM_TERMINE"),
    ("c06", "Ines", "ORIENTATION_VALIDEE"),
    ("c07", "Mehdi", "ENTRETIEN_PLANIFIE"),
    ("c08", "Rania", "ENTRETIEN_REALISE"),
    ("c09", "Omar", "COMPLEMENT_DEMANDE"),
    ("c10", "Lina", "ADMIS"),
    ("c11", "Walid", "REFUSE"),
    ("c12", "Sarra", "INSCRIT"),
    ("c13", "Hamza", "ABANDONNE"),
]
CANDIDATE_STATES = {"VISITEUR", "EN_PROFILAGE", "ORIENTE"}
TEMPLATES = [
    ("confirmation_preinscription", "email", "Votre préinscription est enregistrée"),
    ("invitation_entretien", "email", "Invitation à votre entretien"),
    ("rappel_entretien", "email", "Rappel : votre entretien approche"),
    ("relance_1", "email", "Votre parcours SmartCampus vous attend"),
    ("relance_2", "email", "Avez-vous des questions sur votre orientation ?"),
    ("relance_3", "email", "Dernier rappel avant transmission à un conseiller"),
    ("qcm_licence_informatique", "quiz", None),
]


def states_of(target: str) -> list[str]:
    """States crossed by a candidate who stops at `target`."""
    if target == "ABANDONNE":  # withdraws after pre-registration
        return [*PATH[:4], "ABANDONNE"]
    if target in FINAL_STEPS:
        return PATH + FINAL_STEPS[target]
    return PATH[: PATH.index(target) + 1]


def actor_of(state: str, key: str) -> dict[str, Any]:
    """Who triggers each state (SA-3 §6)."""
    if state == "VISITEUR":
        return {"actor_type": "system"}
    if state in ("EN_PROFILAGE", "ORIENTE"):
        return {"actor_type": "agent"}
    if state in ("PREINSCRIT", "QCM_TERMINE", "ABANDONNE"):
        return {"actor_type": "human", "actor_user_id": uid("user", key)}
    if state == "ORIENTATION_VALIDEE":
        return {"actor_type": "human", "actor_user_id": uid("user", "academic_manager")}
    return {"actor_type": "human", "actor_user_id": uid("user", "interview_manager")}


def seed_demo(conn: Connection) -> None:
    iit = uid("institution", "IIT")
    program = uid("program", "IIT-LIC-INFO")
    campaign = uid("campaign", "IIT", "2026-2027")
    # Applications are only created in an open campaign (SA-13); the reference data stays draft.
    conn.execute(
        update(AdmissionCampaign.__table__)
        .where(AdmissionCampaign.__table__.c.id == campaign)
        .values(status="open")
    )

    insert_if_missing(
        conn,
        User,
        *(
            {
                "id": uid("user", role),
                "email": email,
                "password_hash": DEMO_PASSWORD_HASH,
                "role": role,
                "institution_id": uid("institution", inst) if inst else None,
            }
            for role, email, inst in STAFF
        ),
    )
    admin = uid("user", "admin")
    insert_if_missing(
        conn,
        MessageTemplate,
        *(
            {
                "id": uid("template", code),
                "code": code,
                "kind": kind,
                "subject": subject,
                "body": "Bonjour {first_name},\n\n… (texte approuvé par l'administrateur)",
                "approved_by": admin,
                "approved_at": T0 - timedelta(days=20),
            }
            for code, kind, subject in TEMPLATES
        ),
    )
    insert_if_missing(
        conn,
        InterviewSlot,
        *(
            {
                "id": uid("slot", str(n)),
                "published_by": uid("user", "interview_manager"),
                "starts_at": T0 + timedelta(days=14, hours=n),
                "ends_at": T0 + timedelta(days=14, hours=n, minutes=30),
                "location": "IIT — salle B12",
                "is_published": True,
            }
            for n in range(8)
        ),
    )

    for slot_number, (key, first_name, target) in enumerate(CANDIDATES):
        _seed_candidate(conn, key, first_name, target, slot_number, iit, program, campaign)


def _seed_candidate(
    conn: Connection,
    key: str,
    first_name: str,
    target: str,
    slot_number: int,
    institution: uuid.UUID,
    program: uuid.UUID,
    campaign: uuid.UUID,
) -> None:
    states = states_of(target)
    has_application = "PREINSCRIT" in states
    candidate = uid("candidate", key)

    if has_application:
        insert_if_missing(
            conn,
            User,
            {
                "id": uid("user", key),
                "email": f"candidat.{key}@example.com",
                "password_hash": DEMO_PASSWORD_HASH,
                "role": "candidate",
            },
        )
    insert_if_missing(
        conn,
        Candidate,
        {
            "id": candidate,
            "user_id": uid("user", key) if has_application else None,
            "session_id_hash": hashlib.sha256(f"demo-session-{key}".encode()).hexdigest(),
            "status": target if target in CANDIDATE_STATES else "ORIENTE",
            "first_name": first_name if has_application else None,
            "last_name": "Exemple" if has_application else None,
            "phone": f"+216 00 000 {slot_number:03d}" if has_application else None,
            "preferred_language": "fr",
        },
    )
    if "EN_PROFILAGE" in states:
        insert_if_missing(
            conn,
            Profile,
            {
                "id": uid("profile", key),
                "candidate_id": candidate,
                "bac_section": "Mathématiques",
                "bac_average": 13.5,
                "preferred_subjects": ["mathématiques", "informatique"],
                "interests": ["développement logiciel"],
                "career_goals": "Devenir développeur",
            },
        )
    if "ORIENTE" in states:
        validated = "ORIENTATION_VALIDEE" in states
        insert_if_missing(
            conn,
            Recommendation,
            {
                "id": uid("recommendation", key),
                "candidate_id": candidate,
                "program_id": program,
                "score": 82,
                "justification": "Profil scientifique, intérêt pour le développement logiciel.",
                "status": "validated" if validated else "proposed",
                "reviewed_by": uid("user", "academic_manager") if validated else None,
                "reviewed_at": T0 + timedelta(days=5) if validated else None,
            },
        )

    application = uid("application", key)
    if has_application:
        consent = uid("consent", key)
        insert_if_missing(
            conn,
            Consent,
            {
                "id": consent,
                "candidate_id": candidate,
                "text_version": CONSENT_TEXT_VERSION,
                "accepted_at": T0,
            },
        )
        insert_if_missing(
            conn,
            Application,
            {
                "id": application,
                "candidate_id": candidate,
                "program_id": program,
                "campaign_id": campaign,
                "consent_id": consent,
                "status": states[-1],
            },
        )
    if "QCM_TERMINE" in states:
        quiz = uid("quiz", key)
        insert_if_missing(
            conn,
            Quiz,
            {
                "id": quiz,
                "application_id": application,
                "program_id": program,
                "template_id": uid("template", "qcm_licence_informatique"),
                "score": 75,
                "summary": "Bonnes bases en algorithmique ; à approfondir : motivation.",
                "submitted_at": T0 + timedelta(days=3),
            },
        )
        insert_if_missing(
            conn,
            QuizQuestion,
            *(
                {
                    "id": uid("question", key, str(position)),
                    "quiz_id": quiz,
                    "position": position,
                    "statement": statement,
                    "choices": choices,
                    "correct_choice": 0,
                    "candidate_choice": 0,
                }
                for position, statement, choices in (
                    (1, "Que vaut 2 puissance 10 ?", ["1024", "512", "2048"]),
                    (2, "Quel langage est compilé ?", ["C", "HTML", "CSS"]),
                )
            ),
        )
    if "ENTRETIEN_PLANIFIE" in states:
        result = {
            "ADMIS": "admitted",
            "INSCRIT": "admitted",
            "REFUSE": "refused",
            "COMPLEMENT_DEMANDE": "more_info",
        }.get(target)
        done = "ENTRETIEN_REALISE" in states
        insert_if_missing(
            conn,
            Appointment,
            {
                "id": uid("appointment", key),
                "slot_id": uid("slot", str(slot_number % 8)),
                "application_id": application,
                "status": "done" if done else "accepted",
                "result": result,
                "observations": "Candidat motivé." if done else None,
                "decided_by": uid("user", "interview_manager") if result else None,
            },
        )

    insert_if_missing(
        conn,
        StateTransition,
        *(
            {
                "id": uid("transition", key, str(n)),
                "candidate_id": candidate,
                "application_id": application if has_application and n >= 3 else None,
                "from_state": states[n - 1] if n else None,
                "to_state": state,
                **actor_of(state, key),
                "reason": "Données de démonstration",
            }
            for n, state in enumerate(states)
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference-only", action="store_true")
    parser.add_argument(
        "--allow-test-database",
        action="store_true",
        help="allow a non-development target only when its database name ends in '_test'",
    )
    args = parser.parse_args()

    from app.core.db import engine

    ensure_seed_allowed(get_settings(), allow_test_database=args.allow_test_database)
    with engine.begin() as conn:
        seed_reference(conn)
        if not args.reference_only:
            seed_demo(conn)
    print("Données insérées (rejouable sans doublons).")


if __name__ == "__main__":
    main()
