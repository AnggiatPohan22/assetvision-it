"""Task 2-01 hierarchy, retention, audit, RBAC and PostgreSQL race regressions."""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from conftest import csrf_headers, session_headers, sign_in
from fastapi import HTTPException
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError
from test_asset_csv import fingerprint

from app.location_schemas import LocationCreate, LocationPatch
from app.location_service import save_location
from app.locations import Location
from app.models import AuditEvent, Role, User
from app.seed_assets import seed_assets

ROOT = "/api/v1/locations"


@pytest.fixture()
def headers(client, user, password):
    assert sign_in(client, password).status_code == 200
    return session_headers(client)


def create(client, headers, code="site", parent=None, kind="SITE", **extra):
    response = client.post(
        ROOT,
        headers=headers,
        json={
            "code": code,
            "name": code.title(),
            "kind": kind,
            "parent_id": parent,
            **extra,
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_hierarchy_filters_tree_archive_and_audit(client, headers, db, user):
    site = create(client, headers, "  RESORT  ", name=" Synthetic   Resort ")
    assert (site["code"], site["name"], site["version"]) == ("resort", "Synthetic Resort", 1)
    area = create(client, headers, "garden", site["id"], "AREA")
    villa1 = create(client, headers, "villa-1", area["id"], "BUILDING")
    create(client, headers, "villa-10", area["id"], "BUILDING")
    floor = create(client, headers, "ground", villa1["id"], "FLOOR")
    lounge = create(client, headers, "lounge", floor["id"], "ROOM")
    create(client, headers, "lobby", floor["id"], "ROOM")
    create(client, headers, "corner", lounge["id"], "SPOT")
    tree = client.get(ROOT + "/tree").json()
    assert tree["total"] == len(tree["items"]) == 8
    assert {x["id"]: x["parent_id"] for x in tree["items"]}[floor["id"]] == villa1["id"]
    for query, count in (
        ("roots_only=true", 1),
        (f"parent_id={area['id']}", 2),
        ("kind=ROOM", 2),
        ("search=Villa", 2),
        ("search=%25", 0),
    ):
        response = client.get(ROOT + "?" + query)
        assert response.status_code == 200 and response.json()["total"] == count
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
    page = client.get(ROOT + "?page_size=3&page=2").json()
    assert len(page["items"]) == 3 and page["total_pages"] == 3
    assert client.get(ROOT + "?page=100").json()["items"] == []
    before = fingerprint(db)
    client.get(ROOT + "/tree")
    client.get(ROOT + "/" + lounge["id"])
    assert fingerprint(db) == before
    path = ROOT + "/" + site["id"]
    archived = client.patch(path, headers=headers, json={"version": 1, "is_active": False})
    assert archived.status_code == 200 and archived.json()["version"] == 2
    assert client.get(ROOT + "/tree").json()["total"] == 8
    assert client.get(ROOT + "?is_active=false").json()["total"] == 1
    assert client.get(ROOT + "/" + area["id"]).json()["parent_id"] == site["id"]
    audits = list(db.scalars(select(AuditEvent).where(AuditEvent.action.like("location_%"))))
    assert len(audits) == 9
    archive = next(a for a in audits if a.action == "location_archive")
    assert archive.actor_id == user.id and archive.created_at is not None
    assert json.loads(archive.details["before"])["is_active"] is True
    assert json.loads(archive.details["after"])["version"] == 2
    assert client.delete(path, headers=headers).status_code == 405


def test_parent_unique_codes_cycles_and_versions(client, headers):
    a = create(client, headers, "a")
    b = create(client, headers, "b")
    child = create(client, headers, "room", a["id"], "ROOM")
    create(client, headers, "room", b["id"], "ROOM")
    for parent in (None, a["id"]):
        code = "a" if parent is None else "room"
        assert (
            client.post(
                ROOT,
                headers=headers,
                json={"code": code, "name": "Duplicate", "kind": "ROOM", "parent_id": parent},
            ).status_code
            == 409
        )
    for target in (a["id"], child["id"]):
        assert (
            client.patch(
                ROOT + "/" + a["id"], headers=headers, json={"version": 1, "parent_id": target}
            ).status_code
            == 409
        )
    assert (
        client.patch(
            ROOT + "/" + child["id"],
            headers=headers,
            json={"version": 1, "parent_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )
    path = ROOT + "/" + child["id"]
    assert (
        client.patch(path, headers=headers, json={"version": 1, "parent_id": None}).status_code
        == 200
    )
    assert (
        client.patch(path, headers=headers, json={"version": 1, "name": "Stale"}).status_code == 409
    )
    assert client.get(path).json()["parent_id"] is None
    assert (
        client.patch(path, headers=headers, json={"version": 2, "parent_id": b["id"]}).status_code
        == 409
    )
    assert client.get(path).json()["version"] == 2


def test_archived_parent_policy_and_restore(client, headers):
    a = create(client, headers, "a")
    child = create(client, headers, "child", a["id"])
    other = create(client, headers, "other")
    assert (
        client.patch(
            ROOT + "/" + a["id"], headers=headers, json={"version": 1, "is_active": False}
        ).status_code
        == 200
    )
    assert (
        client.post(
            ROOT,
            headers=headers,
            json={"code": "new", "name": "New", "kind": "SPOT", "parent_id": a["id"]},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            ROOT + "/" + other["id"], headers=headers, json={"version": 1, "parent_id": a["id"]}
        ).status_code
        == 409
    )
    path = ROOT + "/" + child["id"]
    assert (
        client.patch(path, headers=headers, json={"version": 1, "name": "Historical"}).status_code
        == 200
    )
    assert (
        client.patch(path, headers=headers, json={"version": 2, "is_active": False}).status_code
        == 200
    )
    assert (
        client.patch(path, headers=headers, json={"version": 3, "is_active": True}).status_code
        == 409
    )
    assert (
        client.patch(
            path, headers=headers, json={"version": 3, "is_active": True, "parent_id": other["id"]}
        ).status_code
        == 200
    )
    # Archived codes remain reserved.
    assert (
        client.post(
            ROOT, headers=headers, json={"code": "a", "name": "Reuse", "kind": "SITE"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"code": "bad/code"},
        {"code": "x--y"},
        {"name": " "},
        {"kind": "GPS"},
        {"latitude": 91, "longitude": 0},
        {"latitude": 0},
        {"longitude": 0},
        {"latitude": "1", "longitude": 0},
        {"latitude": True, "longitude": 0},
        {"latitude": 0, "longitude": 181},
        {"gps_accuracy_m": 2},
        {"latitude": 0, "longitude": 0, "gps_accuracy_m": -1},
        {"latitude": 0, "longitude": 0, "gps_recorded_at": "2026-10-19T00:00:00"},
        {"id": str(uuid.uuid4())},
        {"created_by": str(uuid.uuid4())},
        {"version": 1},
        {"floorplan_id": str(uuid.uuid4())},
        {"pin_x": 0.5},
    ],
)
def test_invalid_create_no_side_effect(client, headers, db, fields):
    before = fingerprint(db)
    response = client.post(
        ROOT, headers=headers, json={"code": "invalid", "name": "Invalid", "kind": "SITE", **fields}
    )
    assert response.status_code == 422
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"version": True, "name": "X"},
        {"version": 0, "name": "X"},
        {"name": None},
        {"kind": None},
        {"is_active": None},
        {"code": None},
        {"latitude": None},
        {"gps_accuracy_m": -2},
        {"id": str(uuid.uuid4())},
    ],
)
def test_invalid_patch_merged_validation(client, headers, db, fields):
    loc = create(client, headers, latitude=0, longitude=0)
    before = fingerprint(db)
    response = client.patch(ROOT + "/" + loc["id"], headers=headers, json={"version": 1, **fields})
    assert response.status_code == 422
    assert fingerprint(db) == before


def test_coordinate_pair_timestamp_and_clear(client, headers):
    loc = create(
        client,
        headers,
        latitude=-8.6,
        longitude=115.2,
        gps_accuracy_m=3,
        gps_recorded_at="2026-10-19T08:00:00+08:00",
    )
    path = ROOT + "/" + loc["id"]
    assert loc["gps_recorded_at"] is not None
    assert (
        client.patch(path, headers=headers, json={"version": 1, "name": "GPS site"}).status_code
        == 200
    )
    assert (
        client.patch(
            path, headers=headers, json={"version": 2, "latitude": None, "longitude": None}
        ).status_code
        == 422
    )
    cleared = client.patch(
        path,
        headers=headers,
        json={
            "version": 2,
            "latitude": None,
            "longitude": None,
            "gps_accuracy_m": None,
            "gps_recorded_at": None,
        },
    )
    assert cleared.status_code == 200 and cleared.json()["latitude"] is None


@pytest.mark.parametrize(
    "query",
    [
        "kind=bad",
        "page=0",
        "page_size=101",
        "parent_id=bad",
        "roots_only=true&parent_id=00000000-0000-0000-0000-000000000001",
        "unknown=x",
    ],
)
def test_invalid_query(client, headers, query):
    assert client.get(ROOT + "?" + query).status_code == 422


@pytest.mark.parametrize("role", [Role.OFFICER, Role.VIEWER])
def test_read_roles_cannot_mutate(client, headers, db, user, role):
    loc = create(client, headers)
    user.role = role
    db.commit()
    before = fingerprint(db)
    for path in (ROOT, ROOT + "/tree", ROOT + "/" + loc["id"]):
        assert client.get(path).status_code == 200
    assert (
        client.post(
            ROOT, headers=headers, json={"code": "other", "name": "Other", "kind": "SITE"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            ROOT + "/" + loc["id"], headers=headers, json={"version": 1, "is_active": False}
        ).status_code
        == 403
    )
    assert fingerprint(db) == before


def test_anonymous_revoked_inactive_and_csrf(client, headers, db, user):
    loc = create(client, headers)
    path = ROOT + "/" + loc["id"]
    before = fingerprint(db)
    assert client.patch(path, json={"version": 1, "name": "Denied"}).status_code == 403
    assert (
        client.patch(
            path,
            headers={**headers, "Origin": "https://evil.invalid"},
            json={"version": 1, "name": "Denied"},
        ).status_code
        == 403
    )
    user.is_active = False
    db.commit()
    assert client.get(ROOT).status_code == 401
    user.is_active = True
    db.commit()
    assert fingerprint(db) == before
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get(ROOT).status_code == 401
    client.cookies.clear()
    for suffix in ("", "/tree", "/" + loc["id"]):
        assert client.get(ROOT + suffix).status_code == 401
    assert (
        client.post(
            ROOT,
            headers=csrf_headers(client),
            json={"code": "anon", "name": "Anon", "kind": "SITE"},
        ).status_code
        == 401
    )


def test_bounded_body_not_found_and_audit_failure(client, headers, db, monkeypatch):
    assert client.get(ROOT + "/" + str(uuid.uuid4())).status_code == 404
    assert (
        client.post(
            ROOT, headers={**headers, "content-type": "application/json"}, content=(b" " * 17000)
        ).status_code
        == 413
    )
    assert client.post(ROOT, headers=headers, content=b"{}").status_code == 415
    before = fingerprint(db)

    def fail(*args):
        raise RuntimeError("sensitive input must not be returned")

    monkeypatch.setattr("app.location_service.write_audit", fail)
    response = client.post(
        ROOT, headers=headers, json={"code": "rollback", "name": "Rollback", "kind": "SITE"}
    )
    assert response.status_code == 500 and response.json() == {"detail": "Internal server error"}
    assert fingerprint(db) == before


def test_database_guards_direct_sql(db, user):
    a = save_location(db, user, LocationCreate(code="a", name="A", kind="SITE"))
    b = save_location(db, user, LocationCreate(code="b", name="B", kind="ROOM", parent_id=a.id))
    for statement in (
        update(Location).where(Location.id == a.id).values(parent_id=b.id),
        update(Location).where(Location.id == a.id).values(parent_id=a.id),
        update(Location).where(Location.id == a.id).values(id=uuid.uuid4()),
        update(Location).where(Location.id == a.id).values(code="UPPER"),
        update(Location).where(Location.id == a.id).values(latitude=1),
        update(Location).where(Location.id == a.id).values(gps_accuracy_m=-1),
        Location.__table__.delete().where(Location.id == b.id),
    ):
        with pytest.raises(IntegrityError):
            db.execute(statement)
            db.commit()
        db.rollback()


def test_location_migration_preserves_entire_predecessor(factory, db, user):
    seed_assets(db, user.id)
    db.commit()
    before = fingerprint(db)
    db.rollback()
    with factory.kw["bind"].connect() as c:
        config = Config("alembic.ini")
        config.attributes["connection"] = c
        command.downgrade(config, "0005_asset_imports")
        assert "locations" not in inspect(c).get_table_names()
        command.upgrade(config, "head")
        command.check(config)
        c.commit()
    assert fingerprint(db) == before


def test_populated_downgrade_refused(factory, db, user):
    loc = save_location(db, user, LocationCreate(code="preserve", name="Preserve", kind="SITE"))
    db.rollback()  # Release read locks before the successor migration changes the asset FK.
    with factory.kw["bind"].connect() as c:
        config = Config("alembic.ini")
        config.attributes["connection"] = c
        with pytest.raises(RuntimeError, match="Cannot downgrade populated"):
            command.downgrade(config, "0005_asset_imports")
        c.rollback()
    assert db.get(Location, loc.id).name == "Preserve"


@pytest.mark.parametrize("race", ["same-version", "cycle", "direct-cycle"])
def test_postgres_concurrent_hierarchy(factory, db, user, race):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory locks and independent concurrent sessions")
    a = save_location(db, user, LocationCreate(code="a", name="A", kind="SITE"))
    b = save_location(db, user, LocationCreate(code="b", name="B", kind="SITE"))
    ids, actor_id = [a.id, b.id], user.id
    barrier = Barrier(2)

    def worker(n):
        with factory() as s:
            actor = s.get(User, actor_id)
            barrier.wait(timeout=15)
            if race == "direct-cycle":
                try:
                    s.execute(
                        update(Location).where(Location.id == ids[n]).values(parent_id=ids[1 - n])
                    )
                    s.commit()
                    return 200
                except IntegrityError:
                    s.rollback()
                    return 409
            try:
                changes = (
                    {"name": f"Writer {n}"} if race == "same-version" else {"parent_id": ids[1 - n]}
                )
                save_location(
                    s,
                    actor,
                    LocationPatch(version=1, **changes),
                    ids[0] if race == "same-version" else ids[n],
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, range(2))) == [200, 409]
    db.expire_all()
    assert not (
        db.get(Location, ids[0]).parent_id == ids[1]
        and db.get(Location, ids[1]).parent_id == ids[0]
    )
