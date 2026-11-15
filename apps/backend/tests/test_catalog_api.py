"""SA-20 and SA-21 — catalogue, tuition fees, admission requirements and eligibility APIs."""

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.factories import UNKNOWN_ID, insert

API = "/api/v1"


def codes(response) -> list[str]:
    return [item["code"] for item in response.json()["items"]]


# SA-20 — Institutions
def test_institutions_are_listed_by_code_with_pagination(api: TestClient, catalog) -> None:
    response = api.get(f"{API}/institutions", params={"size": 1})

    assert response.status_code == 200
    assert response.json() | {"items": None} == {"items": None, "total": 2, "page": 1, "size": 1}
    assert codes(response) == ["IIT"]
    assert codes(api.get(f"{API}/institutions", params={"size": 1, "page": 2})) == ["ISB"]


def test_institution_detail(api: TestClient, catalog) -> None:
    response = api.get(f"{API}/institutions/{catalog['isb']}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(catalog["isb"]),
        "code": "ISB",
        "name": "ISB",
        "website": "https://isb.example",
    }


def test_unknown_institution_returns_not_found(api: TestClient, catalog) -> None:
    response = api.get(f"{API}/institutions/{UNKNOWN_ID}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert response.json()["message"]


def test_malformed_identifier_is_a_validation_error(api: TestClient) -> None:
    response = api.get(f"{API}/institutions/not-a-uuid")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["details"][0]["field"] == "path.institution_id"


# SA-20 — Programs
def test_programs_list_only_active_programs_ordered_by_institution_and_name(
    api: TestClient, catalog
) -> None:
    response = api.get(f"{API}/programs")

    assert response.status_code == 200
    assert response.json()["total"] == 4
    assert codes(response) == ["IIT-PREPA", "IIT-ING-GL", "IIT-LIC-INFO", "ISB-LIC-GEST"]
    first = response.json()["items"][0]
    assert first["institution"] == {
        "id": str(catalog["iit"]),
        "code": "IIT",
        "name": "Institut International de Technologie",
    }
    assert first["type"] == "prepa"
    assert first["duration_years"] == 2


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"institution": "isb"}, ["ISB-LIC-GEST"]),
        ({"type": "ingenieur"}, ["IIT-ING-GL"]),
        ({"q": "informatique"}, ["IIT-LIC-INFO"]),
        ({"q": "LOGICIEL"}, ["IIT-ING-GL"]),
        ({"institution": "IIT", "type": "licence"}, ["IIT-LIC-INFO"]),
        ({"institution": "UNKNOWN"}, []),
    ],
)
def test_programs_can_be_filtered(api: TestClient, catalog, params, expected) -> None:
    response = api.get(f"{API}/programs", params=params)

    assert response.status_code == 200
    assert codes(response) == expected
    assert response.json()["total"] == len(expected)


def test_programs_pagination_reports_the_full_total(api: TestClient, catalog) -> None:
    response = api.get(f"{API}/programs", params={"page": 2, "size": 3})

    assert codes(response) == ["ISB-LIC-GEST"]
    assert response.json()["total"] == 4


def test_a_page_beyond_the_last_one_is_empty(api: TestClient, catalog) -> None:
    response = api.get(f"{API}/programs", params={"page": 9})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 4


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"page": 0}, "query.page"),
        ({"size": 0}, "query.size"),
        ({"size": 101}, "query.size"),
        ({"type": "master"}, "query.type"),
        ({"q": "x" * 101}, "query.q"),
    ],
)
def test_invalid_list_parameters_are_rejected(api: TestClient, params, field) -> None:
    response = api.get(f"{API}/programs", params=params)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert [detail["field"] for detail in response.json()["details"]] == [field]


def test_program_detail_includes_institution_and_pathways(api: TestClient, catalog) -> None:
    response = api.get(f"{API}/programs/{catalog['prepa']}")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "IIT-PREPA"
    assert body["institution"]["code"] == "IIT"
    assert body["pathways"] == [
        {
            "program": {
                "id": str(catalog["genie"]),
                "code": "IIT-ING-GL",
                "name": "Ingénieur en génie logiciel",
            },
            "conditions": "Validation des deux années",
        }
    ]


