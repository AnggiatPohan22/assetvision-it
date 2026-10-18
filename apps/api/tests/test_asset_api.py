import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import csrf_headers, session_headers, sign_in
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.asset_service import update_asset
from app.assets import AssetChangeEvent, AssetIdentifier, AssetUnit
from app.catalog import DeviceCategory, DeviceModel, Environment, Manufacturer
from app.models import Role

ROOT = "/api/v1/assets"


@pytest.fixture()
def headers(client, user, password):
    assert sign_in(client, password).status_code == 200
    return session_headers(client)


@pytest.fixture()
def model(db):
    category = DeviceCategory(code="access-point", name="Access Point")
    maker = Manufacturer(name="Synthetic Manufacturer")
    db.add_all([category, maker])
    db.flush()
    record = DeviceModel(
        category_id=category.id,
        manufacturer_id=maker.id,
        model_name="Synthetic AP",
        environment=Environment.INDOOR,
    )
    db.add(record)
    db.commit()
    return record


def create(client, headers, model, code="AP-001", **values):
    response = client.post(
        ROOT,
        headers=headers,
        json={
            "asset_code": code,
            "device_model_id": str(model.id),
            **values,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def claim(client, headers, asset, raw="aabb.ccdd.eeff", kind="MAC_LAN"):
    return client.post(
        f"{ROOT}/{asset['id']}/identifiers",
        headers=headers,
        json={
            "asset_version": asset["version"],
            "identifier_type": kind,
            "raw_value": raw,
            "source": "MANUAL",
        },
    )


@pytest.mark.parametrize("role", list(Role))
def test_event_history_scoped_paginated_read_only(client, headers, model, db, user, role):
    asset = create(client, headers, model)
    other = create(client, headers, model, "AP-002")
    path = f"{ROOT}/{asset['id']}"
    client.patch(path, headers=headers, json={"version": 1, "notes": "Synthetic diff"})
    user.role = role
    db.commit()
    events_path = path + "/events"
    page = client.get(events_path, params={"page_size": 1}).json()
    assert page["total"] == 2 and page["total_pages"] == 2
    entry = page["items"][0]
    assert entry["asset_id"] == asset["id"] and entry["actor_id"] == str(user.id)
    assert entry["event_type"] == "UPDATE" and entry["recorded_at"]
    assert entry["before_json"]["asset"]["notes"] is None
    assert entry["after_json"]["asset"]["notes"] == "Synthetic diff"
    second = client.get(events_path, params={"page_size": 1, "page": 2}).json()
    assert second["items"][0]["event_type"] == "CREATE"
    assert client.get(events_path, params={"page": 50}).json()["items"] == []
    assert client.get(f"{ROOT}/{other['id']}/events").json()["total"] == 1
    assert client.get(events_path, params={"page": 0}).status_code == 422
    assert client.get(events_path, params={"page_size": 101}).status_code == 422
    assert client.get(events_path, params={"unexpected": "bad"}).status_code == 422
    assert client.get(f"{ROOT}/{uuid.uuid4()}/events").status_code == 404
    for method in (client.post, client.patch, client.delete):
        assert method(events_path, headers=headers).status_code == 405
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 3
    client.cookies.clear()
    assert client.get(events_path).status_code == 401


def test_crud_snapshots_and_archive(client, headers, model, db, user):
    asset = create(
        client,
        headers,
        model,
        " ap-001 ",
        purchase_date="2026-01-01",
        installed_at="2026-01-02T08:00:00+08:00",
    )
    assert asset["asset_code"] == "AP-001" and asset["version"] == 1
    assert asset["lifecycle_status"] == "IN_STOCK" and asset["condition"] == "UNKNOWN"
    path = f"{ROOT}/{asset['id']}"
    assert client.get(path).json() == asset
    assert client.get(path + "/identifiers").json() == []  # SN intentionally absent.
    patched = client.patch(
        path,
        headers=headers,
        json={
            "version": 1,
            "notes": "Label unreadable",
            "condition": "DAMAGED",
            "purchase_date": None,
            "installed_at": None,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] == 2 and patched.json()["purchase_date"] is None
    assert (
        client.patch(path, headers=headers, json={"version": 1, "notes": "stale"}).status_code
        == 409
    )
    archived = client.post(path + "/archive", headers=headers, json={"version": 2})
    assert archived.status_code == 200 and archived.json()["lifecycle_status"] == "ARCHIVED"
    assert (
        client.post(path + "/archive", headers=headers, json={"version": 3}).json()
        == archived.json()
    )
    assert client.delete(path, headers=headers).status_code == 405
    assert (
        client.post(
            ROOT,
            headers=headers,
            json={
                "asset_code": "AP-001",
                "device_model_id": str(model.id),
            },
        ).status_code
        == 409
    )
    events = list(
        db.scalars(
            select(AssetChangeEvent).order_by(AssetChangeEvent.recorded_at, AssetChangeEvent.id)
        )
    )
    by_type = {e.event_type: e for e in events}
    assert set(by_type) == {"CREATE", "UPDATE", "ARCHIVE"} and len(events) == 3
    assert all(e.actor_id == user.id and e.recorded_at for e in events)
    assert by_type["CREATE"].before_json is None
    assert by_type["CREATE"].after_json["asset"]["asset_code"] == "AP-001"
    assert by_type["UPDATE"].before_json["asset"]["notes"] is None
    assert by_type["UPDATE"].after_json["asset"]["notes"] == "Label unreadable"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.OFFICER, Role.VIEWER])
def test_read_and_write_rbac(client, headers, model, db, user, role):
    asset = create(client, headers, model)
    identifier = claim(client, headers, asset).json()["identifier"]
    user.role = role
    db.commit()
    path = f"{ROOT}/{asset['id']}"
    assert client.get(ROOT).status_code == 200
    assert client.get(path).status_code == 200
    assert client.get(path + "/identifiers").status_code == 200
    if role == Role.ADMIN:
        return
    before = db.scalar(select(func.count()).select_from(AssetChangeEvent))
    mutations = [
        ("post", ROOT, {"asset_code": "AP-002", "device_model_id": str(model.id)}),
        ("patch", path, {"version": 2, "notes": "forbidden"}),
        ("post", path + "/archive", {"version": 2}),
        (
            "post",
            path + "/identifiers",
            {
                "asset_version": 2,
                "identifier_type": "HOSTNAME",
                "raw_value": "ap",
                "source": "MANUAL",
            },
        ),
        (
            "patch",
            path + f"/identifiers/{identifier['id']}",
            {"version": 1, "asset_version": 2, "notes": "no"},
        ),
    ]
    for method, target, body in mutations:
        assert getattr(client, method)(target, json=body, headers=headers).status_code == 403
    assert (
        client.delete(
            path + f"/identifiers/{identifier['id']}?version=1&asset_version=2", headers=headers
        ).status_code
        == 403
    )
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == before


def test_anonymous_csrf_inactive_and_revoked(client, model, user, password, db):
    asset = AssetUnit(asset_code="AP-001", device_model_id=model.id)
    db.add(asset)
    db.commit()
    path = f"{ROOT}/{asset.id}"
    anonymous = csrf_headers(client)
    for target in (ROOT, path, path + "/identifiers"):
        assert client.get(target).status_code == 401
    for method, target, body in [
        ("post", ROOT, {"asset_code": "AP-002", "device_model_id": str(model.id)}),
        ("patch", path, {"version": 1, "notes": "no"}),
        ("post", path + "/archive", {"version": 1}),
        (
            "post",
            path + "/identifiers",
            {
                "asset_version": 1,
                "identifier_type": "HOSTNAME",
                "raw_value": "ap",
                "source": "MANUAL",
            },
        ),
        (
            "patch",
            path + f"/identifiers/{uuid.uuid4()}",
            {"version": 1, "asset_version": 1, "notes": "no"},
        ),
    ]:
        assert getattr(client, method)(target, json=body, headers=anonymous).status_code == 401
    assert (
        client.delete(
            path + f"/identifiers/{uuid.uuid4()}?version=1&asset_version=1", headers=anonymous
        ).status_code
        == 401
    )
    assert sign_in(client, password).status_code == 200
    headers = session_headers(client)
    assert client.patch(path, json={"version": 1, "notes": "no"}).status_code == 403
    assert (
        client.post(
            path + "/archive",
            headers={**headers, "Origin": "https://evil.invalid"},
            json={"version": 1},
        ).status_code
        == 403
    )
    user.is_active = False
    db.commit()
    assert client.get(path).status_code == 401
    user.is_active = True
    db.commit()
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get(path).status_code == 401
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"asset_code": "changed"},
        {"id": str(uuid.uuid4())},
        {"device_model_id": None},
        {"version": True},
        {"version": 0},
        {"version": 2_147_483_648},
        {"notes": "x" * 4001},
        {"notes": "bad\u0000"},
        {"condition": None},
        {"condition": "broken"},
        {"lifecycle_status": "lost"},
        {"current_location": "room"},
        {"installed_at": "2026-01-01T00:00:00"},
        {"purchase_date": "not-a-date"},
    ],
)
def test_patch_validation(client, headers, model, changes, db):
    asset = create(client, headers, model)
    assert (
        client.patch(
            f"{ROOT}/{asset['id']}", headers=headers, json={"version": 1, **changes}
        ).status_code
        == 422
    )
    assert client.get(f"{ROOT}/{asset['id']}").json()["version"] == 1
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 1


