"""Task 2-04: evidence, conflict status, immutable timeline and concurrency."""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from threading import Barrier

import pytest
import test_asset_api as asset_api
import test_movements as movement_cases
from alembic import command
from alembic.config import Config
from conftest import session_headers, sign_in
from fastapi import HTTPException
from sqlalchemy import event, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from test_asset_csv import fingerprint

from app.asset_locations import AssetLocationEvent
from app.assets import AssetChangeEvent, AssetEventType, AssetUnit
from app.location_schemas import LocationPatch
from app.location_service import save_location
from app.models import AuditEvent, Role, User
from app.movement_service import decide_movement
from app.movements import MovementStatus
from app.observation_schemas import ObservationCreate, ObservationReview
from app.observation_service import create_observation, review_observation
from app.observations import LocationObservation, ObservationComparison, ObservationReviewStatus

catalog_model = asset_api.model
setup = movement_cases.setup
ROOT = "/api/v1"


@pytest.fixture()
def headers(client, user, password):
    assert sign_in(client, password).status_code == 200
    return session_headers(client)


def observe(client, headers, setup, **changes):
    return client.post(
        ROOT + "/location-observations",
        headers=headers,
        json={
            "asset_id": setup[0]["id"],
            "asset_version": 2,
            "observed_location_id": setup[1]["id"],
            "evidence_note": " Synthetic field evidence ",
            **changes,
        },
    )


def review(client, headers, observation, **changes):
    return client.post(
        f"{ROOT}/location-observations/{observation['id']}/review",
        headers=headers,
        json={
            "version": 1,
            "review_status": "ACKNOWLEDGED",
            "reason": " Synthetic review ",
            **changes,
        },
    )


def status(client, setup):
    response = client.get(f"{ROOT}/assets/{setup[0]['id']}/location-status")
    assert response.status_code == 200, response.text
    return response.json()


def timeline(client, setup, query=""):
    response = client.get(f"{ROOT}/assets/{setup[0]['id']}/timeline" + query)
    assert response.status_code == 200, response.text
    return response.json()


def move(client, headers, setup):
    movement = movement_cases.request(client, headers, setup).json()
    assert movement_cases.decision(client, headers, movement).status_code == 200
    return movement


def test_conflict_after_move_preserves_official_and_event_history(client, headers, setup, db, user):
    assert status(client, setup)["status"] == "NO_OBSERVATION"
    move(client, headers, setup)
    initial = movement_cases.asset_state(client, setup)
    user.role = Role.OFFICER
    db.commit()
    response = observe(client, headers, setup, asset_version=3)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["comparison_status"] == "LOCATION_CONFLICT" and record["version"] == 1
    assert record["official_location_id_at_recording"] == setup[2]["id"]
    assert record["asset_version_at_recording"] == 3 and record["observed_by"] == str(user.id)
    assert record["snapshot_json"]["observed_location"]["name"] == setup[1]["name"]
    assert record["snapshot_json"]["official_location"]["name"] == setup[2]["name"]
    assert record["evidence_note"] == "Synthetic field evidence"
    current = status(client, setup)
    assert current["location_conflict"] is True and current["status"] == "LOCATION_CONFLICT"
    assert current["latest_observation"]["id"] == record["id"]
    assert movement_cases.asset_state(client, setup) == initial
    entry = db.scalar(
        select(AssetLocationEvent).where(AssetLocationEvent.event_type == "LOCATION_OBSERVED")
    )
    assert entry.actor_id == user.id and entry.payload_json["id"] == record["id"]
    assert entry.payload_json["asset_at_recording"]["current_location_id"] == setup[2]["id"]
    kinds = {x["event_type"] for x in timeline(client, setup)["items"]}
    assert {
        "CREATE",
        "INITIAL_PLACEMENT",
        "MOVEMENT_REQUESTED",
        "MOVEMENT_APPROVED",
        "LOCATION_OBSERVED",
    } <= kinds


