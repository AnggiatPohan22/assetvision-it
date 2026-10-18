import uuid
from typing import Any

import pytest
from conftest import csrf_headers, session_headers, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog import DeviceCategory, DeviceModel, DeviceReferenceImage, Environment, Manufacturer
from app.catalog_schemas import ModelPatch
from app.catalog_service import update_record
from app.models import AuditEvent, Role, User

ROOT = "/api/v1"
RESOURCES = ("device-categories", "manufacturers", "device-models")


@pytest.fixture()
def headers(client: TestClient, user: User, password: str) -> dict[str, str]:
    assert sign_in(client, password).status_code == 200
    return session_headers(client)


@pytest.fixture()
def records(db: Session) -> dict[str, Any]:
    category = DeviceCategory(code="access-point", name="Access Point")
    maker = Manufacturer(name="Ruijie")
    db.add_all([category, maker])
    db.flush()
    model = DeviceModel(
        category_id=category.id,
        manufacturer_id=maker.id,
        model_name="AP680-L",
        environment=Environment.OUTDOOR,
        aliases=["Outdoor Access Point"],
        specs={"bands": ["2.4GHz", "5GHz"]},
    )
    db.add(model)
    db.commit()
    return dict(zip(RESOURCES, (category, maker, model), strict=True))


def payload(resource: str, records: dict[str, Any]) -> dict[str, Any]:
    if resource == "device-categories":
        return {"code": "printer", "name": "Printer"}
    if resource == "manufacturers":
        return {"name": "MikroTik", "website": "https://example.invalid"}
    return {
        "category_id": str(records["device-categories"].id),
        "manufacturer_id": str(records["manufacturers"].id),
        "model_name": " AP  681-L ",
        "environment": "both",
        "aliases": [" Another   AP "],
        "specs": {"ports": 4, "poe": True},
    }


@pytest.mark.parametrize("resource", RESOURCES)
def test_admin_create_detail_update(
    client: TestClient,
    headers,
    records,
    resource: str,
    db: Session,
    user: User,
) -> None:
    response = client.post(f"{ROOT}/{resource}", json=payload(resource, records), headers=headers)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["version"] == 1 and created["is_active"] is True
    assert created["created_by"] == created["updated_by"] == str(user.id)
    assert created["created_at"] and created["updated_at"]
    if resource == "device-models":
        assert created["model_name"] == "AP 681-L" and created["aliases"] == ["Another AP"]
    path = f"{ROOT}/{resource}/{created['id']}"
    assert client.get(path).json() == created
    changes = {"version": 1, "is_active": False}
    if resource != "manufacturers":
        changes["description"] = "Edited"
    patched = client.patch(path, json=changes, headers=headers)
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] == 2 and patched.json()["is_active"] is False
    assert patched.json()["id"] == created["id"]
    if resource != "manufacturers":
        cleared = client.patch(path, json={"version": 2, "description": None}, headers=headers)
        assert cleared.status_code == 200 and cleared.json()["description"] is None
    audits = list(db.scalars(select(AuditEvent).where(AuditEvent.action.like("catalog_%"))))
    assert {audit.action for audit in audits} == {"catalog_create", "catalog_update"}
    assert all(audit.actor_id == user.id for audit in audits)


@pytest.mark.parametrize("resource", RESOURCES)
@pytest.mark.parametrize("role", [Role.ADMIN, Role.OFFICER, Role.VIEWER])
def test_all_roles_read(client, headers, records, db, user, resource, role) -> None:
    user.role = role
    db.commit()
    response = client.get(f"{ROOT}/{resource}")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert client.get(f"{ROOT}/{resource}/{records[resource].id}").status_code == 200


