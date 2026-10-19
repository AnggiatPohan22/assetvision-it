"""Task 2-02: atomic placement, protected history, migrations and concurrent writers."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import test_asset_api as asset_api
from alembic import command
from alembic.config import Config
from conftest import session_headers, sign_in
from fastapi import HTTPException
from sqlalchemy import event, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from test_asset_api import create
from test_asset_csv import fingerprint
from test_locations import create as create_location

from app.asset_location_service import initial_placement
from app.asset_locations import AssetLocationEvent
from app.asset_service import update_asset
from app.assets import AssetUnit
from app.location_schemas import LocationPatch
from app.location_service import save_location
from app.models import Role, User
from app.seed_assets import seed_assets

catalog_model = asset_api.model


@pytest.fixture()
def headers(client, user, password):
    assert sign_in(client, password).status_code == 200
    return session_headers(client)


@pytest.fixture()
def setup(client, headers, catalog_model):
    asset = create(client, headers, catalog_model, "AP-003")
    location = create_location(client, headers, "villa-1", kind="BUILDING")
    return asset, location


def place(client, headers, setup, **changes):
    asset, location = setup
    return client.post(
        f"/api/v1/assets/{asset['id']}/initial-placement",
        headers=headers,
        json={
            "version": asset["version"],
            "location_id": location["id"],
            "reason": " Synthetic initial placement ",
            **changes,
        },
    )


def test_initial_placement_lookup_event_retention(client, headers, setup, db, user):
    asset, loc = setup
    path = f"/api/v1/assets/{asset['id']}"
    assert asset["current_location_id"] is None and asset["location_verified_at"] is None
    before = fingerprint(db)
    assert client.get(path + "/location").json()["location"] is None
    assert fingerprint(db) == before
    response = place(client, headers, setup)
    assert response.status_code == 201, response.text
    placed = response.json()
    assert placed["version"] == 2 and placed["current_location_id"] == loc["id"]
    assert placed["location_verified_at"]
    entry = db.scalar(select(AssetLocationEvent))
    assert entry.actor_id == user.id and str(entry.asset_id) == asset["id"]
    assert entry.event_type == "INITIAL_PLACEMENT" and entry.correlation_id
    assert entry.occurred_at == db.get(AssetUnit, uuid.UUID(asset["id"])).location_verified_at
    assert entry.recorded_at is not None
    assert entry.payload_json["from_location_id"] is None
    assert entry.payload_json["to_location_id"] == loc["id"]
    assert entry.payload_json["reason"] == "Synthetic initial placement"
    assert entry.payload_json["expected_asset_version"] == 1
    assert entry.payload_json["asset_version"] == 2
    assert client.get(path).json()["current_location_id"] == loc["id"]
    page = client.get("/api/v1/assets").json()
    assert page["items"][0]["current_location_id"] == loc["id"]
    # Metadata/identifier changes continue from the placement version.
    assert (
        client.patch(path, headers=headers, json={"version": 1, "notes": "stale"}).status_code
        == 409
    )
    assert (
        client.patch(path, headers=headers, json={"version": 2, "notes": "ok"}).json()["version"]
        == 3
    )
    assert (
        client.patch(
            "/api/v1/locations/" + loc["id"],
            headers=headers,
            json={"version": 1, "is_active": False, "name": "Renamed"},
        ).status_code
        == 200
    )
    result = client.get(path + "/location").json()
    assert result["location"]["is_active"] is False
    assert result["location"]["name"] == "Renamed"
    db.expire_all()
    assert db.get(AssetLocationEvent, entry.id).payload_json["location"]["name"] == loc["name"]
    assert len(list(db.scalars(select(AssetLocationEvent)))) == 1
    assert place(client, headers, setup, version=3).status_code == 409


@pytest.mark.parametrize("role", list(Role))
def test_roles_auth_csrf(client, headers, setup, db, user, role):
    user.role = role
    db.commit()
    path = f"/api/v1/assets/{setup[0]['id']}/location"
    assert client.get(path).status_code == 200
    assert place(client, headers, setup).status_code == (201 if role == Role.ADMIN else 403)
    client.cookies.clear()
    assert client.get(path).status_code == 401
    assert place(client, headers, setup).status_code in (401, 403)


def test_csrf_and_transport(client, headers, setup):
    asset, loc = setup
    path = f"/api/v1/assets/{asset['id']}/initial-placement"
    body = {"version": 1, "location_id": loc["id"], "reason": "test"}
    assert client.post(path, json=body).status_code == 403
    assert (
        client.post(
            path, json=body, headers={**headers, "Origin": "https://bad.invalid"}
        ).status_code
        == 403
    )
    assert client.post(path, content="x", headers=headers).status_code == 415
    assert (
        client.post(
            path, content="x" * 17000, headers={**headers, "Content-Type": "application/json"}
        ).status_code
        == 413
    )
    assert client.patch(path, headers=headers, json=body).status_code == 405


@pytest.mark.parametrize(
    "changes",
    [
        {"version": 0},
        {"version": True},
        {"version": 2147483648},
        {"reason": " "},
        {"reason": None},
        {"reason": "x" * 2001},
        {"reason": "bad\x00"},
        {"location_id": None},
        {"location_id": "bad"},
        {"current_location_id": str(uuid.uuid4())},
        {"effective_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_invalid_placement_no_write(client, headers, setup, db, changes):
    before = fingerprint(db)
    assert place(client, headers, setup, **changes).status_code == 422
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "kind", ["unknown-location", "stale", "archived-location", "archived-asset", "limit"]
)
def test_conflicts_no_write(client, headers, setup, db, kind):
    asset, loc = setup
    changes = {}
    if kind == "unknown-location":
        changes["location_id"] = str(uuid.uuid4())
    elif kind == "stale":
        changes["version"] = 2
    elif kind == "archived-location":
        client.patch(
            "/api/v1/locations/" + loc["id"],
            headers=headers,
            json={"version": 1, "is_active": False},
        )
    elif kind == "archived-asset":
        client.post(f"/api/v1/assets/{asset['id']}/archive", headers=headers, json={"version": 1})
        changes["version"] = 2
    else:
        db.execute(update(AssetUnit).values(version=2147483647))
        db.commit()
        changes["version"] = 2147483647
    before = fingerprint(db)
    assert place(client, headers, setup, **changes).status_code == (
        422 if kind == "unknown-location" else 409
    )
    assert fingerprint(db) == before


def test_unknown_asset_and_generic_writes_forbidden(client, headers, setup, db):
    loc = setup[1]
    unknown = f"/api/v1/assets/{uuid.uuid4()}"
    assert client.get(unknown + "/location").status_code == 404
    assert (
        client.post(
            unknown + "/initial-placement",
            headers=headers,
            json={"version": 1, "location_id": loc["id"], "reason": "test"},
        ).status_code
        == 404
    )
    before = fingerprint(db)
    for field in ("current_location_id", "location_verified_at"):
        assert (
            client.patch(
                f"/api/v1/assets/{setup[0]['id']}",
                headers=headers,
                json={"version": 1, field: loc["id"]},
            ).status_code
            == 422
        )
    assert fingerprint(db) == before


def test_failed_event_rolls_back(client, headers, setup, db):
    before = fingerprint(db)

    def fail(*args):
        raise RuntimeError("synthetic event failure")

    event.listen(AssetLocationEvent, "before_insert", fail)
    try:
        assert place(client, headers, setup).status_code == 500
    finally:
        event.remove(AssetLocationEvent, "before_insert", fail)
    assert fingerprint(db) == before


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_history_append_only_and_fk(client, headers, setup, db, operation):
    assert place(client, headers, setup).status_code == 201
    entry = db.scalar(select(AssetLocationEvent))
    with pytest.raises(IntegrityError):
        if operation == "update":
            entry.event_type = "REWRITTEN"
        else:
            db.delete(entry)
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(update(AssetUnit).values(current_location_id=uuid.uuid4()))
        db.commit()
    db.rollback()


def test_migration_preserves_populated_predecessor(factory, db, user):
    seed_assets(db, user.id)
    db.commit()
    expected = fingerprint(db)
    db.rollback()
    with factory.kw["bind"].connect() as c:
        config = Config("alembic.ini")
        config.attributes["connection"] = c
        command.downgrade(config, "0006_locations")
        assert "asset_events" not in inspect(c).get_table_names()
        assert "current_location_id" not in {x["name"] for x in inspect(c).get_columns("assets")}
        command.upgrade(config, "head")
        command.check(config)
        c.commit()
    assert fingerprint(db) == expected
    assert db.scalar(select(text("count(*)")).select_from(AssetUnit)) == 8
    assert all(
        x.current_location_id is None and x.location_verified_at is None
        for x in db.scalars(select(AssetUnit))
    )


def test_populated_downgrade_refused(client, headers, setup, factory):
    assert place(client, headers, setup).status_code == 201
    with factory.kw["bind"].connect() as c:
        config = Config("alembic.ini")
        config.attributes["connection"] = c
        with pytest.raises(RuntimeError, match="Cannot downgrade populated"):
            command.downgrade(config, "0006_locations")
        c.rollback()
    assert (
        client.get(f"/api/v1/assets/{setup[0]['id']}/location").json()["current_location_id"]
        == setup[1]["id"]
    )


@pytest.mark.parametrize("race", ["placement", "metadata"])
def test_postgres_placement_race(client, headers, setup, db, factory, user, race):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Independent PostgreSQL row-lock sessions")
    barrier = Barrier(2)
    asset_id = uuid.UUID(setup[0]["id"])
    location_id = uuid.UUID(setup[1]["id"])
    actor_id = user.id
    db.rollback()

    def worker(second):
        with factory() as session:
            actor = session.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                if second and race == "metadata":
                    update_asset(session, asset_id, 1, {"notes": "concurrent"}, actor)
                else:
                    initial_placement(session, asset_id, 1, location_id, "race", actor)
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [False, True]))
    assert sorted(results) == [200, 409]
    db.expire_all()
    asset = db.get(AssetUnit, asset_id)
    entries = list(db.scalars(select(AssetLocationEvent)))
    assert asset.version == 2
    assert len(entries) == (1 if asset.current_location_id else 0)


def test_postgres_archive_race(client, headers, setup, db, factory, user):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Independent PostgreSQL hierarchy-lock sessions")
    asset_id, location_id, actor_id = uuid.UUID(setup[0]["id"]), uuid.UUID(setup[1]["id"]), user.id
    barrier = Barrier(2)
    db.rollback()

    def worker(archive):
        with factory() as session:
            actor = session.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                if archive:
                    save_location(
                        session, actor, LocationPatch(version=1, is_active=False), location_id
                    )
                else:
                    initial_placement(session, asset_id, 1, location_id, "race", actor)
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, [False, True]))
    assert outcomes[1] == 200 and outcomes[0] in (200, 409)
    db.expire_all()
    entries = list(db.scalars(select(AssetLocationEvent)))
    assert len(entries) == (1 if outcomes[0] == 200 else 0)
    if entries:
        assert entries[0].payload_json["location"]["is_active"] is True