@pytest.mark.parametrize("decision_status", ["ACKNOWLEDGED", "DISMISSED"])
def test_review_changes_only_review_and_event(client, headers, setup, db, decision_status):
    observation = observe(client, headers, setup, observed_location_id=setup[2]["id"]).json()
    initial = movement_cases.asset_state(client, setup)
    assert status(client, setup)["location_conflict"] is True
    response = review(client, headers, observation, review_status=decision_status)
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["review_status"] == decision_status and record["version"] == 2
    assert record["reviewed_at"] and record["review_reason"] == "Synthetic review"
    assert record["snapshot_json"] == observation["snapshot_json"]
    assert record["comparison_status"] == "LOCATION_CONFLICT"
    assert movement_cases.asset_state(client, setup) == initial
    state = status(client, setup)
    assert state["location_conflict"] == (decision_status == "ACKNOWLEDGED")
    assert state["status"] == (
        "LOCATION_CONFLICT" if decision_status == "ACKNOWLEDGED" else "NO_OBSERVATION"
    )
    before = fingerprint(db)
    assert (
        review(client, headers, observation, version=2, review_status=decision_status).status_code
        == 409
    )
    assert fingerprint(db) == before
    items = timeline(client, setup, "?event_type=LOCATION_OBSERVATION_REVIEWED")["items"]
    assert len(items) == 1 and items[0]["payload_json"]["review_status"] == decision_status


def test_latest_evidence_stale_and_new_match(client, headers, setup):
    first = observe(client, headers, setup).json()
    assert status(client, setup)["status"] == "MATCH"
    move(client, headers, setup)
    stale = status(client, setup)
    assert stale["status"] == "STALE_OBSERVATION" and stale["location_conflict"] is False
    assert stale["latest_observation"]["id"] == first["id"]
    conflict = observe(client, headers, setup, asset_version=3).json()
    assert status(client, setup)["location_conflict"] is True
    # Backdated records are retained, but do not displace newer field evidence.
    older = observe(
        client,
        headers,
        setup,
        asset_version=3,
        observed_location_id=setup[2]["id"],
        observed_at=(datetime.now(UTC) - timedelta(days=2)).isoformat(),
    ).json()
    assert status(client, setup)["latest_observation"]["id"] == conflict["id"]
    matched = observe(
        client, headers, setup, asset_version=3, observed_location_id=setup[2]["id"]
    ).json()
    assert status(client, setup)["status"] == "MATCH"
    assert status(client, setup)["latest_observation"]["id"] == matched["id"]
    assert older["comparison_status"] == "MATCH"
    assert timeline(client, setup)["items"][-1]["payload_json"]["id"] == older["id"]


def test_dismiss_latest_falls_back_to_previous_evidence(client, headers, setup):
    first = observe(client, headers, setup, observed_location_id=setup[2]["id"]).json()
    latest = observe(client, headers, setup).json()
    assert status(client, setup)["status"] == "MATCH"
    assert review(client, headers, latest, review_status="DISMISSED").status_code == 200
    assert status(client, setup)["latest_observation"]["id"] == first["id"]
    assert status(client, setup)["location_conflict"] is True


def test_unlinked_and_unplaced_support_atomic_audit(client, headers, setup, db, catalog_model):
    before = timeline(client, setup)["total"]
    observation = observe(client, headers, setup, asset_id=None, asset_version=None).json()
    assert observation["comparison_status"] == "UNLINKED" and observation["asset_id"] is None
    assert observation["asset_version_at_recording"] is None
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "location_observation_create"))
    assert json.loads(audit.details["snapshot"])["id"] == observation["id"]
    assert review(client, headers, observation).status_code == 200
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "location_observation_review"))
    assert timeline(client, setup)["total"] == before
    asset = asset_api.create(client, headers, catalog_model, "AP-004")
    unplaced = observe(client, headers, setup, asset_id=asset["id"], asset_version=1).json()
    assert unplaced["comparison_status"] == "UNPLACED"
    assert client.get(f"{ROOT}/assets/{asset['id']}/location-status").json()["status"] == "UNPLACED"
    assert client.get(f"{ROOT}/assets/{asset['id']}").json() == asset


def test_timestamp_offset_normalization_and_archived_asset(client, headers, setup):
    observed = (datetime.now(UTC) - timedelta(seconds=1)).astimezone(timezone(timedelta(hours=8)))
    response = observe(client, headers, setup, observed_at=observed.isoformat())
    assert response.status_code == 201
    value = datetime.fromisoformat(response.json()["observed_at"]).replace(tzinfo=UTC)
    assert value == observed.astimezone(UTC)
    assert (
        client.post(
            f"{ROOT}/assets/{setup[0]['id']}/archive", headers=headers, json={"version": 2}
        ).status_code
        == 200
    )
    assert observe(client, headers, setup, asset_version=3).status_code == 201