@pytest.mark.parametrize("resource", RESOURCES)
@pytest.mark.parametrize("role", [Role.OFFICER, Role.VIEWER])
def test_nonadmins_cannot_write(client, headers, records, db, user, resource, role) -> None:
    user.role = role
    db.commit()
    path = f"{ROOT}/{resource}"
    assert client.post(path, json=payload(resource, records), headers=headers).status_code == 403
    detail = f"{path}/{records[resource].id}"
    assert (
        client.patch(detail, json={"version": 1, "is_active": False}, headers=headers).status_code
        == 403
    )
    if resource == "device-models":
        assert (
            client.post(detail + "/archive", json={"version": 1}, headers=headers).status_code
            == 403
        )
    assert (
        db.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("catalog_%"))
        )
        == 0
    )


@pytest.mark.parametrize("resource", RESOURCES)
def test_anonymous_rejected(client, records, resource) -> None:
    headers = csrf_headers(client)
    path = f"{ROOT}/{resource}"
    assert client.get(path).status_code == 401
    assert client.get(f"{path}/{records[resource].id}").status_code == 401
    assert client.post(path, json=payload(resource, records), headers=headers).status_code == 401
    detail = f"{path}/{records[resource].id}"
    assert (
        client.patch(detail, json={"version": 1, "is_active": False}, headers=headers).status_code
        == 401
    )
    if resource == "device-models":
        assert (
            client.post(detail + "/archive", json={"version": 1}, headers=headers).status_code
            == 401
        )


@pytest.mark.parametrize("resource", RESOURCES)
def test_duplicates_and_update_conflicts(client, headers, records, resource) -> None:
    data = payload(resource, records)
    if resource == "device-categories":
        data["code"] = " ACCESS-POINT "
    elif resource == "manufacturers":
        data["name"] = " rUiJiE "
    else:
        data["model_name"] = "\t ap680-l  "
    response = client.post(f"{ROOT}/{resource}", json=data, headers=headers)
    assert response.status_code == 409 and isinstance(response.json()["detail"], str)
    assert "INSERT" not in response.text and "constraint" not in response.text
    created = client.post(
        f"{ROOT}/{resource}", json=payload(resource, records), headers=headers
    ).json()
    changes = {"version": 1}
    key = {"device-categories": "code", "manufacturers": "name", "device-models": "model_name"}[
        resource
    ]
    changes[key] = data[key]
    assert (
        client.patch(
            f"{ROOT}/{resource}/{created['id']}", json=changes, headers=headers
        ).status_code
        == 409
    )


def test_model_different_manufacturer_allowed(client, headers, records) -> None:
    maker = client.post(
        f"{ROOT}/manufacturers", json={"name": "Other Maker"}, headers=headers
    ).json()
    data = payload("device-models", records) | {
        "model_name": "AP680-L",
        "manufacturer_id": maker["id"],
    }
    assert client.post(f"{ROOT}/device-models", json=data, headers=headers).status_code == 201


@pytest.mark.parametrize("resource", RESOURCES)
def test_missing_invalid_ids_and_delete_not_supported(client, headers, records, resource) -> None:
    path = f"{ROOT}/{resource}"
    missing = f"{path}/{uuid.uuid4()}"
    assert client.get(missing).status_code == 404
    assert (
        client.patch(missing, json={"version": 1, "is_active": False}, headers=headers).status_code
        == 404
    )
    assert client.get(path + "/not-a-uuid").status_code == 422
    assert client.delete(f"{path}/{records[resource].id}", headers=headers).status_code == 405
    if resource == "device-models":
        assert (
            client.post(missing + "/archive", json={"version": 1}, headers=headers).status_code
            == 404
        )


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"version": 1},
        {"model_name": "New"},
        {"version": 0, "model_name": "New"},
        {"version": True, "model_name": "New"},
        {"version": 1, "model_name": None},
        {"version": 1, "aliases": None},
        {"version": 1, "specs": None},
        {"version": 1, "is_active": None},
        {"version": 1, "created_by": str(uuid.UUID(int=0))},
    ],
)
def test_patch_validation(client, headers, records, changes) -> None:
    response = client.patch(
        f"{ROOT}/device-models/{records['device-models'].id}", json=changes, headers=headers
    )
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])