def test_inactive_program_is_not_found(api: TestClient, catalog) -> None:
    response = api.get(f"{API}/programs/{catalog['closed']}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# SA-20 — Specialties and subjects
@pytest.fixture
def curriculum(conn: Connection, catalog) -> dict[str, uuid.UUID]:
    glid = insert(
        conn, "program_specialties", program_id=catalog["genie"], code="GLID", name="GLID"
    )
    insert(
        conn,
        "program_specialties",
        program_id=catalog["genie"],
        code="OLD",
        name="Parcours fermé",
        is_active=False,
    )
    common = insert(
        conn, "subjects", program_id=catalog["genie"], name="Algorithmique", study_year=1
    )
    insert(
        conn,
        "subjects",
        program_id=catalog["genie"],
        specialty_id=glid,
        name="Génie logiciel",
        study_year=2,
        semester=3,
        credits=5,
    )
    insert(
        conn,
        "subjects",
        program_id=catalog["genie"],
        name="Matière retirée",
        study_year=1,
        is_active=False,
    )
    return {"glid": glid, "common": common}


def test_active_specialties_are_listed(api: TestClient, catalog, curriculum) -> None:
    response = api.get(f"{API}/programs/{catalog['genie']}/specialties")

    assert response.status_code == 200
    assert response.json() == [
        {"id": str(curriculum["glid"]), "code": "GLID", "name": "GLID", "description": None}
    ]


def test_active_subjects_are_listed_by_year_and_can_be_filtered(
    api: TestClient, catalog, curriculum
) -> None:
    url = f"{API}/programs/{catalog['genie']}/subjects"

    body = api.get(url).json()
    assert [subject["name"] for subject in body["items"]] == ["Algorithmique", "Génie logiciel"]
    assert body["total"] == 2
    assert body["items"][1] | {"id": None} == {
        "id": None,
        "name": "Génie logiciel",
        "specialty_id": str(curriculum["glid"]),
        "study_year": 2,
        "semester": 3,
        "credits": "5.0",
    }
    by_year = api.get(url, params={"study_year": 2}).json()["items"]
    by_specialty = api.get(url, params={"specialty_id": str(curriculum["glid"])}).json()["items"]
    assert [subject["name"] for subject in by_year] == ["Génie logiciel"]
    assert [subject["name"] for subject in by_specialty] == ["Génie logiciel"]


# SA-21 — Tuition fees: only published, official and currently valid fees are public
def days(offset: int) -> date:
    return date.today() + timedelta(days=offset)


OFFICIAL = {"source_url": "https://iit.example/frais.pdf", "verified_on": "2026-09-01"}


def new_fee(conn: Connection, program: uuid.UUID, label: str, **values: Any) -> uuid.UUID:
    row = {
        "academic_year": "2026-2027",
        "amount": 6900,
        "status": "published",
        "valid_from": days(-30),
    } | OFFICIAL
    return insert(conn, "program_fees", program_id=program, label=label, **row | values)


@pytest.fixture
def fees(conn: Connection, catalog) -> None:
    program = catalog["info"]
    new_fee(conn, program, "Frais de scolarité annuels", payment_terms="9 mensualités")
    new_fee(conn, program, "Droits d'inscription", amount=800)
    new_fee(conn, program, "Frais de scolarité annuels", academic_year="2025-2026", amount=6500)
    new_fee(conn, program, "Brouillon", status="draft")
    new_fee(conn, program, "Archivé", status="archived")
    new_fee(conn, program, "Expiré", valid_from=days(-60), valid_until=days(-1))
    new_fee(conn, program, "Futur", valid_from=days(1))
    new_fee(
        conn,
        program,
        "DÉMO FICTIVE — Frais",
        status="draft",
        is_demo=True,
        source_url=None,
        verified_on=None,
    )


def test_only_published_and_currently_valid_fees_are_public(api: TestClient, catalog, fees) -> None:
    response = api.get(f"{API}/programs/{catalog['info']}/fees")

    assert response.status_code == 200
    body = response.json()
    assert body["data_status"] == "verified"
    assert [(fee["academic_year"], fee["label"]) for fee in body["items"]] == [
        ("2026-2027", "Droits d'inscription"),
        ("2026-2027", "Frais de scolarité annuels"),
        ("2025-2026", "Frais de scolarité annuels"),
    ]
    assert body["items"][1] == {
        "academic_year": "2026-2027",
        "label": "Frais de scolarité annuels",
        "amount": "6900.000",
        "currency": "TND",
        "payment_terms": "9 mensualités",
        "source_url": "https://iit.example/frais.pdf",
        "verified_on": "2026-09-01",
        "valid_from": days(-30).isoformat(),
        "valid_until": None,
    }


@pytest.mark.parametrize(
    ("valid_from", "valid_until", "public"),
    [(0, None, True), (-10, 0, True), (1, None, False), (-10, -1, False)],
)
def test_fee_validity_boundaries(
    api: TestClient, conn: Connection, catalog, valid_from, valid_until, public
) -> None:
    new_fee(
        conn,
        catalog["gestion"],
        "Frais",
        valid_from=days(valid_from),
        valid_until=None if valid_until is None else days(valid_until),
    )

    items = api.get(f"{API}/programs/{catalog['gestion']}/fees").json()["items"]

    assert bool(items) is public


def test_fees_can_be_filtered_by_academic_year(api: TestClient, catalog, fees) -> None:
    response = api.get(
        f"{API}/programs/{catalog['info']}/fees", params={"academic_year": "2025-2026"}
    )

    assert [fee["amount"] for fee in response.json()["items"]] == ["6500.000"]


def test_programs_without_public_fees_report_them_unavailable(
    api: TestClient, catalog, fees
) -> None:
    for program, params in [
        (catalog["prepa"], {}),
        (catalog["info"], {"academic_year": "2030-2031"}),
    ]:
        response = api.get(f"{API}/programs/{program}/fees", params=params)

        assert response.status_code == 200
        assert response.json() == {"data_status": "unavailable", "items": []}


@pytest.mark.parametrize("year", ["2026", "2026/2027", "26-27", "2026-2028", "2027-2026"])
def test_malformed_academic_year_is_rejected(api: TestClient, catalog, year) -> None:
    response = api.get(f"{API}/programs/{catalog['info']}/fees", params={"academic_year": year})

    assert response.status_code == 422
    assert response.json()["details"][0]["field"] == "query.academic_year"


@pytest.mark.parametrize(
    "suffix", ["fees", "admission-requirements", "eligibility", "specialties", "subjects"]
)
def test_program_sub_resources_of_unknown_or_inactive_programs_are_not_found(
    api: TestClient, catalog, suffix
) -> None:
    params = {"bac_section": "Mathématiques", "bac_average": 14}
    for program in (UNKNOWN_ID, catalog["closed"]):
        response = api.get(f"{API}/programs/{program}/{suffix}", params=params)

        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


# SA-21 — Admission requirements: only published and currently valid conditions are public
def publish_requirements(
    conn: Connection, program: uuid.UUID, valid_from: int = -30, valid_until: int | None = None
) -> None:
    conn.execute(
        text(
            "UPDATE programs SET admission_source_url = 'https://iit.example/admission', "
            "admission_verified_on = '2026-09-01', admission_status = 'published', "
            "admission_valid_from = :valid_from, admission_valid_until = :valid_until "
            "WHERE id = :id"
        ),
        {
            "id": program,
            "valid_from": days(valid_from),
            "valid_until": None if valid_until is None else days(valid_until),
        },
    )


def requirements(api: TestClient, program: uuid.UUID) -> dict:
    return api.get(f"{API}/programs/{program}/admission-requirements").json()


UNAVAILABLE = {
    "data_status": "unavailable",
    "bac_sections": None,
    "min_bac_average": None,
    "prerequisites": None,
    "source_url": None,
    "verified_on": None,
    "valid_from": None,
    "valid_until": None,
}


def test_published_requirements_are_public(api: TestClient, conn: Connection, catalog) -> None:
    publish_requirements(conn, catalog["info"])

    response = api.get(f"{API}/programs/{catalog['info']}/admission-requirements")

    assert response.status_code == 200
    assert response.json() == {
        "data_status": "verified",
        "bac_sections": ["Mathématiques", "Informatique"],
        "min_bac_average": "12.00",
        "prerequisites": "Admission sur dossier",
        "source_url": "https://iit.example/admission",
        "verified_on": "2026-09-01",
        "valid_from": days(-30).isoformat(),
        "valid_until": None,
    }


def test_unpublished_requirements_are_unavailable(api: TestClient, catalog) -> None:
    assert requirements(api, catalog["info"]) == UNAVAILABLE


@pytest.mark.parametrize(
    ("valid_from", "valid_until", "public"),
    [(0, None, True), (-10, 0, True), (1, None, False), (-10, -1, False)],
)
def test_requirement_validity_boundaries(
    api: TestClient, conn: Connection, catalog, valid_from, valid_until, public
) -> None:
    publish_requirements(conn, catalog["info"], valid_from, valid_until)

    assert (requirements(api, catalog["info"])["data_status"] == "verified") is public


def test_archived_requirements_are_unavailable(api: TestClient, conn: Connection, catalog) -> None:
    publish_requirements(conn, catalog["info"])
    conn.execute(
        text("UPDATE programs SET admission_status = 'archived' WHERE id = :id"),
        {"id": catalog["info"]},
    )

    assert requirements(api, catalog["info"]) == UNAVAILABLE


# SA-21 — Eligibility
def eligibility(api: TestClient, program: uuid.UUID, section: str, average: float | str):
    return api.get(
        f"{API}/programs/{program}/eligibility",
        params={"bac_section": section, "bac_average": average},
    )


def test_meeting_published_conditions_is_eligible(
    api: TestClient, conn: Connection, catalog
) -> None:
    publish_requirements(conn, catalog["info"])

    response = eligibility(api, catalog["info"], "mathématiques", 12)

    assert response.status_code == 200
    assert response.json() == {
        "status": "eligible",
        "data_status": "verified",
        "checks": [
            {"criterion": "bac_section", "met": True},
            {"criterion": "min_bac_average", "met": True},
        ],
        "prerequisites": "Admission sur dossier",
    }


@pytest.mark.parametrize(
    ("section", "average", "failed"),
    [
        ("Lettres", 15, ["bac_section"]),
        ("Informatique", 11.99, ["min_bac_average"]),
        ("Lettres", 8, ["bac_section", "min_bac_average"]),
    ],
)
def test_failing_a_published_condition_is_not_eligible(
    api: TestClient, conn: Connection, catalog, section, average, failed
) -> None:
    publish_requirements(conn, catalog["info"])

    body = eligibility(api, catalog["info"], section, average).json()

    assert body["status"] == "not_eligible"
    assert [check["criterion"] for check in body["checks"] if not check["met"]] == failed


def test_unpublished_conditions_never_conclude(api: TestClient, catalog) -> None:
    for section, average in [("Mathématiques", 18), ("Lettres", 8)]:
        body = eligibility(api, catalog["info"], section, average).json()

        assert body == {
            "status": "undetermined",
            "data_status": "unavailable",
            "checks": [],
            "prerequisites": None,
        }


def test_published_conditions_without_measurable_criterion_are_undetermined(
    api: TestClient, conn: Connection, catalog
) -> None:
    publish_requirements(conn, catalog["gestion"])

    body = eligibility(api, catalog["gestion"], "Lettres", 10).json()

    assert body["status"] == "undetermined"
    assert body["data_status"] == "verified"


def test_bac_sections_match_regardless_of_accents_and_case(
    api: TestClient, conn: Connection, catalog
) -> None:
    conn.execute(
        text(
            "UPDATE programs SET admission_bac_sections = ARRAY['Économie et gestion'] "
            "WHERE id = :id"
        ),
        {"id": catalog["gestion"]},
    )
    publish_requirements(conn, catalog["gestion"])

    body = eligibility(api, catalog["gestion"], "  economie ET gestion", 10).json()

    assert body["status"] == "eligible"


@pytest.mark.parametrize(
    "params",
    [
        {"bac_section": "Mathématiques"},
        {"bac_average": 14},
        {"bac_section": "Mathématiques", "bac_average": 20.5},
        {"bac_section": "Mathématiques", "bac_average": -1},
        {"bac_section": "Mathématiques", "bac_average": "12.345"},
        {"bac_section": "Mathématiques", "bac_average": "douze"},
        {"bac_section": " ", "bac_average": 14},
        {"bac_section": "x" * 101, "bac_average": 14},
    ],
)
def test_invalid_eligibility_parameters_are_rejected(api: TestClient, catalog, params) -> None:
    response = api.get(f"{API}/programs/{catalog['info']}/eligibility", params=params)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