@pytest.mark.parametrize("role", list(Role))
def test_rbac_and_anonymous(client, headers, setup, db, user, role):
    observation = observe(client, headers, setup).json()
    user.role = role
    db.commit()
    for endpoint in ("timeline", "location-status", "location-observations"):
        assert client.get(f"{ROOT}/assets/{setup[0]['id']}/{endpoint}").status_code == 200
    expected = 200 if role == Role.ADMIN else 403
    assert client.get(ROOT + "/location-observations").status_code == expected
    assert client.get(f"{ROOT}/location-observations/{observation['id']}").status_code == expected
    assert review(client, headers, observation).status_code == expected
    assert observe(client, headers, setup).status_code == (403 if role == Role.VIEWER else 201)
    client.cookies.clear()
    for endpoint in ("timeline", "location-status", "location-observations"):
        assert client.get(f"{ROOT}/assets/{setup[0]['id']}/{endpoint}").status_code == 401
    assert client.get(ROOT + "/location-observations").status_code == 401
    assert observe(client, headers, setup).status_code in (401, 403)
    assert review(client, headers, observation).status_code in (401, 403)


@pytest.mark.parametrize(
    "changes",
    [
        {"asset_id": None},
        {"asset_version": None},
        {"asset_version": True},
        {"asset_version": 0},
        {"evidence_note": " "},
        {"evidence_note": None},
        {"evidence_note": "x" * 2001},
        {"evidence_note": "bad\x00"},
        {"observed_location_id": "bad"},
        {"observed_location_id": None},
        {"observed_at": "2026-01-01T00:00:00"},
        {"observed_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        {"observed_by": str(uuid.uuid4())},
        {"review_status": "ACKNOWLEDGED"},
        {"official_location_id_at_recording": str(uuid.uuid4())},
        {"comparison_status": "MATCH"},
        {"version": 2},
    ],
)
def test_validation_no_side_effects(client, headers, setup, db, changes):
    before = fingerprint(db)
    assert observe(client, headers, setup, **changes).status_code == 422
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"version": True},
        {"version": 0},
        {"version": 2},
        {"reason": " "},
        {"reason": "x" * 2001},
        {"review_status": "PENDING"},
        {"review_status": "APPROVED"},
        {"observed_location_id": str(uuid.uuid4())},
    ],
)
def test_review_validation_and_conflict(client, headers, setup, db, changes):
    observation = observe(client, headers, setup).json()
    before = fingerprint(db)
    expected = 409 if changes.get("version") == 2 else 422
    assert review(client, headers, observation, **changes).status_code == expected
    assert fingerprint(db) == before


def test_unknown_stale_archived_and_max_asset_version(client, headers, setup, db):
    assert observe(client, headers, setup, asset_id=str(uuid.uuid4())).status_code == 404
    assert (
        observe(client, headers, setup, observed_location_id=str(uuid.uuid4())).status_code == 422
    )
    assert observe(client, headers, setup, asset_version=1).status_code == 409
    assert (
        client.patch(
            f"{ROOT}/locations/{setup[2]['id']}",
            headers=headers,
            json={"version": 1, "is_active": False},
        ).status_code
        == 200
    )
    assert observe(client, headers, setup, observed_location_id=setup[2]["id"]).status_code == 409
    # Evidence does not increment the asset version, so max-version assets remain auditable.
    db.execute(update(AssetUnit).values(version=2147483647))
    db.commit()
    assert observe(client, headers, setup, asset_version=2147483647).status_code == 201
    assert movement_cases.asset_state(client, setup)["version"] == 2147483647