def test_references_queries_and_empty_patch(client, headers, model, db):
    asset = create(client, headers, model)
    path = f"{ROOT}/{asset['id']}"
    assert client.patch(path, headers=headers, json={"version": 1}).status_code == 422
    assert (
        client.post(
            ROOT,
            headers=headers,
            json={"asset_code": "AP-002", "device_model_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )
    model.is_active = False
    db.commit()
    assert (
        client.post(
            ROOT, headers=headers, json={"asset_code": "AP-002", "device_model_id": str(model.id)}
        ).status_code
        == 409
    )
    # Historical reference remains readable and editable without reassigning its model.
    assert (
        client.patch(path, headers=headers, json={"version": 1, "notes": "history"}).status_code
        == 200
    )
    for suffix in ("page=0", "page_size=101", "unknown=x", "status=bad", "model_id=no"):
        assert client.get(ROOT + "?" + suffix).status_code == 422
    assert client.get(ROOT + "/not-a-uuid").status_code == 422
    assert client.get(ROOT + f"/{uuid.uuid4()}").status_code == 404


def test_search_pagination_and_soft_deleted_claims(client, headers, model):
    first = create(client, headers, model)
    second = create(client, headers, model, "AP-002", lifecycle_status="IN_USE")
    claim(client, headers, first, "SN-123", "SERIAL_NUMBER")
    mac = claim(client, headers, second).json()
    for search, expected in [
        ("ap-001", first["id"]),
        ("sn-123", first["id"]),
        ("aabbccddeeff", second["id"]),
        ("aa-bb-cc-dd-ee-ff", second["id"]),
    ]:
        result = client.get(ROOT, params={"search": search}).json()
        assert [i["id"] for i in result["items"]] == [expected] and result["total"] == 1
    assert (
        client.get(ROOT, params={"model_id": str(model.id), "status": "IN_USE"}).json()["total"]
        == 1
    )
    assert client.get(ROOT + "?page_size=1&page=2").json()["items"][0]["id"] == second["id"]
    assert client.get(ROOT + "?page=10").json()["items"] == []
    assert client.get(ROOT + "?search=%25").json()["total_pages"] == 0
    assert client.get(ROOT + "?model_id=" + str(uuid.uuid4())).json()["total"] == 0
    removed = client.delete(
        f"{ROOT}/{second['id']}/identifiers/{mac['identifier']['id']}?version=1&asset_version=2",
        headers=headers,
    )
    assert removed.status_code == 200
    assert client.get(ROOT + "?search=aabbccddeeff").json()["total"] == 0


def test_identifier_lifecycle_collision_and_audit(client, headers, model, db):
    first = create(client, headers, model)
    second = create(client, headers, model, "AP-002")
    response = claim(client, headers, first)
    assert response.status_code == 201, response.text
    result = response.json()
    identifier = result["identifier"]
    assert result["asset_version"] == 2 and identifier["version"] == 1
    assert (
        identifier["raw_value"] == "aabb.ccdd.eeff"
        and identifier["normalized_value"] == "AA:BB:CC:DD:EE:FF"
    )
    assert identifier["collision_asset_ids"] == []
    assert claim(client, headers, {**first, "version": 2}).status_code == 409
    collided = claim(client, headers, second).json()
    assert collided["identifier"]["collision_asset_ids"] == [first["id"]]
    path = f"{ROOT}/{first['id']}/identifiers"
    assert client.get(path).json()[0]["collision_asset_ids"] == [second["id"]]
    detail = path + "/" + identifier["id"]
    updated = client.patch(
        detail,
        headers=headers,
        json={
            "version": 1,
            "asset_version": 2,
            "raw_value": "112233445566",
            "verification_status": "VERIFIED",
            "notes": "checked",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["asset_version"] == 3
    assert updated.json()["identifier"]["normalized_value"] == "11:22:33:44:55:66"
    assert (
        client.patch(
            detail, headers=headers, json={"version": 1, "asset_version": 3, "notes": "stale"}
        ).status_code
        == 409
    )
    assert client.delete(detail + "?version=2&asset_version=2", headers=headers).status_code == 409
    assert (
        client.patch(
            f"{ROOT}/{second['id']}/identifiers/{identifier['id']}",
            headers=headers,
            json={"version": 2, "asset_version": 2, "notes": "wrong owner"},
        ).status_code
        == 404
    )
    removed = client.delete(detail + "?version=2&asset_version=3", headers=headers)
    assert removed.status_code == 200 and removed.json()["asset_version"] == 4
    assert removed.json()["identifier"]["deleted_at"]
    assert client.get(path).json() == []
    assert (
        client.patch(
            detail, headers=headers, json={"version": 3, "asset_version": 4, "notes": "restore"}
        ).status_code
        == 409
    )
    assert (
        client.delete(detail + "?version=3&asset_version=4", headers=headers).json()[
            "asset_version"
        ]
        == 4
    )
    replacement = claim(client, headers, {**first, "version": 4}, "112233445566")
    assert (
        replacement.status_code == 201
        and replacement.json()["identifier"]["id"] != identifier["id"]
    )
    events = list(
        db.scalars(
            select(AssetChangeEvent).where(AssetChangeEvent.asset_id == uuid.UUID(first["id"]))
        )
    )
    assert {e.event_type for e in events} == {
        "CREATE",
        "IDENTIFIER_ADD",
        "IDENTIFIER_UPDATE",
        "IDENTIFIER_REMOVE",
    }
    update = next(e for e in events if e.event_type == "IDENTIFIER_UPDATE")
    assert update.before_json["identifier"]["raw_value"] == "aabb.ccdd.eeff"
    assert update.after_json["identifier"]["raw_value"] == "112233445566"
    assert db.get(AssetIdentifier, uuid.UUID(identifier["id"])).deleted_at is not None


@pytest.mark.parametrize(
    "raw,kind",
    [
        ("UNKNOWN", "SERIAL_NUMBER"),
        ("", "HOSTNAME"),
        ("no-mac", "MAC_LAN"),
        ("x\n", "HOSTNAME"),
        ("x" * 256, "MANAGEMENT_ID"),
    ],
)
def test_identifier_validation(client, headers, model, raw, kind):
    asset = create(client, headers, model)
    assert claim(client, headers, asset, raw, kind).status_code == 422
    assert client.get(f"{ROOT}/{asset['id']}").json()["version"] == 1


def test_identifier_merged_validation_and_parent_version(client, headers, model):
    asset = create(client, headers, model)
    added = claim(client, headers, asset, " Host-A ", "HOSTNAME").json()
    path = f"{ROOT}/{asset['id']}"
    detail = path + "/identifiers/" + added["identifier"]["id"]
    assert added["identifier"]["normalized_value"] == "host-a"
    assert (
        client.patch(path, headers=headers, json={"version": 1, "notes": "old form"}).status_code
        == 409
    )
    assert (
        client.patch(
            detail,
            headers=headers,
            json={"version": 1, "asset_version": 2, "identifier_type": "MAC_LAN"},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            detail,
            headers=headers,
            json={"version": 1, "asset_version": 2, "normalized_value": "forged"},
        ).status_code
        == 422
    )
    assert client.get(path).json()["version"] == 2
    assert client.delete(detail, headers=headers).status_code == 422


@pytest.mark.parametrize(
    "values",
    [
        {"asset_code": ""},
        {"asset_code": "bad/code"},
        {"asset_code": "x" * 51},
        {"serial_number": "UNKNOWN"},
        {"version": 1},
        {"source": "MANUAL"},
        {"device_model_id": "invalid"},
        {"condition": None},
    ],
)
def test_create_rejects_invalid_fields(client, headers, model, values, db):
    response = client.post(
        ROOT,
        headers=headers,
        json={
            "asset_code": "AP-001",
            "device_model_id": str(model.id),
            **values,
        },
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(AssetUnit)) == 0
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 0


def test_reassign_model_patch_archive_and_identifier_duplicate_update(client, headers, model, db):
    asset = create(client, headers, model)
    path = f"{ROOT}/{asset['id']}"
    unknown = client.patch(
        path, headers=headers, json={"version": 1, "device_model_id": str(uuid.uuid4())}
    )
    assert unknown.status_code == 422
    other_model = DeviceModel(
        category_id=model.category_id,
        manufacturer_id=model.manufacturer_id,
        model_name="Synthetic replacement",
        environment=Environment.INDOOR,
        is_active=False,
    )
    db.add(other_model)
    db.commit()
    assert (
        client.patch(
            path, headers=headers, json={"version": 1, "device_model_id": str(other_model.id)}
        ).status_code
        == 409
    )
    other_model.is_active = True
    db.commit()
    updated = client.patch(
        path,
        headers=headers,
        json={"version": 1, "device_model_id": str(other_model.id), "lifecycle_status": "ARCHIVED"},
    )
    assert updated.status_code == 200 and updated.json()["version"] == 2
    archived = db.scalar(select(AssetChangeEvent).where(AssetChangeEvent.event_type == "ARCHIVE"))
    assert archived.before_json["asset"]["device_model_id"] == str(model.id)
    assert archived.after_json["asset"]["device_model_id"] == str(other_model.id)
    one = claim(client, headers, {**asset, "version": 2}, "first", "HOSTNAME").json()
    two = claim(client, headers, {**asset, "version": 3}, "second", "HOSTNAME").json()
    identifier_path = path + "/identifiers/" + two["identifier"]["id"]
    duplicate = client.patch(
        identifier_path,
        headers=headers,
        json={"version": 1, "asset_version": 4, "raw_value": " FIRST "},
    )
    assert duplicate.status_code == 409
    assert client.get(path).json()["version"] == 4
    # No normalization collision across types, and no removal/reparenting through PATCH.
    assert (
        claim(client, headers, {**asset, "version": 4}, "first", "MANAGEMENT_ID").status_code == 201
    )
    for changes in (
        {"asset_id": str(uuid.uuid4())},
        {"deleted_at": "2026-01-01T00:00:00Z"},
        {"source": None},
        {"identifier_type": "UNKNOWN"},
    ):
        assert (
            client.patch(
                identifier_path, headers=headers, json={"version": 1, "asset_version": 5, **changes}
            ).status_code
            == 422
        )
    assert one["identifier"]["asset_id"] == asset["id"]


def test_concurrent_identifier_and_asset_postgres(client, headers, model, factory, db, user):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    from app.asset_service import mutate_identifier
    from app.assets import IdentifierSource, IdentifierType
    from app.models import User

    asset = create(client, headers, model)
    barrier = Barrier(2)
    actor_id = user.id

    def change(kind):
        with factory() as session:
            actor = session.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                if kind == "asset":
                    return update_asset(
                        session, uuid.UUID(asset["id"]), 1, {"notes": "concurrent"}, actor
                    ).version
                record, _ = mutate_identifier(
                    session,
                    uuid.UUID(asset["id"]),
                    1,
                    {
                        "identifier_type": IdentifierType.HOSTNAME,
                        "raw_value": "test-ap",
                        "source": IdentifierSource.MANUAL,
                    },
                    actor,
                )
                return record.version
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(change, ["asset", "identifier"])) == [2, 409]
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 2


@pytest.mark.parametrize("operation", ["create", "update", "archive", "add", "patch", "remove"])
def test_audit_failure_rolls_back_all_mutations(client, headers, model, db, operation):
    asset = create(client, headers, model)
    identifier = claim(client, headers, asset).json()["identifier"]
    before = client.get(f"{ROOT}/{asset['id']}").json()
    before_claims = client.get(f"{ROOT}/{asset['id']}/identifiers").json()
    events_before = db.scalar(select(func.count()).select_from(AssetChangeEvent))

    def reject(mapper, connection, target):
        raise IntegrityError("synthetic audit failure", {}, None)

    event.listen(AssetChangeEvent, "before_insert", reject)
    try:
        path = f"{ROOT}/{asset['id']}"
        detail = path + "/identifiers/" + identifier["id"]
        if operation == "create":
            response = client.post(
                ROOT,
                headers=headers,
                json={"asset_code": "AP-002", "device_model_id": str(model.id)},
            )
        elif operation == "update":
            response = client.patch(path, headers=headers, json={"version": 2, "notes": "rollback"})
        elif operation == "archive":
            response = client.post(path + "/archive", headers=headers, json={"version": 2})
        elif operation == "add":
            response = claim(client, headers, {**asset, "version": 2}, "new", "HOSTNAME")
        elif operation == "patch":
            response = client.patch(
                detail,
                headers=headers,
                json={"version": 1, "asset_version": 2, "notes": "rollback"},
            )
        else:
            response = client.delete(detail + "?version=1&asset_version=2", headers=headers)
        assert response.status_code == 409
    finally:
        event.remove(AssetChangeEvent, "before_insert", reject)
    assert client.get(path).json() == before
    assert client.get(path + "/identifiers").json() == before_claims
    assert client.get(ROOT).json()["total"] == 1
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == events_before


def test_concurrent_updates_postgres(client, headers, model, factory, db, user):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    asset = create(client, headers, model)
    barrier = Barrier(2)
    actor_id = user.id

    def change(note):
        with factory() as session:
            from app.models import User

            actor = session.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                return update_asset(
                    session, uuid.UUID(asset["id"]), 1, {"notes": note}, actor
                ).version
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(change, ["first", "second"])) == [2, 409]
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 2
    assert client.get(f"{ROOT}/{asset['id']}").json()["version"] == 2
