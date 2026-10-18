import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import session_headers, sign_in
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from test_asset_csv import fingerprint

from app.asset_service import update_asset
from app.assets import AssetChangeEvent, AssetIdentifier, AssetUnit
from app.catalog import DeviceCategory, DeviceModel, Manufacturer
from app.config import get_settings
from app.models import AuditEvent, Role
from app.seed_assets import CODES, MARKER, SeedConflict, seed_assets, seed_id


def run_seed(factory, actor_id):
    with factory.begin() as session:
        return seed_assets(session, actor_id)


def test_seed_cli_requires_explicit_actor_and_confirmation(monkeypatch):
    from app.seed_assets import main

    for arguments in (["seed_assets"], ["seed_assets", "--actor-id", str(uuid.uuid4())]):
        monkeypatch.setattr("sys.argv", arguments)
        with pytest.raises(SystemExit) as failure:
            main()
        assert failure.value.code == 2


@pytest.mark.parametrize("conflict", ["partial", "uuid"])
def test_seed_refuses_partial_batch_or_uuid_collision(db, factory, user, conflict):
    from app.asset_service import audit
    from app.assets import AssetEventType

    category = DeviceCategory(code="access-point", name="Access Point")
    maker = Manufacturer(name="Ruijie")
    db.add_all([category, maker])
    db.flush()
    model = DeviceModel(
        category_id=category.id,
        manufacturer_id=maker.id,
        model_name="AP680-L",
        environment="indoor",
    )
    db.add(model)
    db.flush()
    unit = AssetUnit(
        id=seed_id("AP-001"),
        asset_code="AP-001" if conflict == "partial" else "OTHER-UUID",
        device_model_id=model.id,
        notes=MARKER,
    )
    db.add(unit)
    audit(db, unit, user, AssetEventType.CREATE, None)
    db.commit()
    before = fingerprint(db)
    db.rollback()
    with pytest.raises(SeedConflict):
        run_seed(factory, user.id)
    assert fingerprint(db) == before


def test_seed_acceptance_search_audit_and_repeat(client, db, factory, user, password):
    result = run_seed(factory, user.id)
    assert result == {
        "created_assets": 8,
        "created_identifiers": 22,
        "created_catalog": 3,
        "existing_assets": 0,
    }
    units = list(db.scalars(select(AssetUnit).order_by(AssetUnit.asset_code)))
    assert tuple(unit.asset_code for unit in units) == CODES
    assert all(unit.notes == MARKER for unit in units)
    assert {unit.id for unit in units} == {seed_id(code) for code in CODES}
    assert len({unit.device_model_id for unit in units}) == 1
    model = db.get(DeviceModel, units[0].device_model_id)
    assert model.model_name == "AP680-L"
    assert db.get(Manufacturer, model.manufacturer_id).name == "Ruijie"
    claims = list(db.scalars(select(AssetIdentifier)))
    serials = {
        claim.asset_id: claim.raw_value
        for claim in claims
        if claim.identifier_type == "SERIAL_NUMBER"
    }
    assert serials[seed_id("AP-001")] == "123456789"
    assert serials[seed_id("AP-002")] == "2158763"
    assert seed_id("AP-004") not in serials and seed_id("AP-005") not in serials
    assert all(
        claim.source == "IMPORT" and claim.verification_status == "UNVERIFIED" for claim in claims
    )
    events = list(db.scalars(select(AssetChangeEvent)))
    assert len(events) == 30 and all(e.actor_id == user.id and e.recorded_at for e in events)
    assert sum(e.event_type == "CREATE" for e in events) == 8
    assert sum(e.event_type == "IDENTIFIER_ADD" for e in events) == 22
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 3
    before = fingerprint(db)
    db.rollback()
    assert run_seed(factory, user.id)["created_assets"] == 0
    assert fingerprint(db) == before
    assert sign_in(client, password).status_code == 200
    for search, code in [
        ("AP-001", "AP-001"),
        ("123456789", "AP-001"),
        ("2158763", "AP-002"),
        ("0200001b0004", "AP-004"),
    ]:
        response = client.get("/api/v1/assets", params={"search": search}).json()
        assert response["total"] == 1 and response["items"][0]["asset_code"] == code
    assert client.get(f"/api/v1/assets/{seed_id('AP-004')}/events").json()["total"] == 3
    headers = session_headers(client)
    current = client.get(f"/api/v1/assets/{seed_id('AP-001')}").json()
    assert (
        client.patch(
            f"/api/v1/assets/{seed_id('AP-001')}",
            headers=headers,
            json={"version": current["version"], "asset_code": "RENAMED"},
        ).status_code
        == 422
    )


