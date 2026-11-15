"""One test per rule the database guarantees (SA-12, SA-13, SA-14), run as smartcampus_app."""

import uuid
from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

EMBEDDING = "[" + ",".join(["0.1"] * 1024) + "]"


def insert(conn: Connection, table: str, **cols: Any) -> uuid.UUID:
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return conn.execute(
        text(f"INSERT INTO {table} ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def rejects(conn: Connection, sql: str, match: str, **params: Any) -> None:
    """The statement must fail, with `match` in the error (constraint name or trigger message)."""
    savepoint = conn.begin_nested()
    with pytest.raises(DBAPIError, match=match):
        conn.execute(text(sql), params)
    savepoint.rollback()


@pytest.fixture
def db(conn: Connection) -> dict[str, uuid.UUID]:
    """A minimal coherent dataset: one institution, programs, campaign, staff, candidate."""
    ids: dict[str, uuid.UUID] = {}
    ids["inst"] = insert(conn, "institutions", code="TST", name="Institut de test")
    for key, code in (("prog", "TST-LIC"), ("prog2", "TST-ING")):
        ids[key] = insert(
            conn,
            "programs",
            institution_id=ids["inst"],
            code=code,
            name=code,
            type="licence",
            duration_years=3,
        )
    ids["campaign"] = insert(
        conn,
        "admission_campaigns",
        institution_id=ids["inst"],
        name="Test",
        academic_year="2026-2027",
        starts_on="2026-06-01",
        ends_on="2026-09-30",
        status="open",
    )
    ids["manager"] = insert(
        conn,
        "users",
        email="resp@test.tn",
        password_hash="x",
        role="interview_manager",
        institution_id=ids["inst"],
    )
    ids["admin"] = insert(conn, "users", email="admin@test.tn", password_hash="x", role="admin")
    ids["candidate"] = insert(
        conn, "candidates", session_id_hash="a" * 64, first_name="Test", last_name="Candidat"
    )
    ids["consent"] = insert(
        conn,
        "consents",
        candidate_id=ids["candidate"],
        text_version="v1",
        accepted_at="2026-06-02",
    )
    return ids


def new_application(conn: Connection, db: dict[str, uuid.UUID]) -> uuid.UUID:
    return insert(
        conn,
        "applications",
        candidate_id=db["candidate"],
        program_id=db["prog"],
        campaign_id=db["campaign"],
        consent_id=db["consent"],
    )


def new_document(conn: Connection, db: dict[str, uuid.UUID], uri: str = "doc.pdf") -> uuid.UUID:
    return insert(
        conn,
        "documents",
        institution_id=db["inst"],
        title="Brochure",
        source_type="pdf",
        source_uri=uri,
        content_hash="c" * 64,
        uploaded_by=db["admin"],
    )


# SA-12
def test_program_duration_between_1_and_5(conn, db) -> None:
    rejects(
        conn,
        "UPDATE programs SET duration_years = 6 WHERE id = :id",
        "ck_programs_duration_years",
        id=db["prog"],
    )


def test_min_bac_average_between_0_and_20(conn, db) -> None:
    rejects(
        conn,
        "UPDATE programs SET min_bac_average = 21 WHERE id = :id",
        "ck_programs_min_bac_average",
        id=db["prog"],
    )


def test_pathway_cannot_point_to_its_own_program(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO program_pathways (from_program_id, to_program_id) VALUES (:p, :p)",
        "ck_program_pathways_distinct_programs",
        p=db["prog"],
    )


def test_campaign_academic_year_format(conn, db) -> None:
    rejects(
        conn,
        "UPDATE admission_campaigns SET academic_year = '2026/2027' WHERE id = :id",
        "ck_admission_campaigns_academic_year_format",
        id=db["campaign"],
    )


def test_campaign_ends_after_it_starts(conn, db) -> None:
    rejects(
        conn,
        "UPDATE admission_campaigns SET ends_on = starts_on WHERE id = :id",
        "ck_admission_campaigns_dates",
        id=db["campaign"],
    )


def test_one_open_campaign_per_institution(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO admission_campaigns (institution_id, name, academic_year, starts_on, ends_on,"
        " status) VALUES (:i, 'Bis', '2026-2027', '2026-06-01', '2026-09-30', 'open')",
        "uq_admission_campaigns_one_open",
        i=db["inst"],
    )


def test_app_role_cannot_physically_delete_programs(conn, db) -> None:
    rejects(
        conn,
        "DELETE FROM programs WHERE id = :id",
        "permission denied",
        id=db["prog2"],
    )


# SA-13 — Accounts and candidates
def test_manager_roles_require_an_institution_and_others_have_none(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO users (email, password_hash, role) VALUES ('m@t.tn', 'x', 'academic_manager')",
        "ck_users_institution_scope",
    )
    rejects(
        conn,
        "UPDATE users SET institution_id = :i WHERE id = :id",
        "ck_users_institution_scope",
        i=db["inst"],
        id=db["admin"],
    )


def test_candidate_language_is_fr_ar_tn_or_arabizi(conn, db) -> None:
    rejects(
        conn,
        "UPDATE candidates SET preferred_language = 'en' WHERE id = :id",
        "ck_candidates_preferred_language",
        id=db["candidate"],
    )


def test_session_hash_is_unique(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO candidates (session_id_hash) VALUES (:h)",
        "uq_candidates_session_id_hash",
        h="a" * 64,
    )


def test_profile_bac_average_between_0_and_20(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO profiles (candidate_id, bac_average) VALUES (:c, 20.5)",
        "ck_profiles_bac_average",
        c=db["candidate"],
    )


# SA-13 — Applications
def test_application_rejected_with_a_withdrawn_consent(conn, db) -> None:
    conn.execute(
        text("UPDATE consents SET withdrawn_at = now() WHERE id = :id"), {"id": db["consent"]}
    )
    rejects(
        conn,
        "INSERT INTO applications (candidate_id, program_id, campaign_id, consent_id)"
        " VALUES (:c, :p, :k, :s)",
        "RM-03",
        c=db["candidate"],
        p=db["prog"],
        k=db["campaign"],
        s=db["consent"],
    )


def test_application_rejected_with_another_candidates_consent(conn, db) -> None:
    other = insert(conn, "candidates", session_id_hash="b" * 64, first_name="A", last_name="B")
    rejects(
        conn,
        "INSERT INTO applications (candidate_id, program_id, campaign_id, consent_id)"
        " VALUES (:c, :p, :k, :s)",
        "RM-03",
        c=other,
        p=db["prog"],
        k=db["campaign"],
        s=db["consent"],
    )


def test_application_update_rejects_another_candidates_consent(conn, db) -> None:
    application = new_application(conn, db)
    other = insert(conn, "candidates", session_id_hash="b" * 64, first_name="A", last_name="B")

    rejects(
        conn,
        "UPDATE applications SET candidate_id = :candidate WHERE id = :application",
        "RM-03",
        candidate=other,
        application=application,
    )


def test_application_update_rejects_a_withdrawn_consent(conn, db) -> None:
    application = new_application(conn, db)
    withdrawn = insert(
        conn,
        "consents",
        candidate_id=db["candidate"],
        text_version="v2",
        accepted_at="2026-06-03",
        withdrawn_at="2026-06-04",
    )

    rejects(
        conn,
        "UPDATE applications SET consent_id = :consent WHERE id = :application",
        "RM-03",
        consent=withdrawn,
        application=application,
    )


def test_application_requires_first_and_last_name(conn, db) -> None:
    conn.execute(
        text("UPDATE candidates SET last_name = NULL WHERE id = :id"), {"id": db["candidate"]}
    )
    rejects(
        conn,
        "INSERT INTO applications (candidate_id, program_id, campaign_id, consent_id)"
        " VALUES (:c, :p, :k, :s)",
        "Nom et prénom",
        c=db["candidate"],
        p=db["prog"],
        k=db["campaign"],
        s=db["consent"],
    )


def test_names_kept_while_application_and_consent_exist_then_erasable(conn, db) -> None:
    new_application(conn, db)
    rejects(
        conn,
        "UPDATE candidates SET first_name = NULL WHERE id = :id",
        "Nom et prénom",
        id=db["candidate"],
    )
    # After the consent is withdrawn (RM-13), the identity can be erased.
    conn.execute(
        text("UPDATE consents SET withdrawn_at = now() WHERE id = :id"), {"id": db["consent"]}
    )
    conn.execute(
        text("UPDATE candidates SET first_name = NULL, last_name = NULL WHERE id = :id"),
        {"id": db["candidate"]},
    )


def test_one_application_per_candidate_and_campaign(conn, db) -> None:
    new_application(conn, db)
    rejects(
        conn,
        "INSERT INTO applications (candidate_id, program_id, campaign_id, consent_id)"
        " VALUES (:c, :p, :k, :s)",
        "uq_applications_candidate_id_campaign_id",
        c=db["candidate"],
        p=db["prog2"],
        k=db["campaign"],
        s=db["consent"],
    )


def test_reviewed_recommendation_requires_a_reviewer_and_a_date(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO recommendations (candidate_id, program_id, justification, status)"
        " VALUES (:c, :p, 'x', 'validated')",
        "ck_recommendations_reviewer",
        c=db["candidate"],
        p=db["prog"],
    )
    rejects(
        conn,
        "INSERT INTO recommendations (candidate_id, program_id, justification, status,"
        " reviewed_by) VALUES (:c, :p, 'x', 'validated', :u)",
        "ck_recommendations_reviewed_at",
        c=db["candidate"],
        p=db["prog"],
        u=db["manager"],
    )


def test_recommendation_score_between_0_and_100(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO recommendations (candidate_id, program_id, justification, score)"
        " VALUES (:c, :p, 'x', 101)",
        "ck_recommendations_score",
        c=db["candidate"],
        p=db["prog"],
    )


# SA-13 — Conversations
def test_transcription_flag_only_for_voice_messages(conn, db) -> None:
    conv = insert(conn, "conversations", candidate_id=db["candidate"])
    rejects(
        conn,
        "INSERT INTO messages (conversation_id, sender, content, audio_path)"
        " VALUES (:c, 'candidate', 'x', 'a.webm')",
        "ck_messages_voice_transcription",
        c=conv,
    )
    rejects(
        conn,
        "INSERT INTO messages (conversation_id, sender, content, transcription_reliable)"
        " VALUES (:c, 'candidate', 'x', true)",
        "ck_messages_voice_transcription",
        c=conv,
    )


def test_only_assistant_messages_have_citations(conn, db) -> None:
    conv = insert(conn, "conversations", candidate_id=db["candidate"])
    msg = insert(conn, "messages", conversation_id=conv, sender="candidate", content="Bonjour")
    doc = new_document(conn, db)
    frag = insert(
        conn,
        "document_fragments",
        document_id=doc,
        institution_id=db["inst"],
        document_version=1,
        position=1,
        content="texte",
        embedding=EMBEDDING,
    )
    rejects(
        conn,
        "INSERT INTO message_citations (message_id, fragment_id) VALUES (:m, :f)",
        "RM-01",
        m=msg,
        f=frag,
    )


def test_deleting_a_conversation_deletes_its_messages_and_citations(conn, db) -> None:
    conv = insert(conn, "conversations", candidate_id=db["candidate"])
    msg = insert(conn, "messages", conversation_id=conv, sender="assistant", content="Réponse")
    frag = insert(
        conn,
        "document_fragments",
        document_id=new_document(conn, db),
        institution_id=db["inst"],
        document_version=1,
        position=1,
        content="texte",
        embedding=EMBEDDING,
    )
    conn.execute(
        text("INSERT INTO message_citations (message_id, fragment_id) VALUES (:m, :f)"),
        {"m": msg, "f": frag},
    )
    conn.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": conv})
    left = conn.execute(text("SELECT count(*) FROM messages WHERE id = :id"), {"id": msg}).scalar()
    citations = conn.execute(
        text("SELECT count(*) FROM message_citations WHERE message_id = :id"), {"id": msg}
    ).scalar()
    assert (left, citations) == (0, 0)


# SA-13 — Audit trail
def test_human_actor_requires_a_user_and_agent_requires_a_name(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO state_transitions (candidate_id, to_state, actor_type)"
        " VALUES (:c, 'EN_PROFILAGE', 'human')",
        "ck_state_transitions_human_actor",
        c=db["candidate"],
    )
    rejects(
        conn,
        "INSERT INTO audit_logs (entity_type, entity_id, action, actor_type)"
        " VALUES ('application', :e, 'update', 'human')",
        "ck_audit_logs_human_actor",
        e=db["candidate"],
    )
    rejects(
        conn,
        "INSERT INTO audit_logs (entity_type, entity_id, action, actor_type)"
        " VALUES ('application', :e, 'update', 'agent')",
        "ck_audit_logs_agent_actor",
        e=db["candidate"],
    )


@pytest.mark.parametrize("table", ["audit_logs", "state_transitions"])
@pytest.mark.parametrize(
    "statement", ["UPDATE {table} SET updated_at = now()", "DELETE FROM {table}"]
)
def test_append_only_tables_refuse_update_and_delete(conn, db, table, statement) -> None:
    rejects(conn, statement.format(table=table), "permission denied")


def test_app_role_cannot_physically_delete_candidate_accounts(conn, db) -> None:
    # RM-13: the account is anonymised instead, so the history stays valid.
    account = insert(conn, "users", email="cand@test.tn", password_hash="x", role="candidate")
    conn.execute(
        text("UPDATE candidates SET user_id = :u WHERE id = :c"),
        {"u": account, "c": db["candidate"]},
    )
    rejects(conn, "DELETE FROM users WHERE id = :id", "permission denied", id=account)


def test_deleting_an_anonymous_candidate_removes_its_profile_and_transitions(conn, db) -> None:
    anonymous = insert(conn, "candidates", session_id_hash="d" * 64)
    insert(conn, "profiles", candidate_id=anonymous)
    insert(
        conn, "state_transitions", candidate_id=anonymous, to_state="VISITEUR", actor_type="system"
    )
    conn.execute(text("DELETE FROM candidates WHERE id = :id"), {"id": anonymous})
    left = conn.execute(
        text(
            "SELECT (SELECT count(*) FROM profiles WHERE candidate_id = :id)"
            " + (SELECT count(*) FROM state_transitions WHERE candidate_id = :id)"
        ),
        {"id": anonymous},
    ).scalar()
    assert left == 0


# SA-13 — Quizzes and interviews
def test_quiz_template_must_be_a_quiz_template(conn, db) -> None:
    email = insert(
        conn, "message_templates", code="confirmation", kind="email", subject="S", body="B"
    )
    rejects(
        conn,
        "INSERT INTO quizzes (application_id, program_id, template_id) VALUES (:a, :p, :t)",
        "type quiz",
        a=new_application(conn, db),
        p=db["prog"],
        t=email,
    )


def test_one_quiz_per_program_and_score_between_0_and_100(conn, db) -> None:
    application = new_application(conn, db)
    insert(conn, "quizzes", application_id=application, program_id=db["prog"])
    rejects(
        conn,
        "INSERT INTO quizzes (application_id, program_id) VALUES (:a, :p)",
        "uq_quizzes_application_id_program_id",
        a=application,
        p=db["prog"],
    )
    rejects(
        conn,
        "INSERT INTO quizzes (application_id, program_id, score) VALUES (:a, :p, 120)",
        "ck_quizzes_score",
        a=application,
        p=db["prog2"],
    )


def test_question_position_is_unique_in_a_quiz(conn, db) -> None:
    quiz = insert(conn, "quizzes", application_id=new_application(conn, db), program_id=db["prog"])
    question = {"q": quiz, "c": '["a", "b"]'}
    sql = (
        "INSERT INTO quiz_questions (quiz_id, position, statement, choices, correct_choice)"
        " VALUES (:q, 1, 'Q', CAST(:c AS jsonb), 0)"
    )
    conn.execute(text(sql), question)
    rejects(conn, sql, "uq_quiz_questions_quiz_id_position", **question)


def test_slot_ends_after_it_starts(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO interview_slots (published_by, starts_at, ends_at)"
        " VALUES (:u, '2026-07-01 10:00+01', '2026-07-01 09:00+01')",
        "ck_interview_slots_dates",
        u=db["manager"],
    )


def test_one_accepted_appointment_per_slot(conn, db) -> None:
    slot = insert(
        conn,
        "interview_slots",
        published_by=db["manager"],
        starts_at="2026-07-01 09:00+01",
        ends_at="2026-07-01 09:30+01",
        is_published=True,
    )
    application = new_application(conn, db)
    insert(conn, "appointments", slot_id=slot, application_id=application, status="declined")
    insert(conn, "appointments", slot_id=slot, application_id=application, status="accepted")
    rejects(
        conn,
        "INSERT INTO appointments (slot_id, application_id, status) VALUES (:s, :a, 'accepted')",
        "uq_appointments_one_accepted_per_slot",
        s=slot,
        a=application,
    )


def test_interview_result_requires_its_decider(conn, db) -> None:
    slot = insert(
        conn,
        "interview_slots",
        published_by=db["manager"],
        starts_at="2026-07-01 09:00+01",
        ends_at="2026-07-01 09:30+01",
    )
    rejects(
        conn,
        "INSERT INTO appointments (slot_id, application_id, status, result)"
        " VALUES (:s, :a, 'done', 'admitted')",
        "ck_appointments_decision_author",
        s=slot,
        a=new_application(conn, db),
    )


# SA-13 — Communication
def test_email_template_requires_a_subject_and_approval_has_a_date(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO message_templates (code, kind, body) VALUES ('relance_1', 'email', 'B')",
        "ck_message_templates_email_subject",
    )
    rejects(
        conn,
        "INSERT INTO message_templates (code, kind, subject, body, approved_by)"
        " VALUES ('relance_1', 'email', 'S', 'B', :u)",
        "ck_message_templates_approval",
        u=db["admin"],
    )


def test_follow_up_number_only_for_follow_ups_between_1_and_3(conn, db) -> None:
    template = insert(
        conn, "message_templates", code="relance", kind="email", subject="S", body="B"
    )
    base = (
        "INSERT INTO notifications (candidate_id, template_id, type, follow_up_number)"
        " VALUES (:c, :t, CAST(:type AS notification_type), :n)"
    )
    rejects(
        conn,
        base,
        "ck_notifications_follow_up_number",
        c=db["candidate"],
        t=template,
        type="follow_up",
        n=None,
    )
    rejects(
        conn,
        base,
        "ck_notifications_follow_up_number",
        c=db["candidate"],
        t=template,
        type="reminder",
        n=1,
    )
    rejects(
        conn,
        base,
        "ck_notifications_follow_up_range",
        c=db["candidate"],
        t=template,
        type="follow_up",
        n=4,
    )


# SA-14
def test_document_source_unique_per_institution_and_version_starts_at_0(conn, db) -> None:
    doc = new_document(conn, db)
    version = conn.execute(text("SELECT version FROM documents WHERE id = :id"), {"id": doc})
    assert version.scalar() == 0
    rejects(
        conn,
        "INSERT INTO documents (institution_id, title, source_type, source_uri, content_hash,"
        " uploaded_by) VALUES (:i, 'Bis', 'pdf', 'doc.pdf', :h, :u)",
        "uq_documents_institution_id_source_uri",
        i=db["inst"],
        h="c" * 64,
        u=db["admin"],
    )


def test_app_role_cannot_physically_delete_a_document(conn, db) -> None:
    document = new_document(conn, db)

    rejects(
        conn,
        "DELETE FROM documents WHERE id = :document",
        "permission denied",
        document=document,
    )


def test_fragment_position_unique_and_content_tsv_generated(conn, db) -> None:
    fragment = {
        "d": new_document(conn, db),
        "i": db["inst"],
        "e": EMBEDDING,
    }
    sql = (
        "INSERT INTO document_fragments (document_id, institution_id, document_version, position,"
        " content, embedding) VALUES (:d, :i, 1, 1, 'Licence en informatique', :e) RETURNING id"
    )
    frag = conn.execute(text(sql), fragment).scalar_one()
    tsv = conn.execute(
        text("SELECT content_tsv::text FROM document_fragments WHERE id = :id"), {"id": frag}
    ).scalar()
    assert tsv == "'en':2 'informatique':3 'licence':1"
    rejects(conn, sql, "uq_document_fragments_document_id_document_version_position", **fragment)


def test_embedding_has_1024_dimensions(conn, db) -> None:
    rejects(
        conn,
        "INSERT INTO document_fragments (document_id, institution_id, document_version, position,"
        " content, embedding) VALUES (:d, :i, 1, 1, 'x', '[0.1, 0.2]')",
        "expected 1024 dimensions",
        d=new_document(conn, db),
        i=db["inst"],
    )


def test_one_sync_in_progress_per_document(conn, db) -> None:
    doc = new_document(conn, db)
    sql = (
        "INSERT INTO document_syncs (document_id, document_version, trigger_type, status,"
        " embedding_model) VALUES (:d, 1, 'upload', CAST(:s AS sync_status), 'bge-m3')"
    )
    conn.execute(text(sql), {"d": doc, "s": "pending"})
    rejects(conn, sql, "uq_document_syncs_one_in_progress", d=doc, s="running")


def test_sync_outcome_requires_count_or_error(conn, db) -> None:
    sql = (
        "INSERT INTO document_syncs (document_id, document_version, trigger_type, status,"
        " embedding_model) VALUES (:d, 1, 'upload', CAST(:s AS sync_status), 'bge-m3')"
    )
    doc = new_document(conn, db)
    rejects(conn, sql, "ck_document_syncs_fragments_count", d=doc, s="succeeded")
    rejects(conn, sql, "ck_document_syncs_error_message", d=doc, s="failed")