def test_get_filters_no_side_effects_and_unknowns(client, headers, setup, db, catalog_model):
    a = observe(client, headers, setup).json()
    observe(client, headers, setup, observed_location_id=setup[2]["id"])
    observe(client, headers, setup, asset_id=None, asset_version=None)
    assert review(client, headers, a).status_code == 200
    path = ROOT + "/location-observations"
    assert client.get(path + "?review_status=PENDING").json()["total"] == 2
    assert client.get(path + "?comparison_status=LOCATION_CONFLICT").json()["total"] == 1
    assert client.get(path + "?unlinked_only=true").json()["total"] == 1
    assert client.get(path + f"?asset_id={setup[0]['id']}").json()["total"] == 2
    assert client.get(path + "?page_size=1").json()["total_pages"] == 3
    assert client.get(path + "?page=100").json()["items"] == []
    asset_path = f"{ROOT}/assets/{setup[0]['id']}"
    before = fingerprint(db)
    for route in (
        path,
        path + "/" + a["id"],
        asset_path + "/timeline",
        asset_path + "/location-status",
        asset_path + "/location-observations",
    ):
        response = client.get(route)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert fingerprint(db) == before
    for query in ("page=0", "page_size=101", "unknown=bad", "review_status=BAD"):
        assert client.get(path + "?" + query).status_code == 422
    assert client.get(path + f"?unlinked_only=true&asset_id={setup[0]['id']}").status_code == 422
    unknown = str(uuid.uuid4())
    for endpoint in ("timeline", "location-status", "location-observations"):
        assert client.get(f"{ROOT}/assets/{unknown}/{endpoint}").status_code == 404
    assert client.get(path + "/" + unknown).status_code == 404
    assert review(client, headers, {"id": unknown}).status_code == 404
    other = asset_api.create(client, headers, catalog_model, "AP-004")
    assert client.get(f"{ROOT}/assets/{other['id']}/location-observations").json()["items"] == []


def test_timeline_sources_filters_and_pagination(client, headers, setup):
    observe(client, headers, setup)
    assert (
        client.patch(
            f"{ROOT}/assets/{setup[0]['id']}",
            headers=headers,
            json={"version": 2, "notes": "Metadata edit"},
        ).status_code
        == 200
    )
    page = timeline(client, setup)
    assert page["total"] == 4
    assert {x["event_type"] for x in page["items"]} == {
        "UPDATE",
        "LOCATION_OBSERVED",
        "INITIAL_PLACEMENT",
        "CREATE",
    }
    # Preserve legacy stored precision; SQLite metadata server defaults have whole seconds.
    keys = [
        (
            datetime.fromisoformat(x["occurred_at"]).replace(tzinfo=UTC),
            datetime.fromisoformat(x["recorded_at"]).replace(tzinfo=UTC),
            x["source"],
            x["id"],
        )
        for x in page["items"]
    ]
    assert keys == sorted(keys, reverse=True)
    metadata = next(x for x in page["items"] if x["event_type"] == "UPDATE")
    assert metadata["source"] == "METADATA" and metadata["correlation_id"] is None
    assert metadata["payload_json"]["before_json"]["asset"]["notes"] is None
    assert metadata["payload_json"]["after_json"]["asset"]["notes"] == "Metadata edit"
    assert timeline(client, setup, "?source=LOCATION")["total"] == 2
    assert timeline(client, setup, "?event_type=CREATE")["total"] == 1
    assert timeline(client, setup, "?event_type=not-existing")["total"] == 0
    first = timeline(client, setup, "?page_size=1")
    assert first["total_pages"] == 4
    assert (
        timeline(client, setup, "?page_size=1&page=2")["items"][0]["event_type"]
        == page["items"][1]["event_type"]
    )
    assert timeline(client, setup, "?page=100")["items"] == []
    for query in ("source=BAD", "page=0", "page_size=101", "unknown=bad"):
        assert client.get(f"{ROOT}/assets/{setup[0]['id']}/timeline?" + query).status_code == 422


@pytest.mark.parametrize("table", ["asset_events", "asset_change_events"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_event_sources_append_only(client, headers, setup, db, table, operation):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                f"{operation} {table} SET actor_id=actor_id"
                if operation == "UPDATE"
                else f"DELETE FROM {table}"
            )
        )
        db.commit()
    db.rollback()