@pytest.mark.parametrize(
    "changes",
    [
        {"model_name": " \n "},
        {"model_name": "x" * 201},
        {"environment": "unknown"},
        {"aliases": ["AP", " ap "]},
        {"aliases": ["a"] * 21},
        {"specs": {"nested": {"x": 1}}},
        {"specs": {"bad key": "x"}},
        {"specs": {"x": "a" * 501}},
        {"specs": {"x": [1] * 21}},
        {"specs": {str(i): 1 for i in range(33)}},
        {"specs": {"x": 10**13}},
        {"description": "x\u0000y"},
        {"id": str(uuid.UUID(int=0))},
        {"is_active": "false"},
        {"specs": {"x": ["a" * 500] * 20}},
    ],
)
def test_model_validation(client, headers, records, changes) -> None:
    data = payload("device-models", records) | changes
    response = client.post(f"{ROOT}/device-models", json=data, headers=headers)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "resource,data",
    [
        ("device-categories", {"code": "invalid code", "name": "Test"}),
        ("device-categories", {"code": "ok", "name": "  "}),
        ("manufacturers", {"name": "  "}),
        ("manufacturers", {"name": "Test", "website": "file:///etc/passwd"}),
        ("manufacturers", {"name": "Test", "website": "https://user:password@example.invalid"}),
    ],
)
def test_master_validation(client, headers, resource, data) -> None:
    assert client.post(f"{ROOT}/{resource}", json=data, headers=headers).status_code == 422


@pytest.mark.parametrize(
    "key,resource", [("category_id", "device-categories"), ("manufacturer_id", "manufacturers")]
)
def test_missing_inactive_references(client, headers, records, key, resource) -> None:
    data = payload("device-models", records)
    assert (
        client.post(
            f"{ROOT}/device-models", json=data | {key: str(uuid.uuid4())}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{ROOT}/{resource}/{records[resource].id}",
            json={"version": 1, "is_active": False},
            headers=headers,
        ).status_code
        == 200
    )
    assert client.post(f"{ROOT}/device-models", json=data, headers=headers).status_code == 409


@pytest.mark.parametrize("resource", RESOURCES)
def test_stale_version_rejected(client, headers, records, resource) -> None:
    path = f"{ROOT}/{resource}/{records[resource].id}"
    assert (
        client.patch(path, json={"version": 1, "is_active": False}, headers=headers).status_code
        == 200
    )
    assert (
        client.patch(path, json={"version": 1, "is_active": True}, headers=headers).status_code
        == 409
    )
    assert client.get(path).json()["is_active"] is False


def test_archive_retains_history_and_is_idempotent(client, headers, records, db, user) -> None:
    model = records["device-models"]
    image = DeviceReferenceImage(
        device_model_id=model.id,
        uploaded_by=user.id,
        storage_key="synthetic/reference.png",
        sha256="a" * 64,
        mime_type="image/png",
        byte_size=100,
    )
    db.add(image)
    db.commit()
    path = f"{ROOT}/device-models/{model.id}"
    archived = client.post(path + "/archive", json={"version": 1}, headers=headers)
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False and archived.json()["version"] == 2
    assert db.get(DeviceReferenceImage, image.id).device_model_id == model.id
    assert client.get(path).json()["id"] == str(model.id)
    assert client.post(path + "/archive", json={"version": 1}, headers=headers).status_code == 409
    assert (
        client.post(path + "/archive", json={"version": 2}, headers=headers).json()["version"] == 2
    )
    assert (
        len(list(db.scalars(select(AuditEvent).where(AuditEvent.action == "catalog_archive")))) == 1
    )
    data = payload("device-models", records) | {"model_name": model.model_name}
    assert client.post(f"{ROOT}/device-models", json=data, headers=headers).status_code == 409


