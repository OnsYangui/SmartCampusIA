"""SA-22 — consistency rules and permissions of the catalogue, fees and requirements."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

import app.seed as seed
from app.main import app
from app.models.enums import program_type
from app.schemas.catalog import ProgramType
from app.services.catalog import Requirements, assess_eligibility


@pytest.fixture
def program(conn: Connection) -> uuid.UUID:
    institution = conn.execute(
        text("INSERT INTO institutions (code, name) VALUES ('T', 'Test') RETURNING id")
    ).scalar_one()
    return conn.execute(
        text(
            "INSERT INTO programs (institution_id, code, name, type, duration_years) "
            "VALUES (:institution, 'T-1', 'Test', 'licence', 3) RETURNING id"
        ),
        {"institution": institution},
    ).scalar_one()


def insert_fee(conn: Connection, program: uuid.UUID, **values: Any) -> None:
    row = {
        "program_id": program,
        "academic_year": "2026-2027",
        "label": "Frais de scolarité annuels",
        "amount": 6900,
        "source_url": "https://iit.example/frais.pdf",
        "verified_on": "2026-09-01",
    } | values
    columns = ", ".join(row)
    params = ", ".join(f":{name}" for name in row)
    with conn.begin_nested():
        conn.execute(text(f"INSERT INTO program_fees ({columns}) VALUES ({params})"), row)


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"source_url": None}, "ck_program_fees_official_or_demo"),
        ({"verified_on": None}, "ck_program_fees_official_or_demo"),
        ({"amount": 0}, "ck_program_fees_positive_amount"),
        ({"academic_year": "2026"}, "ck_program_fees_academic_year_format"),
        ({"academic_year": "2026-2028"}, "ck_program_fees_academic_year_format"),
        ({"academic_year": "26-27xxxx"}, "ck_program_fees_academic_year_format"),
        ({"currency": "dt"}, "ck_program_fees_currency_code"),
    ],
)
def test_invalid_fees_are_rejected(conn: Connection, program, values, constraint) -> None:
    with pytest.raises(DBAPIError, match=constraint):
        insert_fee(conn, program, **values)


def test_demonstration_fees_need_no_official_source(conn: Connection, program) -> None:
    insert_fee(conn, program, source_url=None, verified_on=None, is_demo=True)


def test_a_fee_has_one_draft_per_program_year_and_label(conn: Connection, program) -> None:
    insert_fee(conn, program)

    with pytest.raises(DBAPIError, match="uq_program_fees_one_draft"):
        insert_fee(conn, program, amount=7000)


@pytest.mark.parametrize(
    "assignment",
    [
        "admission_source_url = 'https://x.example'",
        "admission_verified_on = '2026-09-01'",
        "admission_is_demo = true, admission_source_url = 'https://x.example', "
        "admission_verified_on = '2026-09-01'",
    ],
)
def test_admission_provenance_is_consistent(conn: Connection, program, assignment) -> None:
    with pytest.raises(DBAPIError, match="ck_programs_admission_provenance"), conn.begin_nested():
        conn.execute(text(f"UPDATE programs SET {assignment} WHERE id = :id"), {"id": program})


@pytest.mark.parametrize(
    ("role", "privilege", "granted"),
    [
        ("smartcampus_app", "SELECT", True),
        ("smartcampus_app", "INSERT", True),
        ("smartcampus_app", "UPDATE", True),
        ("smartcampus_app", "DELETE", False),
        ("smartcampus_readonly", "SELECT", True),
        ("smartcampus_readonly", "INSERT", False),
    ],
)
def test_fee_table_follows_least_privilege(conn: Connection, role, privilege, granted) -> None:
    query = text("SELECT has_table_privilege(:role, 'program_fees', :privilege)")

    assert conn.execute(query, {"role": role, "privilege": privilege}).scalar_one() is granted


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/programs"),
        ("put", f"/api/v1/programs/{uuid.UUID(int=1)}"),
        ("delete", f"/api/v1/programs/{uuid.UUID(int=1)}"),
        ("post", f"/api/v1/programs/{uuid.UUID(int=1)}/fees"),
        ("post", "/api/v1/institutions"),
    ],
)
def test_catalogue_is_read_only_until_authentication_exists(
    api: TestClient, method: str, path: str
) -> None:
    response = api.request(method, path)

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_reference_seed_does_not_invent_official_fees(conn: Connection) -> None:
    seed.seed_reference(conn)

    assert conn.execute(text("SELECT count(*) FROM program_fees")).scalar_one() == 0


def requirements_by_code(api: TestClient, conn: Connection) -> dict[str, dict]:
    programs = conn.execute(text("SELECT code, id FROM programs")).all()
    return {
        code: api.get(f"/api/v1/programs/{program}/admission-requirements").json()
        for code, program in programs
    }


def test_reference_seed_records_official_admission_conditions(
    api: TestClient, conn: Connection
) -> None:
    seed.seed_reference(conn)

    requirements = requirements_by_code(api, conn)

    assert {code: body["data_status"] for code, body in requirements.items()} == {
        "IIT-PREPA": "verified",
        "IIT-LIC-INFO": "verified",
        "IIT-ING-GL": "verified",
        "ISB-LIC-GEST": "verified",
    }
    for code, body in requirements.items():
        assert body["source_url"].startswith(f"https://{code[:3].lower()}.tn/")
        assert body["verified_on"] == "2026-11-14"
        assert "DÉMO" not in body["prerequisites"]
    assert "DC-SC-17" in requirements["IIT-ING-GL"]["prerequisites"]
    assert requirements["IIT-ING-GL"]["bac_sections"] is None


def test_reference_seed_uses_official_program_names(conn: Connection) -> None:
    seed.seed_reference(conn)
    conn.execute(
        text("UPDATE programs SET name = 'Ingénieur en génie logiciel' WHERE code = 'IIT-ING-GL'")
    )

    seed.seed_reference(conn)

    names = dict(conn.execute(text("SELECT code, name FROM programs")).all())
    assert names["IIT-ING-GL"] == "Ingénieur en génie informatique"
    assert names["ISB-LIC-GEST"] == "Licence nationale en gestion"


def test_reference_seed_records_official_specialties_and_subjects(
    api: TestClient, conn: Connection
) -> None:
    seed.seed_reference(conn)
    seed.seed_reference(conn)

    def public(code: str, resource: str):
        return api.get(f"/api/v1/programs/{seed.uid('program', code)}/{resource}").json()

    assert [s["code"] for s in public("IIT-ING-GL", "specialties")] == ["ARSI", "GLID", "SDIA"]
    assert len(public("ISB-LIC-GEST", "specialties")) == 5
    subjects = public("ISB-LIC-GEST", "subjects")
    assert subjects["total"] == 18
    assert {subject["study_year"] for subject in subjects["items"]} == {1}


def test_demonstration_fees_are_never_public(api: TestClient, conn: Connection) -> None:
    seed.seed_reference(conn)
    seed.seed_demo(conn)

    for code in ("IIT-PREPA", "ISB-LIC-GEST"):
        fees = api.get(f"/api/v1/programs/{seed.uid('program', code)}/fees").json()
        assert fees == {"data_status": "unavailable", "items": []}


def test_reference_seed_keeps_a_source_recorded_since(api: TestClient, conn: Connection) -> None:
    seed.seed_reference(conn)
    conn.execute(
        text(
            "UPDATE programs SET admission_source_url = 'https://iit.tn/nouveau.pdf', "
            "admission_verified_on = '2027-06-01' WHERE code = 'IIT-PREPA'"
        )
    )

    seed.seed_reference(conn)

    assert requirements_by_code(api, conn)["IIT-PREPA"]["source_url"] == (
        "https://iit.tn/nouveau.pdf"
    )


@pytest.mark.parametrize(
    ("code", "section", "status"),
    [
        ("IIT-PREPA", "Sciences expérimentales", "eligible"),
        ("IIT-PREPA", "Économie et gestion", "not_eligible"),
        ("IIT-LIC-INFO", "Economie et gestion", "eligible"),
        ("IIT-LIC-INFO", "Lettres", "not_eligible"),
        ("IIT-ING-GL", "Mathématiques", "undetermined"),
        ("ISB-LIC-GEST", "Économie et gestion", "undetermined"),
    ],
)
def test_eligibility_against_the_official_conditions(
    api: TestClient, conn: Connection, code: str, section: str, status: str
) -> None:
    seed.seed_reference(conn)

    response = api.get(
        f"/api/v1/programs/{seed.uid('program', code)}/eligibility",
        params={"bac_section": section, "bac_average": 14},
    )

    assert response.json()["status"] == status


def test_demonstration_fees_are_labelled_and_unverified(conn: Connection) -> None:
    seed.seed_reference(conn)
    seed.seed_demo(conn)

    fees = conn.execute(text("SELECT label, is_demo, source_url FROM program_fees")).all()

    assert fees
    assert all(
        label.startswith("DÉMO FICTIVE — ") and is_demo and source_url is None
        for label, is_demo, source_url in fees
    )


def published(**values: Any) -> Requirements:
    return Requirements(
        **{"bac_sections": None, "min_bac_average": None, "prerequisites": None} | values
    )


@pytest.mark.parametrize(
    ("requirements", "section", "average", "status"),
    [
        (
            published(bac_sections=["Sciences expérimentales"]),
            " SCIENCES EXPERIMENTALES ",
            10,
            "eligible",
        ),
        (published(min_bac_average=Decimal("12.00")), "Lettres", Decimal("12.00"), "eligible"),
        (published(min_bac_average=Decimal("12.00")), "Lettres", Decimal("11.99"), "not_eligible"),
        (published(prerequisites="Entretien et test"), "Lettres", 15, "undetermined"),
        (None, "Lettres", 15, "undetermined"),
    ],
)
def test_assess_eligibility(requirements, section, average, status) -> None:
    assert assess_eligibility(requirements, section, Decimal(average)).status == status


def test_program_type_filter_matches_the_database_enum() -> None:
    assert sorted(member.value for member in ProgramType) == sorted(program_type.enums)


def test_unexpected_errors_use_the_error_format() -> None:
    from app.core.db import get_session

    def broken_session():
        raise RuntimeError("database driver crashed")

    app.dependency_overrides[get_session] = broken_session
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/api/v1/institutions")
    finally:
        app.dependency_overrides.pop(get_session)

    assert response.status_code == 500
    assert response.json() == {"code": "internal_error", "message": "Erreur interne du serveur"}


def test_openapi_documents_the_catalogue_contract(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]

    assert set(spec["paths"]) >= {
        "/api/v1/institutions",
        "/api/v1/institutions/{institution_id}",
        "/api/v1/programs",
        "/api/v1/programs/{program_id}",
        "/api/v1/programs/{program_id}/fees",
        "/api/v1/programs/{program_id}/admission-requirements",
        "/api/v1/programs/{program_id}/eligibility",
        "/api/v1/programs/{program_id}/specialties",
        "/api/v1/programs/{program_id}/subjects",
        "/api/v1/manage/programs",
        "/api/v1/manage/fees/{fee_id}/publish",
        "/api/v1/manage/programs/{program_id}/admission-requirements/publish",
    }
    assert schemas["EligibilityOut"]["properties"]["status"]["enum"] == [
        "eligible",
        "not_eligible",
        "undetermined",
    ]
    assert schemas["FeeListOut"]["properties"]["data_status"]["enum"] == ["verified", "unavailable"]
    assert "404" in spec["paths"]["/api/v1/programs/{program_id}"]["get"]["responses"]
    parameters = spec["paths"]["/api/v1/programs"]["get"]["parameters"]
    assert {parameter["name"] for parameter in parameters} == {
        "page",
        "size",
        "institution",
        "type",
        "q",
    }


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"status": "published", "valid_from": None}, "ck_program_fees_publication"),
        (
            {"status": "published", "is_demo": True, "source_url": None, "verified_on": None},
            "ck_program_fees_publication",
        ),
        ({"valid_from": "2026-09-01", "valid_until": "2026-08-31"}, "ck_program_fees_validity"),
        ({"valid_until": "2026-08-31"}, "ck_program_fees_validity"),
    ],
)
def test_fee_publication_rules_are_enforced_by_the_database(
    conn: Connection, program, values, constraint
) -> None:
    with pytest.raises(DBAPIError, match=constraint):
        insert_fee(conn, program, **values)


@pytest.mark.parametrize(
    ("assignment", "constraint"),
    [
        ("admission_status = 'published'", "ck_programs_admission_publication"),
        (
            "admission_valid_from = '2026-09-01', admission_valid_until = '2026-08-31'",
            "ck_programs_admission_validity",
        ),
    ],
)
def test_admission_publication_rules_are_enforced_by_the_database(
    conn: Connection, program, assignment, constraint
) -> None:
    with pytest.raises(DBAPIError, match=constraint), conn.begin_nested():
        conn.execute(text(f"UPDATE programs SET {assignment} WHERE id = :id"), {"id": program})


def test_a_subject_cannot_use_another_programs_specialty(conn: Connection, program) -> None:
    other = conn.execute(
        text(
            "INSERT INTO programs (institution_id, code, name, type, duration_years) "
            "SELECT institution_id, 'T-2', 'Autre', 'licence', 3 FROM programs WHERE id = :id "
            "RETURNING id"
        ),
        {"id": program},
    ).scalar_one()
    specialty = conn.execute(
        text(
            "INSERT INTO program_specialties (program_id, code, name) "
            "VALUES (:program, 'X', 'X') RETURNING id"
        ),
        {"program": other},
    ).scalar_one()

    with pytest.raises(DBAPIError, match="fk_subjects_specialty_id_program_specialties"):
        conn.execute(
            text(
                "INSERT INTO subjects (program_id, specialty_id, name, study_year) "
                "VALUES (:program, :specialty, 'Matière', 1)"
            ),
            {"program": program, "specialty": specialty},
        )


@pytest.mark.parametrize("table", ["program_specialties", "subjects"])
@pytest.mark.parametrize(
    ("role", "privilege", "granted"),
    [
        ("smartcampus_app", "INSERT", True),
        ("smartcampus_app", "UPDATE", True),
        ("smartcampus_app", "DELETE", False),
        ("smartcampus_readonly", "SELECT", True),
        ("smartcampus_readonly", "UPDATE", False),
    ],
)
def test_new_catalogue_tables_follow_least_privilege(
    conn: Connection, table, role, privilege, granted
) -> None:
    query = text("SELECT has_table_privilege(:role, :table, :privilege)")

    assert (
        conn.execute(query, {"role": role, "table": table, "privilege": privilege}).scalar_one()
        is granted
    )


def test_an_archived_fee_frees_its_year_and_label(conn: Connection, program) -> None:
    insert_fee(conn, program, status="archived")
    insert_fee(conn, program)

    with pytest.raises(DBAPIError, match="uq_program_fees_one_draft"):
        insert_fee(conn, program, amount=7000)


@pytest.mark.parametrize(
    ("second", "overlaps"),
    [
        ({"valid_from": "2026-12-01"}, True),
        ({"valid_from": "2026-09-01", "valid_until": "2026-12-31"}, True),
        ({"valid_from": "2027-07-01"}, False),
        ({"valid_from": "2026-12-01", "label": "Droits d'inscription"}, False),
    ],
)
def test_published_fees_cannot_overlap_in_the_database(
    conn: Connection, program, second, overlaps
) -> None:
    published = {"status": "published", "valid_from": "2026-09-01"}
    insert_fee(conn, program, **published, valid_until="2027-06-30")

    if overlaps:
        with pytest.raises(DBAPIError, match="program_fees_published_overlap"):
            insert_fee(conn, program, **published | second)
    else:
        insert_fee(conn, program, **published | second)
