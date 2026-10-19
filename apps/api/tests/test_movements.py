"""Task 2-03 API, invariants, rollback, retention, migration and PostgreSQL races."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
import test_asset_api as asset_api
from alembic import command
from alembic.config import Config
from conftest import session_headers, sign_in
from fastapi import HTTPException
from sqlalchemy import event, insert, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from test_asset_csv import fingerprint
from test_locations import create as create_location

from app.asset_location_service import initial_placement
from app.asset_locations import AssetLocationEvent
from app.asset_service import update_asset
from app.assets import AssetUnit
from app.location_schemas import LocationCreate, LocationPatch
from app.location_service import save_location
from app.models import Role, User
from app.movement_service import decide_movement
from app.movements import AssetMovement, MovementStatus
from app.seed_assets import seed_assets

catalog_model = asset_api.model
ROOT = "/api/v1"


@pytest.fixture()
def headers(client, user, password):
    assert sign_in(client, password).status_code == 200
    return session_headers(client)


@pytest.fixture()
def setup(client, headers, catalog_model):
    asset = asset_api.create(client, headers, catalog_model, "AP-003")
    origin = create_location(client, headers, "villa-1", kind="BUILDING")
    destination = create_location(client, headers, "villa-10", kind="BUILDING")
    placed = client.post(
        f"{ROOT}/assets/{asset['id']}/initial-placement",
        headers=headers,
        json={"version": 1, "location_id": origin["id"], "reason": "Synthetic placement"},
    )
    assert placed.status_code == 201
    return placed.json(), origin, destination


def request(client, headers, setup, **changes):
    return client.post(
        f"{ROOT}/assets/{setup[0]['id']}/movements",
        headers=headers,
        json={
            "asset_version": 2,
            "to_location_id": setup[2]["id"],
            "reason": " Synthetic move ",
            **changes,
        },
    )


def decision(client, headers, movement, action="approve", **changes):
    return client.post(
        f"{ROOT}/movements/{movement['id']}/{action}",
        headers=headers,
        json={"version": 1, "reason": " Reviewed synthetic move ", **changes},
    )


def asset_state(client, setup):
    return client.get(f"{ROOT}/assets/{setup[0]['id']}").json()


def test_officer_request_admin_approval_atomically(client, headers, setup, db, user, password):
    initial = asset_state(client, setup)
    user.role = Role.OFFICER
    db.commit()
    response = request(client, headers, setup)
    assert response.status_code == 201, response.text
    movement = response.json()
    assert movement["status"] == "PENDING" and movement["version"] == 1
    assert movement["expected_asset_version"] == 2 and movement["reason"] == "Synthetic move"
    assert (
        movement["from_location_id"] == setup[1]["id"]
        and movement["to_location_id"] == setup[2]["id"]
    )
    assert movement["requested_by"] == str(user.id) and movement["requested_at"]
    assert all(
        movement[x] is None
        for x in ("reviewed_by", "reviewed_at", "approved_at", "effective_at", "review_reason")
    )
    assert asset_state(client, setup) == initial
    # Separate ADMIN reviewer; request actor remains the original OFFICER.
    reviewer = User(
        email="reviewer@example.com",
        name="Synthetic reviewer",
        role=Role.ADMIN,
        password_hash=user.password_hash,
    )
    db.add(reviewer)
    db.commit()
    assert sign_in(client, password, reviewer.email).status_code == 200
    approved = decision(client, session_headers(client), movement)
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert result["status"] == "APPROVED" and result["version"] == 2
    assert result["reviewed_by"] == str(reviewer.id)
    assert result["approved_at"] == result["reviewed_at"] == result["effective_at"]
    current = asset_state(client, setup)
    assert current["current_location_id"] == setup[2]["id"] and current["version"] == 3
    assert datetime.fromisoformat(current["location_verified_at"]).replace(tzinfo=UTC) == (
        datetime.fromisoformat(result["effective_at"]).replace(tzinfo=UTC)
    )
    for key in ("device_model_id", "condition", "lifecycle_status", "installed_at", "notes"):
        assert current[key] == initial[key]
    entries = list(db.scalars(select(AssetLocationEvent).order_by(AssetLocationEvent.occurred_at)))
    assert [x.event_type for x in entries] == [
        "INITIAL_PLACEMENT",
        "MOVEMENT_REQUESTED",
        "MOVEMENT_APPROVED",
    ]
    last = entries[-1]
    assert last.actor_id == reviewer.id and last.payload_json["requested_by"] == str(user.id)
    assert last.payload_json["from_location_id"] == setup[1]["id"]
    assert last.payload_json["to_location_id"] == setup[2]["id"]
    assert last.payload_json["asset_version"] == 3 and last.payload_json["self_approval"] is False
    assert len({x.correlation_id for x in entries}) == 3


def test_pilot_self_approval_and_archive_history(client, headers, setup, db, user):
    movement = request(client, headers, setup).json()
    assert decision(client, headers, movement).status_code == 200
    entry = db.scalar(
        select(AssetLocationEvent).where(AssetLocationEvent.event_type == "MOVEMENT_APPROVED")
    )
    assert entry.payload_json["self_approval"] is True
    assert entry.payload_json["self_approval_policy"] == "ALLOWED_PILOT"
    assert entry.payload_json["requested_by"] == entry.payload_json["reviewed_by"] == str(user.id)
    original_payload = dict(entry.payload_json)
    for loc in setup[1:]:
        assert (
            client.patch(
                f"{ROOT}/locations/{loc['id']}",
                headers=headers,
                json={"version": 1, "is_active": False, "name": "Renamed"},
            ).status_code
            == 200
        )
    db.expire_all()
    assert db.get(AssetLocationEvent, entry.id).payload_json == original_payload
    history = client.get(f"{ROOT}/assets/{setup[0]['id']}/movements").json()
    assert (
        history["total"] == 1
        and history["items"][0]["request_snapshot_json"]["to"]["name"] == setup[2]["name"]
    )


@pytest.mark.parametrize("action,status", [("reject", "REJECTED"), ("cancel", "CANCELLED")])
def test_reject_cancel_preserve_asset(client, headers, setup, db, action, status):
    movement = request(client, headers, setup).json()
    initial = asset_state(client, setup)
    response = decision(client, headers, movement, action)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == status and result["version"] == 2
    assert result["reviewed_at"] and result["review_reason"] == "Reviewed synthetic move"
    assert result["approved_at"] is None and result["effective_at"] is None
    assert asset_state(client, setup) == initial
    assert db.scalar(
        select(AssetLocationEvent).where(AssetLocationEvent.event_type == "MOVEMENT_" + status)
    )


@pytest.mark.parametrize("role", list(Role))
def test_roles_all_routes(client, headers, setup, db, user, role):
    movement = request(client, headers, setup).json()
    user.role = role
    db.commit()
    assert client.get(f"{ROOT}/assets/{setup[0]['id']}/movements").status_code == 200
    assert client.get(f"{ROOT}/movements/{movement['id']}").status_code == 200
    assert client.get(ROOT + "/movements").status_code == (200 if role == Role.ADMIN else 403)
    assert request(client, headers, setup).status_code == (403 if role == Role.VIEWER else 201)
    if role != Role.ADMIN:
        before = fingerprint(db)
        assert decision(client, headers, movement, "approve").status_code == 403
        assert decision(client, headers, movement, "reject").status_code == 403
        assert fingerprint(db) == before
    assert decision(client, headers, movement, "cancel").status_code == (
        403 if role == Role.VIEWER else 200
    )
    client.cookies.clear()
    assert client.get(f"{ROOT}/assets/{setup[0]['id']}/movements").status_code == 401
    assert client.get(f"{ROOT}/movements/{movement['id']}").status_code == 401
    assert client.get(ROOT + "/movements").status_code == 401
    assert request(client, headers, setup).status_code in (401, 403)
    assert decision(client, headers, movement).status_code in (401, 403)


def test_officer_cannot_cancel_others(client, headers, setup, db, user):
    movement = request(client, headers, setup).json()
    other = User(
        email="other@example.com", name="Other", role=Role.OFFICER, password_hash=user.password_hash
    )
    db.add(other)
    db.commit()
    # Change the request actor identity through a genuine login, preserving roles.
    from app.security import hash_password

    other.password_hash = hash_password("synthetic-long-password-123")
    db.commit()
    assert sign_in(client, "synthetic-long-password-123", other.email).status_code == 200
    before = fingerprint(db)
    assert decision(client, session_headers(client), movement, "cancel").status_code == 403
    assert fingerprint(db) == before


@pytest.mark.parametrize("first", ["approve", "reject", "cancel"])
@pytest.mark.parametrize("second", ["approve", "reject", "cancel"])
def test_terminal_decision_matrix(client, headers, setup, db, first, second):
    movement = request(client, headers, setup).json()
    assert decision(client, headers, movement, first).status_code == 200
    before = fingerprint(db)
    assert decision(client, headers, movement, second, version=2).status_code == 409
    assert fingerprint(db) == before


def test_multiple_requests_stale_and_explicit_rerequest(client, headers, setup):
    a = request(client, headers, setup).json()
    b = request(client, headers, setup).json()
    assert decision(client, headers, a).status_code == 200
    assert decision(client, headers, b).status_code == 409
    assert client.get(f"{ROOT}/movements/{b['id']}").json()["status"] == "PENDING"
    assert decision(client, headers, b, "reject").status_code == 200
    back = request(client, headers, setup, asset_version=3, to_location_id=setup[1]["id"])
    assert back.status_code == 201 and decision(client, headers, back.json()).status_code == 200
    assert asset_state(client, setup)["version"] == 4
    assert asset_state(client, setup)["current_location_id"] == setup[1]["id"]


@pytest.mark.parametrize(
    "kind", ["metadata", "identifier", "origin", "destination-archive", "asset-archive"]
)
def test_approval_revalidation(client, headers, setup, db, kind):
    movement = request(client, headers, setup).json()
    path = f"{ROOT}/assets/{setup[0]['id']}"
    if kind == "metadata":
        assert (
            client.patch(
                path, headers=headers, json={"version": 2, "notes": "Concurrent edit"}
            ).status_code
            == 200
        )
    elif kind == "identifier":
        assert (
            client.post(
                path + "/identifiers",
                headers=headers,
                json={
                    "asset_version": 2,
                    "identifier_type": "SERIAL_NUMBER",
                    "raw_value": "SYNTHETIC",
                    "source": "MANUAL",
                },
            ).status_code
            == 201
        )
    elif kind == "origin":
        db.execute(update(AssetUnit).values(current_location_id=uuid.UUID(setup[2]["id"])))
        db.commit()
    elif kind == "destination-archive":
        assert (
            client.patch(
                f"{ROOT}/locations/{setup[2]['id']}",
                headers=headers,
                json={"version": 1, "is_active": False},
            ).status_code
            == 200
        )
    else:
        assert (
            client.post(path + "/archive", headers=headers, json={"version": 2}).status_code == 200
        )
    before = fingerprint(db)
    assert decision(client, headers, movement).status_code == 409
    assert fingerprint(db) == before
    # Stale/archived requests can still be closed without changing the asset.
    state = asset_state(client, setup)
    assert decision(client, headers, movement, "reject").status_code == 200
    assert asset_state(client, setup) == state


@pytest.mark.parametrize(
    "changes",
    [
        {"asset_version": 0},
        {"asset_version": True},
        {"asset_version": 2147483648},
        {"to_location_id": "bad"},
        {"to_location_id": None},
        {"reason": " "},
        {"reason": None},
        {"reason": "x" * 2001},
        {"reason": "bad\x00"},
        {"from_location_id": str(uuid.uuid4())},
        {"status": "APPROVED"},
        {"requested_by": str(uuid.uuid4())},
        {"effective_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_invalid_request_no_write(client, headers, setup, db, changes):
    before = fingerprint(db)
    assert request(client, headers, setup, **changes).status_code == 422
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"version": 0},
        {"version": True},
        {"version": 2},
        {"reason": " "},
        {"reason": "x" * 2001},
        {"effective_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_invalid_decision_no_write(client, headers, setup, db, changes):
    movement = request(client, headers, setup).json()
    before = fingerprint(db)
    assert decision(client, headers, movement, **changes).status_code == (
        409 if changes.get("version") == 2 else 422
    )
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "kind",
    [
        "unknown-location",
        "same-location",
        "stale",
        "unplaced",
        "archived-asset",
        "archived-target",
        "limit",
    ],
)
def test_request_conflicts(client, headers, setup, db, kind):
    changes = {}
    if kind == "unknown-location":
        changes["to_location_id"] = str(uuid.uuid4())
    elif kind == "same-location":
        changes["to_location_id"] = setup[1]["id"]
    elif kind == "stale":
        changes["asset_version"] = 1
    elif kind == "unplaced":
        db.execute(update(AssetUnit).values(current_location_id=None))
        db.commit()
    elif kind == "archived-target":
        client.patch(
            f"{ROOT}/locations/{setup[2]['id']}",
            headers=headers,
            json={"version": 1, "is_active": False},
        )
    elif kind == "archived-asset":
        client.post(f"{ROOT}/assets/{setup[0]['id']}/archive", headers=headers, json={"version": 2})
        changes["asset_version"] = 3
    else:
        db.execute(update(AssetUnit).values(version=2147483647))
        db.commit()
        changes["asset_version"] = 2147483647
    before = fingerprint(db)
    assert request(client, headers, setup, **changes).status_code == (
        422 if kind == "unknown-location" else 409
    )
    assert fingerprint(db) == before


def test_archived_origin_can_move_out(client, headers, setup):
    assert (
        client.patch(
            f"{ROOT}/locations/{setup[1]['id']}",
            headers=headers,
            json={"version": 1, "is_active": False},
        ).status_code
        == 200
    )
    movement = request(client, headers, setup).json()
    assert movement["request_snapshot_json"]["from"]["is_active"] is False
    assert decision(client, headers, movement).status_code == 200


def test_query_filters_pagination_and_no_side_effects(client, headers, setup, db, catalog_model):
    a = request(client, headers, setup).json()
    b = request(client, headers, setup).json()
    assert decision(client, headers, a, "reject").status_code == 200
    path = f"{ROOT}/assets/{setup[0]['id']}/movements"
    assert client.get(path + "?page_size=1").json()["total_pages"] == 2
    assert client.get(path + "?page=100").json()["items"] == []
    assert client.get(path + "?status=REJECTED").json()["total"] == 1
    assert client.get(ROOT + "/movements?status=PENDING").json()["items"][0]["id"] == b["id"]
    assert client.get(ROOT + f"/movements?asset_id={uuid.uuid4()}").json()["total"] == 0
    other = asset_api.create(client, headers, catalog_model, "AP-004")
    assert client.get(f"{ROOT}/assets/{other['id']}/movements").json()["items"] == []
    before = fingerprint(db)
    for route in (path, ROOT + "/movements", ROOT + f"/movements/{a['id']}"):
        assert client.get(route).status_code == 200
        assert client.get(route).headers["cache-control"] == "no-store"
    assert fingerprint(db) == before
    for query in ("page=0", "page_size=101", "status=BAD", "unknown=bad"):
        assert client.get(path + "?" + query).status_code == 422
    assert client.get(f"{ROOT}/assets/{uuid.uuid4()}/movements").status_code == 404
    assert client.get(f"{ROOT}/movements/{uuid.uuid4()}").status_code == 404
    assert decision(client, headers, {"id": str(uuid.uuid4())}).status_code == 404


def test_transport_csrf_and_no_unsafe_routes(client, headers, setup):
    path = f"{ROOT}/assets/{setup[0]['id']}/movements"
    body = {"asset_version": 2, "to_location_id": setup[2]["id"], "reason": "Test"}
    assert client.post(path, json=body).status_code == 403
    assert (
        client.post(
            path, json=body, headers={**headers, "Origin": "https://bad.invalid"}
        ).status_code
        == 403
    )
    assert client.post(path, headers=headers, content="bad").status_code == 415
    assert (
        client.post(
            path, headers={**headers, "Content-Type": "application/json"}, content="x" * 17000
        ).status_code
        == 413
    )
    movement = request(client, headers, setup).json()
    decision_path = f"{ROOT}/movements/{movement['id']}"
    assert (
        client.post(decision_path + "/approve", json={"version": 1, "reason": "Bad"}).status_code
        == 403
    )
    assert (
        client.patch(decision_path, headers=headers, json={"status": "APPROVED"}).status_code == 405
    )
    assert client.delete(decision_path, headers=headers).status_code == 405


@pytest.mark.parametrize("phase", ["request", "approve", "reject", "cancel"])
def test_audit_failure_rolls_back_everything(client, headers, setup, db, phase):
    movement = None if phase == "request" else request(client, headers, setup).json()
    before = fingerprint(db)

    def fail(*args):
        raise RuntimeError("Synthetic movement event failure")

    event.listen(AssetLocationEvent, "before_insert", fail)
    try:
        response = (
            request(client, headers, setup)
            if phase == "request"
            else decision(client, headers, movement, phase)
        )
        assert response.status_code == 500
    finally:
        event.remove(AssetLocationEvent, "before_insert", fail)
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "kind", ["rewrite-request", "delete", "pending-update", "reopen", "rewrite-terminal", "fk"]
)
def test_database_guards(client, headers, setup, db, kind):
    movement = request(client, headers, setup).json()
    record = db.get(AssetMovement, uuid.UUID(movement["id"]))
    db.rollback()
    if kind in ("reopen", "rewrite-terminal"):
        assert decision(client, headers, movement, "reject").status_code == 200
    with pytest.raises(IntegrityError):
        if kind == "rewrite-request":
            db.execute(update(AssetMovement).values(reason="Rewritten"))
        elif kind == "delete":
            db.execute(text("DELETE FROM asset_movements"))
        elif kind == "pending-update":
            db.execute(update(AssetMovement).values(version=2))
        elif kind == "reopen":
            db.execute(update(AssetMovement).values(status=MovementStatus.PENDING, version=3))
        elif kind == "rewrite-terminal":
            db.execute(update(AssetMovement).values(review_reason="Changed"))
        else:
            # A new pending row with an orphan FK cannot bypass referential integrity.
            db.add(
                AssetMovement(
                    id=uuid.uuid4(),
                    asset_id=uuid.uuid4(),
                    from_location_id=record.from_location_id,
                    to_location_id=record.to_location_id,
                    status=MovementStatus.PENDING,
                    version=1,
                    reason="Test",
                    requested_by=record.requested_by,
                    requested_at=record.requested_at,
                    expected_asset_version=2,
                    request_snapshot_json={},
                )
            )
        db.commit()
    db.rollback()


def test_migration_preserves_predecessor_data(factory, db, user):
    seed_assets(db, user.id)
    db.commit()
    location = save_location(
        db, user, LocationCreate(code="migration-site", name="Migration site", kind="SITE")
    )
    asset = db.scalar(select(AssetUnit).where(AssetUnit.asset_code == "AP-003"))
    initial_placement(db, asset.id, asset.version, location.id, "Preserved initial evidence", user)
    before = fingerprint(db)
    db.rollback()
    with factory.kw["bind"].connect() as c:
        config = Config("alembic.ini")
        config.attributes["connection"] = c
        command.downgrade(config, "0007_asset_location")
        assert "asset_movements" not in inspect(c).get_table_names()
        command.upgrade(config, "head")
        command.check(config)
        c.commit()
    assert fingerprint(db) == before


def test_populated_migration_downgrade_refuses(client, headers, setup, factory):
    movement = request(client, headers, setup).json()
    with factory.kw["bind"].connect() as c:
        config = Config("alembic.ini")
        config.attributes["connection"] = c
        with pytest.raises(RuntimeError, match="Cannot downgrade populated"):
            command.downgrade(config, "0007_asset_location")
        c.rollback()
    assert client.get(f"{ROOT}/movements/{movement['id']}").status_code == 200


@pytest.mark.parametrize(
    "race", ["double-approve", "two-requests", "reject", "cancel", "metadata", "archive"]
)
def test_postgres_atomic_decision_race(client, headers, setup, db, factory, user, race):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Independent PostgreSQL sessions")
    first = request(client, headers, setup).json()
    second = request(client, headers, setup).json() if race == "two-requests" else first
    actor_id = user.id
    asset_id = uuid.UUID(setup[0]["id"])
    destination_id = uuid.UUID(setup[2]["id"])
    db.rollback()
    barrier = Barrier(2)

    def worker(alternate):
        with factory() as session:
            actor = session.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                if alternate and race == "metadata":
                    update_asset(session, asset_id, 2, {"notes": "Race metadata"}, actor)
                elif alternate and race == "archive":
                    save_location(
                        session, actor, LocationPatch(version=1, is_active=False), destination_id
                    )
                else:
                    target = second if alternate else first
                    action = (
                        {"reject": MovementStatus.REJECTED, "cancel": MovementStatus.CANCELLED}.get(
                            race, MovementStatus.APPROVED
                        )
                        if alternate
                        else MovementStatus.APPROVED
                    )
                    decide_movement(
                        session, uuid.UUID(target["id"]), 1, action, "Concurrent review", actor
                    )
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [False, True]))
    if race == "archive":
        assert results[1] == 200 and results[0] in (200, 409)
    else:
        assert sorted(results) == [200, 409]
    db.expire_all()
    asset = db.get(AssetUnit, asset_id)
    approvals = list(
        db.scalars(
            select(AssetLocationEvent).where(AssetLocationEvent.event_type == "MOVEMENT_APPROVED")
        )
    )
    assert len(approvals) <= 1
    assert asset.current_location_id == (destination_id if approvals else uuid.UUID(setup[1]["id"]))
    assert asset.version == (3 if approvals or race == "metadata" else 2)
    decisions = list(
        db.scalars(select(AssetMovement).where(AssetMovement.status != MovementStatus.PENDING))
    )
    assert len(decisions) == (len(approvals) if race in ("metadata", "archive") else 1)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": MovementStatus.APPROVED},
        {"version": 0},
        {"expected_asset_version": 0},
        {"reason": " "},
        {"review_reason": "Invalid pending review"},
        {"effective_at": datetime.now(UTC)},
    ],
)
def test_database_state_constraints(client, headers, setup, db, user, changes):
    values = dict(
        id=uuid.uuid4(),
        asset_id=uuid.UUID(setup[0]["id"]),
        from_location_id=uuid.UUID(setup[1]["id"]),
        to_location_id=uuid.UUID(setup[2]["id"]),
        status=MovementStatus.PENDING,
        version=1,
        expected_asset_version=2,
        reason="Synthetic",
        requested_by=user.id,
        requested_at=datetime.now(UTC),
        request_snapshot_json={},
    )
    values.update(changes)
    before = fingerprint(db)
    with pytest.raises(IntegrityError):
        db.execute(insert(AssetMovement).values(**values))
        db.commit()
    db.rollback()
    assert fingerprint(db) == before