def test_filter_search_pagination(client, headers, records) -> None:
    path = f"{ROOT}/device-models"
    for name in ("Alpha", "Beta", "Gamma"):
        data = payload("device-models", records) | {"model_name": name}
        assert client.post(path, json=data, headers=headers).status_code == 201
    page1 = client.get(path, params={"page_size": 2}).json()
    page2 = client.get(path, params={"page": 2, "page_size": 2}).json()
    assert page1["total"] == 4 and page1["total_pages"] == 2
    assert [item["model_name"] for item in page1["items"] + page2["items"]] == [
        "Alpha",
        "AP680-L",
        "Beta",
        "Gamma",
    ]
    assert client.get(path, params={"page_size": 2}).json() == page1
    assert client.get(path, params={"page": 9}).json()["items"] == []
    for search, total in (
        ("outdoor", 1),
        ("ruijie", 4),
        ("beta", 1),
        ("%", 0),
        ("_", 0),
        ("' OR 1=1--", 0),
    ):
        assert client.get(path, params={"search": search}).json()["total"] == total
    filters = {
        "category_id": str(records["device-categories"].id),
        "manufacturer_id": str(records["manufacturers"].id),
        "environment": "outdoor",
        "is_active": True,
    }
    assert client.get(path, params=filters).json()["total"] == 1
    assert client.get(path, params={"category_id": str(uuid.uuid4())}).json()["total"] == 0
    assert client.get(path, params={"is_active": False}).json()["total"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=101",
        "page_size=0",
        "page=1000001",
        "category_id=bad",
        "environment=bad",
        "search=" + "x" * 201,
        "unknown=true",
    ],
)
def test_list_validation(client, headers, query) -> None:
    assert client.get(f"{ROOT}/device-models?{query}").status_code == 422


def test_csrf_required_for_catalog_mutations(client, headers, records) -> None:
    path = f"{ROOT}/device-models/{records['device-models'].id}"
    assert client.patch(path, json={"version": 1, "is_active": False}).status_code == 403
    assert client.post(path + "/archive", json={"version": 1}).status_code == 403
    foreign = headers | {"Origin": "http://evil.example"}
    assert (
        client.post(
            f"{ROOT}/device-models", json=payload("device-models", records), headers=foreign
        ).status_code
        == 403
    )


def test_audit_failure_rolls_back_create(client, headers, records, db) -> None:
    def fail_audit(mapper, connection, target) -> None:
        if target.action.startswith("catalog_"):
            raise IntegrityError("synthetic failure", {}, Exception())

    event.listen(AuditEvent, "before_insert", fail_audit)
    try:
        response = client.post(
            f"{ROOT}/device-models", json=payload("device-models", records), headers=headers
        )
    finally:
        event.remove(AuditEvent, "before_insert", fail_audit)
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(DeviceModel)) == 1


def test_database_race_returns_conflict(factory, records, db, user) -> None:
    from fastapi import HTTPException

    current = records["device-models"]
    with factory() as other:
        stale = other.get(DeviceModel, current.id)
        current.description = "Approved change"
        db.commit()
        with pytest.raises(HTTPException) as caught:
            update_record(other, stale, ModelPatch(version=1, description="Stale change"), user)
        assert caught.value.status_code == 409
    db.expire_all()
    assert current.description == "Approved change"


def test_noop_update_checks_and_increments_version(client, headers, records) -> None:
    path = f"{ROOT}/device-models/{records['device-models'].id}"
    response = client.patch(path, json={"version": 1, "model_name": "AP680-L"}, headers=headers)
    assert response.status_code == 200 and response.json()["version"] == 2
    assert (
        client.patch(path, json={"version": 1, "description": "Stale"}, headers=headers).status_code
        == 409
    )