@pytest.mark.parametrize("mode", ["officer", "inactive", "missing", "production"])
def test_seed_denies_invalid_actor_or_environment(db, factory, user, monkeypatch, mode):
    if mode == "officer":
        user.role = Role.OFFICER
    elif mode == "inactive":
        user.is_active = False
    elif mode == "production":
        monkeypatch.setattr(get_settings(), "app_env", "production")
    db.commit()
    before = fingerprint(db)
    db.rollback()
    with pytest.raises(SeedConflict):
        run_seed(factory, uuid.uuid4() if mode == "missing" else user.id)
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "target", ["code", "archived_category", "archived_model", "foreign_unit", "identifier"]
)
def test_seed_refuses_conflicts_without_adopting_or_modifying_rows(db, factory, user, target):
    category = DeviceCategory(code="access-point", name="Existing category", description="Keep")
    maker = Manufacturer(name="Ruijie", website="https://example.com")
    db.add_all([category, maker])
    db.flush()
    model = DeviceModel(
        category_id=category.id,
        manufacturer_id=maker.id,
        model_name="AP680-L",
        environment="indoor",
        specs={"existing": True},
    )
    db.add(model)
    db.flush()
    if target == "archived_category":
        category.is_active = False
    elif target == "archived_model":
        model.is_active = False
    else:
        unit = AssetUnit(
            asset_code="AP-001" if target == "code" else "EXISTING-001", device_model_id=model.id
        )
        db.add(unit)
        db.flush()
        if target == "identifier":
            # A different model holds the colliding claim, so the identifier guard is exercised.
            other = DeviceModel(
                category_id=category.id,
                manufacturer_id=maker.id,
                model_name="Existing other model",
                environment="indoor",
            )
            db.add(other)
            db.flush()
            unit.device_model_id = other.id
            db.add(
                AssetIdentifier(
                    asset_id=unit.id,
                    identifier_type="SERIAL_NUMBER",
                    raw_value="123456789",
                    source="MANUAL",
                )
            )
    db.commit()
    before = fingerprint(db)
    db.rollback()
    with pytest.raises(SeedConflict):
        run_seed(factory, user.id)
    assert fingerprint(db) == before


def test_seed_reuses_active_catalog_without_changes_and_preserves_later_unit_edits(
    db, factory, user
):
    category = DeviceCategory(code="access-point", name="Existing category")
    maker = Manufacturer(name="Ruijie", website="https://example.com")
    db.add_all([category, maker])
    db.flush()
    model = DeviceModel(
        category_id=category.id,
        manufacturer_id=maker.id,
        model_name="AP680-L",
        description="Preserve me",
        environment="indoor",
        specs={"ports": 2},
    )
    db.add(model)
    db.commit()
    before = {
        key: value
        for key, value in fingerprint(db).items()
        if key in {"device_categories", "manufacturers", "device_models", "users"}
    }
    db.rollback()
    assert run_seed(factory, user.id)["created_catalog"] == 0
    assert all(fingerprint(db)[key] == value for key, value in before.items())
    unit = db.get(AssetUnit, seed_id("AP-004"))
    update_asset(
        db, unit.id, unit.version, {"notes": "User edited", "lifecycle_status": "ARCHIVED"}, user
    )
    edited = fingerprint(db)
    db.rollback()
    assert run_seed(factory, user.id)["created_assets"] == 0
    assert fingerprint(db) == edited


@pytest.mark.parametrize(
    "audit_kind,position",
    [(AuditEvent, 2), (AssetChangeEvent, 1), (AssetChangeEvent, 18), (AssetChangeEvent, 30)],
)
def test_seed_audit_failure_rolls_back_catalog_assets_claims_events(
    db, factory, user, audit_kind, position
):
    before = fingerprint(db)
    db.rollback()
    calls = 0

    def reject(mapper, connection, target):
        nonlocal calls
        calls += 1
        if calls == position:
            raise IntegrityError("synthetic audit failure", {}, Exception())

    event.listen(audit_kind, "before_insert", reject)
    try:
        with pytest.raises(IntegrityError):
            run_seed(factory, user.id)
    finally:
        event.remove(audit_kind, "before_insert", reject)
    assert fingerprint(db) == before


def test_seed_same_batch_concurrent_postgres(db, factory, user):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL advisory and reference row locks")
    barrier = Barrier(2)

    def run(_):
        barrier.wait(timeout=10)
        return run_seed(factory, user.id)["created_assets"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == [0, 8]
    assert db.scalar(select(func.count()).select_from(AssetUnit)) == 8
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 30