@pytest.mark.parametrize("linked", [True, False])
@pytest.mark.parametrize("phase", ["create", "review"])
def test_event_failure_rolls_back(client, headers, setup, db, linked, phase):
    changes = {} if linked else {"asset_id": None, "asset_version": None}
    observation = observe(client, headers, setup, **changes).json() if phase == "review" else None
    before = fingerprint(db)
    target = AssetLocationEvent if linked else AuditEvent

    def fail(*args):
        raise RuntimeError("Synthetic observation audit failure")

    event.listen(target, "before_insert", fail)
    try:
        response = (
            observe(client, headers, setup, **changes)
            if phase == "create"
            else review(client, headers, observation)
        )
        assert response.status_code == 500
    finally:
        event.remove(target, "before_insert", fail)
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "field",
    [
        "evidence_note",
        "observed_location_id",
        "observed_at",
        "asset_id",
        "snapshot_json",
        "comparison_status",
    ],
)
def test_evidence_database_immutable(client, headers, setup, db, field):
    observe(client, headers, setup)
    changes = {
        "evidence_note": "Changed",
        "observed_location_id": uuid.UUID(setup[2]["id"]),
        "observed_at": datetime.now(UTC),
        "asset_id": None,
        "snapshot_json": {},
        "comparison_status": ObservationComparison.UNPLACED,
    }
    with pytest.raises(IntegrityError):
        db.execute(update(LocationObservation).values(**{field: changes[field]}))
        db.commit()
    db.rollback()


def test_review_terminal_delete_and_fk_guards(client, headers, setup, db):
    observation = observe(client, headers, setup).json()
    assert review(client, headers, observation).status_code == 200
    for statement in (
        update(LocationObservation).values(review_reason="Changed"),
        text("DELETE FROM location_observations"),
    ):
        with pytest.raises(IntegrityError):
            db.execute(statement)
            db.commit()
        db.rollback()


def test_preserved_snapshots_after_archiving_locations(client, headers, setup, db):
    observation = observe(client, headers, setup, observed_location_id=setup[2]["id"]).json()
    event_before = timeline(client, setup, "?event_type=LOCATION_OBSERVED")["items"][0]
    for loc in setup[1:]:
        assert (
            client.patch(
                f"{ROOT}/locations/{loc['id']}",
                headers=headers,
                json={"version": 1, "is_active": False, "name": "Renamed"},
            ).status_code
            == 200
        )
    assert (
        client.get(f"{ROOT}/location-observations/{observation['id']}").json()["snapshot_json"]
        == observation["snapshot_json"]
    )
    assert timeline(client, setup, "?event_type=LOCATION_OBSERVED")["items"][0] == event_before
    assert review(client, headers, observation).status_code == 200


def test_transport_csrf_and_immutable_routes(client, headers, setup):
    body = {"observed_location_id": setup[1]["id"], "evidence_note": "Synthetic"}
    path = ROOT + "/location-observations"
    assert client.post(path, json=body).status_code == 403
    assert (
        client.post(
            path, headers={**headers, "Origin": "https://bad.invalid"}, json=body
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
    observation = observe(client, headers, setup).json()
    assert (
        client.post(
            path + f"/{observation['id']}/review",
            json={"version": 1, "reason": "Bad", "review_status": "DISMISSED"},
        ).status_code
        == 403
    )
    for method in (client.patch, client.delete):
        assert method(path + "/" + observation["id"], headers=headers).status_code == 405
        assert (
            method(f"{ROOT}/assets/{setup[0]['id']}/timeline", headers=headers).status_code == 405
        )
    assert (
        client.post(
            f"{ROOT}/assets/{setup[0]['id']}/timeline", headers=headers, json={}
        ).status_code
        == 405
    )


def test_migration_preserves_populated_predecessor(factory, client, headers, setup, db):
    move(client, headers, setup)
    before = fingerprint(db)
    db.rollback()
    with factory.kw["bind"].connect() as c:
        config = Config("alembic.ini")
        config.attributes["connection"] = c
        command.downgrade(config, "0008_asset_movements")
        command.upgrade(config, "head")
        command.check(config)
        c.commit()
    assert fingerprint(db) == before


def test_populated_downgrade_refused(factory, client, headers, setup):
    observe(client, headers, setup)
    with factory.kw["bind"].connect() as c:
        config = Config("alembic.ini")
        config.attributes["connection"] = c
        with pytest.raises(RuntimeError, match="Cannot downgrade populated"):
            command.downgrade(config, "0008_asset_movements")
        c.rollback()
    assert timeline(client, setup)["total"] == 3


@pytest.mark.parametrize("race", ["approve", "review", "archive"])
def test_postgres_observation_races(client, headers, setup, db, factory, user, race):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Independent PostgreSQL sessions")
    movement = movement_cases.request(client, headers, setup).json()
    observation = observe(client, headers, setup).json() if race == "review" else None
    actor_id = user.id
    data = ObservationCreate(
        asset_id=uuid.UUID(setup[0]["id"]),
        asset_version=2,
        observed_location_id=uuid.UUID(setup[1]["id"]),
        evidence_note="Concurrent evidence",
    )
    db.rollback()
    barrier = Barrier(2)

    def worker(second):
        with factory() as session:
            actor = session.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                if race == "review":
                    review_observation(
                        session,
                        uuid.UUID(observation["id"]),
                        ObservationReview(
                            version=1,
                            review_status="ACKNOWLEDGED" if second else "DISMISSED",
                            reason="Concurrent review",
                        ),
                        actor,
                    )
                elif second and race == "approve":
                    decide_movement(
                        session,
                        uuid.UUID(movement["id"]),
                        1,
                        MovementStatus.APPROVED,
                        "Move",
                        actor,
                    )
                elif second and race == "archive":
                    save_location(
                        session,
                        actor,
                        LocationPatch(version=1, is_active=False),
                        uuid.UUID(setup[1]["id"]),
                    )
                else:
                    create_observation(session, data, actor)
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [False, True]))
    if race == "review":
        assert sorted(results) == [200, 409]
    else:
        assert results[1] == 200 and results[0] in (200, 409)
    db.expire_all()
    asset = db.get(AssetUnit, uuid.UUID(setup[0]["id"]))
    assert asset.version == (3 if race == "approve" else 2)
    assert str(asset.current_location_id) == setup[2 if race == "approve" else 1]["id"]
    if race != "review":
        observations = list(db.scalars(select(LocationObservation)))
        assert len(observations) == (1 if results[0] == 200 else 0)
        if observations:
            assert observations[0].asset_version_at_recording == 2
            assert observations[0].official_location_id_at_recording == uuid.UUID(setup[1]["id"])


