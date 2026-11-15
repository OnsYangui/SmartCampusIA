"""SA-20 to SA-22 — responsible-only management of the catalogue, fees and admission conditions."""

import uuid
from collections.abc import Callable, Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.security import Principal, get_principal
from app.main import app
from tests.factories import UNKNOWN_ID

MANAGE = "/api/v1/manage"
TODAY = date.today()
SOURCE = {"source_url": "https://iit.tn/frais.pdf", "verified_on": "2026-09-01"}


@pytest.fixture
def login() -> Iterator[Callable[..., None]]:
    def as_user(role: str, institution: uuid.UUID | None = None) -> None:
        principal = Principal(user_id=uuid.uuid4(), role=role, institution_id=institution)
        app.dependency_overrides[get_principal] = lambda: principal

    yield as_user
    app.dependency_overrides.pop(get_principal, None)


@pytest.fixture
def admin(login, api: TestClient) -> TestClient:
    login("admin")
    return api


@pytest.fixture
def iit_manager(login, api: TestClient, catalog) -> TestClient:
    login("academic_manager", catalog["iit"])
    return api


def program_payload(institution: uuid.UUID, code: str = "IIT-ING-CIV", **values) -> dict:
    return {
        "institution_id": str(institution),
        "code": code,
        "name": "Ingénieur en génie civil",
        "type": "ingenieur",
        "field": "Génie civil",
        "duration_years": 3,
    } | values


# SA-22 — Authorization
MANAGEMENT_CALLS = [
    ("get", "/programs"),
    ("post", "/programs"),
    ("put", f"/programs/{UNKNOWN_ID}"),
    ("delete", f"/programs/{UNKNOWN_ID}"),
    ("post", f"/programs/{UNKNOWN_ID}/specialties"),
    ("post", f"/programs/{UNKNOWN_ID}/subjects"),
    ("post", f"/programs/{UNKNOWN_ID}/fees"),
    ("post", f"/fees/{UNKNOWN_ID}/publish"),
    ("post", f"/fees/{UNKNOWN_ID}/revisions"),
    ("put", f"/programs/{UNKNOWN_ID}/admission-requirements"),
    ("post", f"/programs/{UNKNOWN_ID}/admission-requirements/publish"),
]


@pytest.mark.parametrize(("method", "path"), MANAGEMENT_CALLS)
def test_management_requires_authentication(api: TestClient, method: str, path: str) -> None:
    response = api.request(method, MANAGE + path, json={})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


@pytest.mark.parametrize("role", ["candidate", "interview_manager", "management"])
@pytest.mark.parametrize(("method", "path"), MANAGEMENT_CALLS[:3])
def test_management_is_reserved_to_catalogue_managers(
    api: TestClient, login, catalog, role: str, method: str, path: str
) -> None:
    login(role, catalog["iit"] if role == "interview_manager" else None)

    response = api.request(method, MANAGE + path, json={})

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_academic_manager_only_sees_own_institution(iit_manager: TestClient, catalog) -> None:
    codes = [item["code"] for item in iit_manager.get(f"{MANAGE}/programs").json()["items"]]

    assert codes == ["IIT-PREPA", "IIT-ING-GL", "IIT-LIC-INFO"]
    response = iit_manager.get(f"{MANAGE}/programs/{catalog['gestion']}")
    assert response.status_code == 404


def test_academic_manager_cannot_create_for_another_institution(
    iit_manager: TestClient, catalog
) -> None:
    response = iit_manager.post(f"{MANAGE}/programs", json=program_payload(catalog["isb"]))

    assert response.status_code == 403


def test_academic_manager_cannot_change_another_institution(
    iit_manager: TestClient, catalog
) -> None:
    payload = program_payload(catalog["isb"], code="ISB-LIC-GEST")

    for response in (
        iit_manager.put(f"{MANAGE}/programs/{catalog['gestion']}", json=payload),
        iit_manager.delete(f"{MANAGE}/programs/{catalog['gestion']}"),
        iit_manager.post(f"{MANAGE}/programs/{catalog['gestion']}/fees", json={}),
    ):
        assert response.status_code == 404


