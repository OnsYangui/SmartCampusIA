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
    ProgramFee,
    ProgramPathway,
    ProgramSpecialty,
    Quiz,
    QuizQuestion,
    Recommendation,
    StateTransition,
    Subject,
    User,
)

NAMESPACE = uuid.UUID("5c1e5a4e-0f6b-4c2a-9a51-2e1d0b7a6f10")

# Not a valid Argon2 hash, so no password can ever match: demo accounts cannot log in until SA-28
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
        "Ingénieur en génie informatique",
        "ingenieur",
        "Génie informatique",
        3,
        "DÉMO FICTIVE — Cycle préparatoire ou diplôme équivalent ; admission sur dossier.",
    ),
    (
        "ISB",
        "ISB-LIC-GEST",
        "Licence nationale en gestion",
        "licence",
        "Gestion",
        3,
        "DÉMO FICTIVE — Baccalauréat ou diplôme équivalent ; admission sur dossier.",
    ),
]


# Official admission conditions, checked on the sources below (SA-21). IIT publishes its fees as
# indicative and without academic year, and ISB publishes none, so no official fee is recorded.
IIT_ADMISSION_CRITERIA = "https://iit.tn/wp-content/uploads/2026/10/Criteres_d_admission.pdf"
OFFICIAL_ADMISSION = {
    "IIT-PREPA": {
        "admission_bac_sections": [
            "Mathématiques",
            "Sciences expérimentales",
            "Sciences de l'informatique",
            "Sciences techniques",
        ],
        "prerequisites": "Baccalauréat scientifique : mathématiques, sciences expérimentales, "
        "informatique ou technique.",
        "admission_source_url": "https://iit.tn/filieres-ingenieur/cycle-preparatoire/",
    },
    "IIT-LIC-INFO": {
        "admission_bac_sections": [
            "Mathématiques",
            "Sciences expérimentales",
            "Sciences de l'informatique",
            "Économie et gestion",
            "Sciences techniques",
        ],
        "prerequisites": "Baccalauréat : mathématiques, sciences, informatique, économie et "
        "gestion ou technique (Licence en informatique, Génie logiciel et systèmes intelligents).",
        "admission_source_url": "https://iit.tn/genie-logiciel-systemes-intelligents/",
    },
    "IIT-ING-GL": {
        "admission_bac_sections": None,
        "prerequisites": "Critères d'admission IIT DC-SC-17 (rév. 00 du 17/06/2025), Génie "
        "informatique : diplôme du cycle préparatoire (MP, PC ou PT), ou licence dans l'une des "
        "spécialités suivantes : sciences de l'information, ingénierie des systèmes "
        "d'information, technologies de l'information, automatisation et informatique "
        "industrielle, systèmes automatisés et réseaux industriels, ingénierie de l'information, "
        "informatique de gestion, mathématiques, mathématiques appliquées, sciences et "
        "technologies de l'information et de la communication, électronique et électrotechnique, "
        "informatique de précision et appareils mobiles, informatique et multimédia, ingénierie "
        "logicielle et systèmes d'information, ingénierie des réseaux et des systèmes, systèmes "
        "mobiles et Internet des objets, développement des systèmes d'information, systèmes "
        "portables et mobiles, réseaux et services informatiques, multimédia et développement "
        "web, intelligence d'affaires, services électroniques dans le monde des affaires, "
        "systèmes d'information dans le monde des affaires, mathématiques et informatique.",
        "admission_source_url": IIT_ADMISSION_CRITERIA,
    },
    "ISB-LIC-GEST": {
        "admission_bac_sections": None,
        "prerequisites": "Accessible aux titulaires du baccalauréat.",
        "admission_source_url": "https://isb.tn/lng/",
    },
}
# Names used before the official program pages were checked.
PROVISIONAL_NAMES = {
    "IIT-ING-GL": (
        "Ingénieur en génie logiciel",
        "Ingénieur en génie informatique, parcours génie logiciel et informatique décisionnelle",
    ),
    "ISB-LIC-GEST": ("Licence en gestion",),
}
OFFICIAL_ADMISSION_CHECKED_ON = date(2026, 11, 14)