def test_timeline_cross_source_id_and_time_ties(client, headers, setup, db, user):
    shared = uuid.uuid4()
    stamp = datetime.now(UTC) - timedelta(days=1)
    db.add_all(
        [
            AssetChangeEvent(
                id=shared,
                asset_id=uuid.UUID(setup[0]["id"]),
                actor_id=user.id,
                event_type=AssetEventType.UPDATE,
                recorded_at=stamp,
                before_json=None,
                after_json={"synthetic": "metadata"},
            ),
            AssetLocationEvent(
                id=shared,
                asset_id=uuid.UUID(setup[0]["id"]),
                actor_id=user.id,
                event_type="UPDATE",
                occurred_at=stamp,
                recorded_at=stamp,
                correlation_id=uuid.uuid4(),
                payload_json={"synthetic": "location"},
            ),
        ]
    )
    db.commit()
    page = timeline(client, setup, "?event_type=UPDATE")
    assert page["total"] == 2
    assert [x["source"] for x in page["items"]] == ["METADATA", "LOCATION"]
    assert page["items"][0]["payload_json"]["after_json"]["synthetic"] == "metadata"
    assert page["items"][1]["payload_json"]["synthetic"] == "location"


@pytest.mark.parametrize(
    "changes",
    [
        {"version": 0},
        {"asset_id": uuid.uuid4()},
        {"observed_location_id": uuid.uuid4()},
        {"evidence_note": " "},
        {"review_status": ObservationReviewStatus.ACKNOWLEDGED},
        {"comparison_status": ObservationComparison.UNLINKED},
        {"official_location_id_at_recording": None},
    ],
)
def test_database_constraints(client, headers, setup, db, user, changes):
    values = dict(
        id=uuid.uuid4(),
        asset_id=uuid.UUID(setup[0]["id"]),
        observed_location_id=uuid.UUID(setup[1]["id"]),
        observed_by=user.id,
        observed_at=datetime.now(UTC),
        recorded_at=datetime.now(UTC),
        evidence_note="Synthetic",
        official_location_id_at_recording=uuid.UUID(setup[1]["id"]),
        asset_version_at_recording=2,
        comparison_status=ObservationComparison.MATCH,
        snapshot_json={},
        review_status=ObservationReviewStatus.PENDING,
        version=1,
    )
    values.update(changes)
    before = fingerprint(db)
    with pytest.raises(IntegrityError):
        db.execute(insert(LocationObservation).values(**values))
        db.commit()
    db.rollback()
    assert fingerprint(db) == before