# SA-20 — Programs
def test_program_lifecycle(admin: TestClient, catalog) -> None:
    created = admin.post(f"{MANAGE}/programs", json=program_payload(catalog["iit"]))

    assert created.status_code == 201
    program = created.json()
    assert program["code"] == "IIT-ING-CIV"
    assert program["is_active"] is True
    assert admin.get(f"/api/v1/programs/{program['id']}").status_code == 200

    updated = admin.put(
        f"{MANAGE}/programs/{program['id']}",
        json=program_payload(catalog["iit"], description="Formation d'ingénieurs."),
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Formation d'ingénieurs."

    assert admin.delete(f"{MANAGE}/programs/{program['id']}").status_code == 204
    assert admin.get(f"/api/v1/programs/{program['id']}").status_code == 404
    assert admin.get(f"{MANAGE}/programs/{program['id']}").json()["is_active"] is False


def test_management_list_includes_inactive_programs_with_filters(
    admin: TestClient, catalog
) -> None:
    body = admin.get(f"{MANAGE}/programs", params={"institution": "ISB", "size": 1}).json()

    assert body["total"] == 2
    assert [item["code"] for item in body["items"]] == ["ISB-OLD"]
    searched = admin.get(f"{MANAGE}/programs", params={"q": "ancienne"}).json()
    assert [item["code"] for item in searched["items"]] == ["ISB-OLD"]


def test_duplicate_program_code_is_a_conflict(admin: TestClient, catalog) -> None:
    response = admin.post(
        f"{MANAGE}/programs", json=program_payload(catalog["iit"], code="IIT-PREPA")
    )

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


@pytest.mark.parametrize(
    "values",
    [
        {"duration_years": 6},
        {"duration_years": 0},
        {"type": "master"},
        {"name": ""},
        {"code": "code avec espaces"},
        {"institution_id": "not-a-uuid"},
    ],
)
def test_invalid_program_is_rejected(admin: TestClient, catalog, values) -> None:
    response = admin.post(f"{MANAGE}/programs", json=program_payload(catalog["iit"], **values))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_unknown_institution_is_rejected(admin: TestClient, catalog) -> None:
    response = admin.post(f"{MANAGE}/programs", json=program_payload(uuid.UUID(UNKNOWN_ID)))

    assert response.status_code == 422


def test_missing_program_is_not_found(admin: TestClient, catalog) -> None:
    payload = program_payload(catalog["iit"])

    assert admin.get(f"{MANAGE}/programs/{UNKNOWN_ID}").status_code == 404
    assert admin.put(f"{MANAGE}/programs/{UNKNOWN_ID}", json=payload).status_code == 404


# SA-20 — Specialties and subjects
def test_specialty_lifecycle(admin: TestClient, catalog) -> None:
    url = f"{MANAGE}/programs/{catalog['genie']}/specialties"
    created = admin.post(url, json={"code": "GLID", "name": "Génie logiciel"})

    assert created.status_code == 201
    specialty = created.json()
    assert admin.post(url, json={"code": "GLID", "name": "Doublon"}).status_code == 409

    renamed = admin.put(
        f"{MANAGE}/specialties/{specialty['id']}",
        json={"code": "GLID", "name": "Génie logiciel et informatique décisionnelle"},
    )
    assert renamed.json()["name"] == "Génie logiciel et informatique décisionnelle"
    public = f"/api/v1/programs/{catalog['genie']}/specialties"
    assert [item["code"] for item in admin.get(public).json()] == ["GLID"]

    assert admin.delete(f"{MANAGE}/specialties/{specialty['id']}").status_code == 204
    assert admin.get(public).json() == []
    assert admin.get(url).json()[0]["is_active"] is False


def test_subject_lifecycle(admin: TestClient, catalog) -> None:
    specialty = admin.post(
        f"{MANAGE}/programs/{catalog['genie']}/specialties", json={"code": "GLID", "name": "GLID"}
    ).json()
    url = f"{MANAGE}/programs/{catalog['genie']}/subjects"
    payload = {"name": "Génie logiciel", "study_year": 2, "specialty_id": specialty["id"]}

    created = admin.post(url, json=payload | {"semester": 3, "credits": "5.0"})
    assert created.status_code == 201
    subject = created.json()
    assert admin.post(url, json=payload).status_code == 409

    updated = admin.put(f"{MANAGE}/subjects/{subject['id']}", json=payload | {"credits": "6"})
    assert updated.json()["credits"] == "6.0"
    assert admin.get(url, params={"study_year": 2}).json()["total"] == 1

    assert admin.delete(f"{MANAGE}/subjects/{subject['id']}").status_code == 204
    assert admin.get(f"/api/v1/programs/{catalog['genie']}/subjects").json()["items"] == []


def test_subject_specialty_must_belong_to_the_same_program(admin: TestClient, catalog) -> None:
    other = admin.post(
        f"{MANAGE}/programs/{catalog['info']}/specialties", json={"code": "X", "name": "X"}
    ).json()

    response = admin.post(
        f"{MANAGE}/programs/{catalog['genie']}/subjects",
        json={"name": "Matière", "study_year": 1, "specialty_id": other["id"]},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "values", [{"study_year": 7}, {"semester": 13}, {"credits": "0"}, {"name": ""}]
)
def test_invalid_subject_is_rejected(admin: TestClient, catalog, values) -> None:
    response = admin.post(
        f"{MANAGE}/programs/{catalog['genie']}/subjects",
        json={"name": "Matière", "study_year": 1} | values,
    )

    assert response.status_code == 422


# SA-21 — Fees and their publication
def fee_payload(**values) -> dict:
    return (
        {
            "academic_year": "2026-2027",
            "label": "Frais de scolarité annuels",
            "amount": "6900.000",
            "payment_terms": "9 mensualités ; 5 % de remise pour un paiement intégral",
            "valid_from": TODAY.isoformat(),
        }
        | SOURCE
        | values
    )


def public_fees(api: TestClient, program: uuid.UUID) -> list[dict]:
    return api.get(f"/api/v1/programs/{program}/fees").json()["items"]


def test_fee_is_public_only_once_published(admin: TestClient, catalog) -> None:
    created = admin.post(f"{MANAGE}/programs/{catalog['info']}/fees", json=fee_payload())

    assert created.status_code == 201
    fee = created.json()
    assert fee["status"] == "draft"
    assert public_fees(admin, catalog["info"]) == []

    published = admin.post(f"{MANAGE}/fees/{fee['id']}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    [public] = public_fees(admin, catalog["info"])
    assert public["payment_terms"].startswith("9 mensualités")


def publish_new_fee(api: TestClient, program: uuid.UUID, **values) -> dict:
    fee = api.post(f"{MANAGE}/programs/{program}/fees", json=fee_payload(**values)).json()
    return api.post(f"{MANAGE}/fees/{fee['id']}/publish").json()


def revise(api: TestClient, fee: dict, **values):
    return api.post(f"{MANAGE}/fees/{fee['id']}/revisions", json=fee_payload(**values))


def days(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def test_a_published_fee_is_changed_through_a_revision(admin: TestClient, catalog) -> None:
    fee = publish_new_fee(admin, catalog["info"], valid_from=days(-30))

    assert admin.put(f"{MANAGE}/fees/{fee['id']}", json=fee_payload()).status_code == 409
    revision = revise(admin, fee, amount="7200", valid_from=days(0))
    assert revision.status_code == 201
    assert revision.json() | {"id": None} == revision.json() | {
        "id": None,
        "status": "draft",
        "replaces_id": fee["id"],
    }
    assert [f["amount"] for f in public_fees(admin, catalog["info"])] == ["6900.000"]

    admin.post(f"{MANAGE}/fees/{revision.json()['id']}/publish")

    assert [f["amount"] for f in public_fees(admin, catalog["info"])] == ["7200.000"]
    assert admin.get(f"{MANAGE}/fees/{fee['id']}").json()["status"] == "archived"


def test_a_future_revision_keeps_the_current_version_until_it_starts(
    admin: TestClient, catalog
) -> None:
    fee = publish_new_fee(admin, catalog["info"], valid_from=days(-30), payment_terms="9 mois")
    revision = revise(admin, fee, amount="7200", valid_from=days(10), payment_terms="10 mois")

    admin.post(f"{MANAGE}/fees/{revision.json()['id']}/publish")

    [current] = public_fees(admin, catalog["info"])
    assert (current["amount"], current["payment_terms"]) == ("6900.000", "9 mois")
    assert current["valid_until"] == days(9)
    statuses = {
        f["amount"]: f["status"]
        for f in admin.get(f"{MANAGE}/programs/{catalog['info']}/fees").json()
    }
    assert statuses == {"6900.000": "published", "7200.000": "published"}


def test_a_fee_has_at_most_one_pending_revision(admin: TestClient, catalog) -> None:
    fee = publish_new_fee(admin, catalog["info"])
    revise(admin, fee, amount="7200")

    assert revise(admin, fee, amount="7300").status_code == 409


def test_only_published_fees_can_be_revised(admin: TestClient, catalog) -> None:
    draft = admin.post(f"{MANAGE}/programs/{catalog['info']}/fees", json=fee_payload()).json()

    assert revise(admin, draft).status_code == 409


@pytest.mark.parametrize(
    ("first_until", "second_from", "allowed"), [(None, 5, False), (5, 6, True)]
)
def test_published_fees_never_overlap(
    admin: TestClient, catalog, first_until, second_from, allowed
) -> None:
    until = None if first_until is None else days(first_until)
    publish_new_fee(admin, catalog["info"], valid_from=days(-30), valid_until=until)
    second = admin.post(
        f"{MANAGE}/programs/{catalog['info']}/fees",
        json=fee_payload(amount="7200", valid_from=days(second_from)),
    ).json()

    response = admin.post(f"{MANAGE}/fees/{second['id']}/publish")

    assert response.status_code == (200 if allowed else 409)


def test_archived_fee_is_withdrawn_and_frozen(admin: TestClient, catalog) -> None:
    fee = admin.post(f"{MANAGE}/programs/{catalog['info']}/fees", json=fee_payload()).json()
    admin.post(f"{MANAGE}/fees/{fee['id']}/publish")

    assert admin.post(f"{MANAGE}/fees/{fee['id']}/archive").json()["status"] == "archived"
    assert public_fees(admin, catalog["info"]) == []
    assert admin.post(f"{MANAGE}/fees/{fee['id']}/publish").status_code == 409
    assert admin.put(f"{MANAGE}/fees/{fee['id']}", json=fee_payload()).status_code == 409


@pytest.mark.parametrize(
    "values",
    [
        {"is_demo": True, "source_url": None, "verified_on": None},
        {"valid_from": None},
    ],
)
def test_fee_without_official_source_or_validity_cannot_be_published(
    admin: TestClient, catalog, values
) -> None:
    fee = admin.post(f"{MANAGE}/programs/{catalog['info']}/fees", json=fee_payload(**values)).json()

    response = admin.post(f"{MANAGE}/fees/{fee['id']}/publish")

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


@pytest.mark.parametrize(
    "values",
    [
        {"source_url": None},
        {"amount": "0"},
        {"academic_year": "2026-2028"},
        {"currency": "dt"},
        {"valid_until": (TODAY - timedelta(days=1)).isoformat()},
    ],
)
def test_invalid_fee_is_rejected(admin: TestClient, catalog, values) -> None:
    response = admin.post(f"{MANAGE}/programs/{catalog['info']}/fees", json=fee_payload(**values))

    assert response.status_code == 422


def test_fees_are_listed_with_their_status(admin: TestClient, catalog) -> None:
    url = f"{MANAGE}/programs/{catalog['info']}/fees"
    first = admin.post(url, json=fee_payload()).json()
    admin.post(url, json=fee_payload(label="Droits d'inscription", amount="800"))
    admin.post(f"{MANAGE}/fees/{first['id']}/publish")

    statuses = {fee["label"]: fee["status"] for fee in admin.get(url).json()}

    assert statuses == {"Frais de scolarité annuels": "published", "Droits d'inscription": "draft"}


# SA-21 — Admission conditions and their publication
def requirements_payload(**values) -> dict:
    return (
        {
            "bac_sections": ["Mathématiques", "Sciences de l'informatique"],
            "min_bac_average": "12.00",
            "prerequisites": "Admission sur dossier.",
            "valid_from": TODAY.isoformat(),
            "valid_until": None,
        }
        | SOURCE
        | values
    )


def test_admission_requirements_publication(admin: TestClient, catalog) -> None:
    url = f"{MANAGE}/programs/{catalog['prepa']}/admission-requirements"
    public = f"/api/v1/programs/{catalog['prepa']}/admission-requirements"

    saved = admin.put(url, json=requirements_payload())
    assert saved.status_code == 200
    assert saved.json()["status"] == "draft"
    assert admin.get(public).json()["data_status"] == "unavailable"

    assert admin.post(f"{url}/publish").json()["status"] == "published"
    assert admin.get(public).json()["bac_sections"] == [
        "Mathématiques",
        "Sciences de l'informatique",
    ]
    eligibility = admin.get(
        f"/api/v1/programs/{catalog['prepa']}/eligibility",
        params={"bac_section": "Lettres", "bac_average": 15},
    ).json()
    assert eligibility["status"] == "not_eligible"

    assert admin.post(f"{url}/archive").json()["status"] == "archived"
    assert admin.get(public).json()["data_status"] == "unavailable"
    assert admin.get(url).json()["status"] == "archived"


def test_editing_published_requirements_withdraws_them(admin: TestClient, catalog) -> None:
    url = f"{MANAGE}/programs/{catalog['prepa']}/admission-requirements"
    admin.put(url, json=requirements_payload())
    admin.post(f"{url}/publish")

    admin.put(url, json=requirements_payload(min_bac_average="13.00"))

    public = admin.get(f"/api/v1/programs/{catalog['prepa']}/admission-requirements").json()
    assert public["data_status"] == "unavailable"


@pytest.mark.parametrize(
    "values",
    [{"source_url": None, "verified_on": None}, {"valid_from": None}, {"is_demo": True}],
)
def test_unverified_requirements_cannot_be_published(admin: TestClient, catalog, values) -> None:
    url = f"{MANAGE}/programs/{catalog['prepa']}/admission-requirements"
    payload = requirements_payload(**values)
    if values.get("is_demo"):
        payload |= {"source_url": None, "verified_on": None}
    admin.put(url, json=payload)

    response = admin.post(f"{url}/publish")

    assert response.status_code == 409


@pytest.mark.parametrize(
    "values",
    [
        {"min_bac_average": "21"},
        {"source_url": "https://iit.tn/x.pdf", "verified_on": None},
        {"valid_until": (TODAY - timedelta(days=1)).isoformat()},
        {"is_demo": True},
    ],
)
def test_invalid_requirements_are_rejected(admin: TestClient, catalog, values) -> None:
    response = admin.put(
        f"{MANAGE}/programs/{catalog['prepa']}/admission-requirements",
        json=requirements_payload(**values),
    )

    assert response.status_code == 422


# SA-20 — Remaining management operations
def test_specialties_subjects_and_fees_are_read_individually(admin: TestClient, catalog) -> None:
    program = catalog["genie"]
    specialty = admin.post(
        f"{MANAGE}/programs/{program}/specialties", json={"code": "GLID", "name": "GLID"}
    ).json()
    subject = admin.post(
        f"{MANAGE}/programs/{program}/subjects", json={"name": "Algorithmique", "study_year": 1}
    ).json()
    fee = admin.post(f"{MANAGE}/programs/{program}/fees", json=fee_payload()).json()

    for path, expected in [
        (f"/specialties/{specialty['id']}", specialty),
        (f"/subjects/{subject['id']}", subject),
        (f"/fees/{fee['id']}", fee),
    ]:
        response = admin.get(MANAGE + path)
        assert response.status_code == 200
        assert response.json() == expected


def test_resources_of_another_institution_are_not_found(api: TestClient, login, catalog) -> None:
    login("admin")
    program = catalog["gestion"]
    specialty = api.post(
        f"{MANAGE}/programs/{program}/specialties", json={"code": "FIN", "name": "Finance"}
    ).json()
    subject = api.post(
        f"{MANAGE}/programs/{program}/subjects", json={"name": "Microéconomie", "study_year": 1}
    ).json()
    fee = api.post(f"{MANAGE}/programs/{program}/fees", json=fee_payload()).json()

    login("academic_manager", catalog["iit"])
    calls = [
        ("get", f"/specialties/{specialty['id']}", None),
        ("put", f"/specialties/{specialty['id']}", {"code": "FIN", "name": "X"}),
        ("delete", f"/specialties/{specialty['id']}", None),
        ("get", f"/subjects/{subject['id']}", None),
        ("put", f"/subjects/{subject['id']}", {"name": "X", "study_year": 1}),
        ("delete", f"/subjects/{subject['id']}", None),
        ("get", f"/fees/{fee['id']}", None),
        ("put", f"/fees/{fee['id']}", fee_payload()),
        ("post", f"/fees/{fee['id']}/publish", None),
        ("post", f"/fees/{fee['id']}/archive", None),
        ("get", f"/programs/{program}/admission-requirements", None),
        ("post", f"/programs/{program}/admission-requirements/publish", None),
    ]
    for method, path, body in calls:
        assert api.request(method, MANAGE + path, json=body).status_code == 404, path


def test_deactivated_specialty_and_subject_can_be_reactivated(admin: TestClient, catalog) -> None:
    program = catalog["genie"]
    specialty = admin.post(
        f"{MANAGE}/programs/{program}/specialties", json={"code": "GLID", "name": "GLID"}
    ).json()
    subject = admin.post(
        f"{MANAGE}/programs/{program}/subjects", json={"name": "Algorithmique", "study_year": 1}
    ).json()
    admin.delete(f"{MANAGE}/specialties/{specialty['id']}")
    admin.delete(f"{MANAGE}/subjects/{subject['id']}")

    admin.put(
        f"{MANAGE}/specialties/{specialty['id']}",
        json={"code": "GLID", "name": "GLID", "is_active": True},
    )
    admin.put(
        f"{MANAGE}/subjects/{subject['id']}",
        json={"name": "Algorithmique", "study_year": 1, "is_active": True},
    )

    assert len(admin.get(f"/api/v1/programs/{program}/specialties").json()) == 1
    assert admin.get(f"/api/v1/programs/{program}/subjects").json()["total"] == 1


def test_subjects_can_be_searched_by_name(admin: TestClient, catalog) -> None:
    program = catalog["genie"]
    for name in ("Génie logiciel", "Bases de données", "Logique formelle"):
        admin.post(f"{MANAGE}/programs/{program}/subjects", json={"name": name, "study_year": 1})

    for url in (f"{MANAGE}/programs/{program}/subjects", f"/api/v1/programs/{program}/subjects"):
        names = [s["name"] for s in admin.get(url, params={"q": "logi"}).json()["items"]]
        assert names == ["Génie logiciel", "Logique formelle"]


def test_manager_cannot_move_a_program_to_another_institution(
    iit_manager: TestClient, catalog
) -> None:
    response = iit_manager.put(
        f"{MANAGE}/programs/{catalog['prepa']}",
        json=program_payload(catalog["isb"], code="IIT-PREPA"),
    )

    assert response.status_code == 403


def test_renaming_a_program_to_an_existing_code_is_a_conflict(admin: TestClient, catalog) -> None:
    response = admin.put(
        f"{MANAGE}/programs/{catalog['info']}",
        json=program_payload(catalog["iit"], code="IIT-PREPA"),
    )

    assert response.status_code == 409


# SA-21 — Fee versions and validity
def test_an_archived_fee_can_be_replaced(admin: TestClient, catalog) -> None:
    url = f"{MANAGE}/programs/{catalog['info']}/fees"
    old = admin.post(url, json=fee_payload()).json()
    admin.post(f"{MANAGE}/fees/{old['id']}/publish")
    admin.post(f"{MANAGE}/fees/{old['id']}/archive")

    replacement = admin.post(url, json=fee_payload(amount="7200"))
    assert replacement.status_code == 201
    admin.post(f"{MANAGE}/fees/{replacement.json()['id']}/publish")

    assert [fee["amount"] for fee in public_fees(admin, catalog["info"])] == ["7200.000"]


def test_only_one_current_fee_per_year_and_label(admin: TestClient, catalog) -> None:
    url = f"{MANAGE}/programs/{catalog['info']}/fees"
    admin.post(url, json=fee_payload())

    assert admin.post(url, json=fee_payload(amount="7200")).status_code == 409


def test_expired_data_cannot_be_published(admin: TestClient, catalog) -> None:
    expired = {
        "valid_from": (TODAY - timedelta(days=30)).isoformat(),
        "valid_until": (TODAY - timedelta(days=1)).isoformat(),
    }
    fee = admin.post(
        f"{MANAGE}/programs/{catalog['info']}/fees", json=fee_payload(**expired)
    ).json()
    url = f"{MANAGE}/programs/{catalog['prepa']}/admission-requirements"
    admin.put(url, json=requirements_payload(**expired))

    assert admin.post(f"{MANAGE}/fees/{fee['id']}/publish").status_code == 409
    assert admin.post(f"{url}/publish").status_code == 409


def test_payment_terms_are_bounded(admin: TestClient, catalog) -> None:
    response = admin.post(
        f"{MANAGE}/programs/{catalog['info']}/fees", json=fee_payload(payment_terms="x" * 1001)
    )

    assert response.status_code == 422