# Tracks published on iit.tn/filieres-ingenieur/genie-informatique-2/ and isb.tn/lng/.
OFFICIAL_SPECIALTIES = {
    "IIT-ING-GL": [
        (
            "GLID",
            "Génie logiciel et informatique décisionnelle",
            "Conception et développement de logiciels, architecture logicielle, gestion des "
            "données, informatique décisionnelle et systèmes d'aide à la décision.",
        ),
        (
            "ARSI",
            "Administration réseau et sécurité informatique",
            "Réseaux informatiques, administration des systèmes, infrastructures Cloud, "
            "cybersécurité et protection des systèmes d'information.",
        ),
        (
            "SDIA",
            "Science des données et intelligence artificielle",
            "Analyse des données, apprentissage automatique, apprentissage profond et "
            "développement de solutions intelligentes.",
        ),
    ],
    "ISB-LIC-GEST": [
        ("COMPTA", "Comptabilité", "Dès la deuxième année."),
        ("FIN", "Finance", "En troisième année."),
        ("MKT", "Marketing", "En troisième année."),
        ("MGT", "Management", "En troisième année."),
        ("GRH", "Gestion des ressources humaines", "En troisième année."),
    ],
}
# First-year common core of isb.tn/lng/; the page does not say reliably which semester.
ISB_GESTION_FIRST_YEAR = [
    "Principes de Gestion 1",
    "Comptabilité Financière I",
    "Microéconomie",
    "Mathématique 1",
    "Introduction au Droit",
    "Mathématiques Financières",
    "Etudier à l'université",
    "Français Professionnel 1",
    "Digital Skills 1",
    "Principe de Gestion 2",
    "Comptabilité Financière II",
    "Mathématique 2",
    "Statistique Descriptive et Calculs de Probabilité",
    "Macroéconomie",
    "Droit des Sociétés Commerciales",
    "Anglais 1",
    "Français Professionnel 2",
    "Apprendre à apprendre",
]


def record_official_admission(conn: Connection) -> None:
    """Replaces provisional names and conditions; a source recorded since is never overwritten."""
    programs = Program.__table__
    for _, code, name, _, field, _, _ in PROGRAMS:
        if code in PROVISIONAL_NAMES:
            conn.execute(
                update(programs)
                .where(programs.c.id == uid("program", code))
                .where(programs.c.name.in_(PROVISIONAL_NAMES[code]))
                .values(name=name, field=field)
            )
    for code, conditions in OFFICIAL_ADMISSION.items():
        conn.execute(
            update(programs)
            .where(programs.c.id == uid("program", code))
            .where(programs.c.admission_source_url.is_(None))
            .values(
                **conditions,
                admission_verified_on=OFFICIAL_ADMISSION_CHECKED_ON,
                admission_is_demo=False,
                admission_status="published",
                admission_valid_from=OFFICIAL_ADMISSION_CHECKED_ON,
            )
        )
    insert_if_missing(
        conn,
        ProgramSpecialty,
        *(
            {
                "id": uid("specialty", code, specialty),
                "program_id": uid("program", code),
                "code": specialty,
                "name": name,
                "description": description,
            }
            for code, specialties in OFFICIAL_SPECIALTIES.items()
            for specialty, name, description in specialties
        ),
    )
    insert_if_missing(
        conn,
        Subject,
        *(
            {
                "id": uid("subject", "ISB-LIC-GEST", name),
                "program_id": uid("program", "ISB-LIC-GEST"),
                "name": name,
                "study_year": 1,
            }
            for name in ISB_GESTION_FIRST_YEAR
        ),
    )


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
                "admission_is_demo": True,
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
    conn.execute(
        update(Program.__table__)
        .where(Program.__table__.c.id.in_([uid("program", row[1]) for row in PROGRAMS]))
        .where(Program.__table__.c.admission_source_url.is_(None))
        .where(Program.__table__.c.prerequisites.startswith("DÉMO FICTIVE"))
        .values(admission_is_demo=True)
    )
    record_official_admission(conn)
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
# Fictional amounts in TND: official fees come only from verified documents (SA-21).
DEMO_ANNUAL_FEES = {"prepa": 6500, "licence": 5800, "ingenieur": 7900}
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
        ProgramFee,
        *(
            {
                "id": uid("fee", code, "2026-2027"),
                "program_id": uid("program", code),
                "academic_year": "2026-2027",
                "label": "DÉMO FICTIVE — Frais de scolarité annuels",
                "amount": DEMO_ANNUAL_FEES[kind],
                "is_demo": True,
            }
            for _, code, _, kind, _, _, _ in PROGRAMS
        ),
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