def test_reactivate_requires_active_parents_and_clear_website(client, headers, records) -> None:
    model = f"{ROOT}/device-models/{records['device-models'].id}"
    maker = f"{ROOT}/manufacturers/{records['manufacturers'].id}"
    assert client.post(model + "/archive", json={"version": 1}, headers=headers).status_code == 200
    assert (
        client.patch(
            maker, json={"version": 1, "is_active": False, "website": None}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.patch(model, json={"version": 2, "is_active": True}, headers=headers).status_code
        == 409
    )
    # Historical references remain editable without silently reactivating either entity.
    edited = client.patch(model, json={"version": 2, "description": "Historical"}, headers=headers)
    assert edited.status_code == 200 and edited.json()["is_active"] is False
    assert client.get(f"{ROOT}/device-models?is_active=false").json()["total"] == 1
    assert client.get(f"{ROOT}/device-models?is_active=true").json()["total"] == 0


@pytest.mark.parametrize("resource", ["device-categories", "manufacturers"])
def test_master_filters_and_pagination(client, headers, records, resource) -> None:
    path = f"{ROOT}/{resource}"
    assert client.post(path, json=payload(resource, records), headers=headers).status_code == 201
    page = client.get(path, params={"page_size": 1}).json()
    assert page["total"] == 2 and page["total_pages"] == 2 and len(page["items"]) == 1
    assert (
        client.get(path, params={"page_size": 1, "page": 2}).json()["items"][0]["id"]
        != page["items"][0]["id"]
    )
    search = "ACCESS" if resource == "device-categories" else "rUiJiE"
    assert client.get(path, params={"search": search}).json()["total"] == 1
    assert client.get(path, params={"is_active": False}).json()["items"] == []


def test_disabled_session_cannot_write(client, headers, records, db, user) -> None:
    user.is_active = False
    db.commit()
    assert client.get(f"{ROOT}/device-models").status_code == 401
    assert (
        client.post(
            f"{ROOT}/device-models", json=payload("device-models", records), headers=headers
        ).status_code
        == 401
    )


def test_unicode_alias_search_and_tied_pagination(client, headers, records) -> None:
    path = f"{ROOT}/device-models"
    maker = client.post(f"{ROOT}/manufacturers", json={"name": "Synthetic"}, headers=headers).json()
    data = payload("device-models", records) | {
        "manufacturer_id": maker["id"],
        "model_name": "AP680-L",
        "aliases": ["Perangkat 日本語"],
    }
    assert client.post(path, json=data, headers=headers).status_code == 201
    assert client.get(path, params={"search": "日本語"}).json()["total"] == 1
    first = client.get(path, params={"page_size": 1}).json()["items"][0]["id"]
    second = client.get(path, params={"page_size": 1, "page": 2}).json()["items"][0]["id"]
    assert first != second and first < second


@pytest.mark.parametrize(
    "changes",
    [
        {"model_name": "invalid\ud800"},
        {"aliases": ["invalid\ud800"]},
        {"specs": {"x": 10**1000}},
        {"specs": {"x": "invalid\ud800"}},
    ],
)
def test_unrepresentable_values_are_validation_errors(client, headers, records, changes) -> None:
    import json

    body = json.dumps(payload("device-models", records) | changes)
    response = client.post(
        f"{ROOT}/device-models",
        content=body,
        headers=headers | {"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_search_null_byte_rejected(client, headers) -> None:
    assert client.get(f"{ROOT}/device-models", params={"search": "bad\x00query"}).status_code == 422


def test_catalog_openapi_documents_contract(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for resource in RESOURCES:
        assert {"get", "post"} <= paths[f"{ROOT}/{resource}"].keys()
        assert {"get", "patch"} <= paths[f"{ROOT}/{resource}/{{record_id}}"].keys()
        for status in ("401", "403", "404", "409", "422"):
            assert status in paths[f"{ROOT}/{resource}"]["post"]["responses"]
    assert "post" in paths[f"{ROOT}/device-models/{{record_id}}/archive"]
    assert f"{ROOT}/device-models/{{model_id}}/reference-images" in paths


@pytest.mark.parametrize("resource", RESOURCES)
def test_audit_exact_payload_and_failed_writes_are_not_success_events(
    client, headers, records, db, user, resource
) -> None:
    path = f"{ROOT}/{resource}"
    data = payload(resource, records)
    created = client.post(path, json=data, headers=headers).json()
    record_path = f"{path}/{created['id']}"
    assert client.post(path, json=data, headers=headers).status_code == 409
    assert (
        client.patch(
            record_path, json={"version": 1, "is_active": False}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.patch(
            record_path, json={"version": 1, "is_active": True}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.patch(
            record_path, json={"version": 2, "is_active": None}, headers=headers
        ).status_code
        == 422
    )
    user.role = Role.OFFICER
    db.commit()
    assert (
        client.patch(
            record_path, json={"version": 2, "is_active": True}, headers=headers
        ).status_code
        == 403
    )
    audits = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action.like("catalog_%"))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )
    assert len(audits) == 2
    assert {(a.action, a.details["version"]) for a in audits} == {
        ("catalog_create", "1"),
        ("catalog_update", "2"),
    }
    table = {
        "device-categories": "device_categories",
        "manufacturers": "manufacturers",
        "device-models": "device_models",
    }[resource]
    for audit in audits:
        assert audit.actor_id == user.id and audit.created_at is not None
        assert audit.details == {
            "table": table,
            "id": created["id"],
            "version": "1" if audit.action == "catalog_create" else "2",
        }


@pytest.mark.parametrize("action", ["update", "archive"])
def test_audit_failure_rolls_back_update_and_archive(client, headers, records, db, action):
    model = records["device-models"]

    def fail(mapper, connection, target):
        if target.action == f"catalog_{action}":
            raise IntegrityError("synthetic audit failure", {}, Exception())

    event.listen(AuditEvent, "before_insert", fail)
    try:
        path = f"{ROOT}/device-models/{model.id}"
        response = (
            client.post(path + "/archive", json={"version": 1}, headers=headers)
            if action == "archive"
            else client.patch(
                path, json={"version": 1, "description": "must rollback"}, headers=headers
            )
        )
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    assert response.status_code == 409
    actual = client.get(path).json()
    assert actual["version"] == 1 and actual["is_active"] and actual["description"] is None
    assert (
        db.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("catalog_%"))
        )
        == 0
    )


@pytest.mark.parametrize("resource", RESOURCES)
def test_pagination_empty_boundaries_and_no_duplicate_rows(client, headers, records, resource):
    path = f"{ROOT}/{resource}"
    for index in range(5):
        data = payload(resource, records)
        if resource == "device-categories":
            data |= {"code": f"test-{index}", "name": "Same display name"}
        elif resource == "manufacturers":
            data |= {"name": f"Maker {index}"}
        else:
            data |= {"model_name": f"Model {index}", "aliases": ["find", "find twice"]}
        assert client.post(path, json=data, headers=headers).status_code == 201
    collected = []
    for page in (1, 2, 3):
        query = {"page": page, "page_size": 2}
        result = client.get(path, params=query).json()
        assert result == client.get(path, params=query).json()
        assert result["total"] == 6 and result["total_pages"] == 3
        assert result["page"] == page and result["page_size"] == 2
        collected.extend(item["id"] for item in result["items"])
    assert len(set(collected)) == 6
    for query in ({"search": "no matching synthetic record"}, {"is_active": False}):
        result = client.get(path, params=query).json()
        assert result["items"] == [] and result["total"] == result["total_pages"] == 0
    result = client.get(path, params={"page": 1_000_000, "page_size": 100}).json()
    assert result["items"] == [] and result["total"] == 6 and result["total_pages"] == 1
    for query in ({"page": -1}, {"page_size": 101}, {"page_size": 0}, {"page": 1_000_001}):
        assert client.get(path, params=query).status_code == 422
    if resource == "device-models":
        result = client.get(path, params={"search": "find", "page_size": 2}).json()
        assert result["total"] == 5 and result["total_pages"] == 3
