import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.assets import (
    AssetChangeEvent,
    AssetCondition,
    AssetEventType,
    AssetIdentifier,
    AssetUnit,
    IdentifierSource,
    IdentifierType,
    LifecycleStatus,
    normalize_identifier,
)
from app.catalog import DeviceCategory, DeviceModel, Environment, Manufacturer
from app.db import Base
from app.models import AuditEvent, AuthSession, DeviceReferenceImage, StorageCleanupJob


@pytest.fixture()
def asset_model(db):
    category = DeviceCategory(code="synthetic-ap", name="Synthetic AP")
    manufacturer = Manufacturer(name="Synthetic maker")
    db.add_all([category, manufacturer])
    db.flush()
    model = DeviceModel(
        manufacturer_id=manufacturer.id,
        category_id=category.id,
        model_name="Synthetic AP680-L",
        environment=Environment.OUTDOOR,
    )
    db.add(model)
    db.commit()
    return model


@pytest.fixture()
def asset(db, asset_model):
    unit = AssetUnit(asset_code=" ap-001 ", device_model_id=asset_model.id)
    db.add(unit)
    db.commit()
    return unit


def claim(asset, **overrides):
    values = dict(
        asset_id=asset.id,
        identifier_type=IdentifierType.MAC_LAN,
        raw_value="aa-bb-cc-dd-ee-ff",
        source=IdentifierSource.MANUAL,
    )
    return AssetIdentifier(**(values | overrides))


def test_unit_without_serial_and_multiple_units(db, asset, asset_model):
    other = AssetUnit(asset_code="AP-002", device_model_id=asset_model.id)
    db.add(other)
    db.commit()
    assert asset.asset_code == "AP-001"
    assert asset.id != other.id and asset.device_model_id == other.device_model_id
    assert asset.lifecycle_status == LifecycleStatus.IN_STOCK
    assert asset.condition == AssetCondition.UNKNOWN
    assert asset.version == 1 and asset.created_at and asset.updated_at
    assert asset.purchase_date is None and asset.installed_at is None
    assert db.scalar(select(func.count()).select_from(AssetIdentifier)) == 0


@pytest.mark.parametrize("code", ["", " ", "AP 1", "AP/1", "é-1", "A" * 51, "-AP"])
def test_invalid_code_at_orm(code):
    with pytest.raises(ValueError):
        AssetUnit(asset_code=code)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE assets SET asset_code='AP-999'",
        "UPDATE assets SET id=:replacement",
        "DELETE FROM assets",
        "UPDATE assets SET lifecycle_status='invalid'",
        "UPDATE assets SET condition='invalid'",
        "UPDATE assets SET version=0",
        "UPDATE assets SET device_model_id=:replacement",
        "DELETE FROM device_models",
    ],
)
def test_direct_sql_asset_guards(db, asset, sql):
    with pytest.raises(IntegrityError):
        db.execute(text(sql), {"replacement": str(uuid.uuid4())})
        db.commit()


def test_orm_code_immutable_and_archived_code_reserved(db, asset, asset_model):
    asset.asset_code = "AP-999"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    asset.lifecycle_status = LifecycleStatus.ARCHIVED
    db.commit()
    assert asset.asset_code == "AP-001"
    db.add(AssetUnit(asset_code="ap-001", device_model_id=asset_model.id))
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize("code", ["ap-002", "AP 002", "AP/002", "-AP", "A" * 51])
def test_raw_insert_code_validation(db, asset_model, code):
    # PostgreSQL rejects varchar overflow before the CHECK/trigger is reached.
    expected = (
        DataError if len(code) > 50 and db.bind.dialect.name == "postgresql" else IntegrityError
    )
    with pytest.raises(expected):
        db.execute(
            AssetUnit.__table__.insert().values(
                id=uuid.uuid4(), asset_code=code, device_model_id=asset_model.id
            )
        )


@pytest.mark.parametrize(
    "raw",
    [
        "aabbccddeeff",
        "aa:bb:cc:dd:ee:ff",
        "aa-bb-cc-dd-ee-ff",
        "aabb.ccdd.eeff",
        " AA:BB:CC:DD:EE:FF ",
    ],
)
def test_mac_normalization(db, asset, raw):
    identifier = claim(asset, raw_value=raw, normalized_value="forged")
    db.add(identifier)
    db.commit()
    db.expire_all()
    assert identifier.normalized_value == "AA:BB:CC:DD:EE:FF"
    assert identifier.raw_value == raw and identifier.version == 1
    assert identifier.verification_status.value == "UNVERIFIED" and identifier.created_at


@pytest.mark.parametrize("raw", ["", " ", "UNKNOWN", "n/a", "NA", "-", "123\n456", "x" * 256])
def test_invalid_serial_claim(raw):
    with pytest.raises(ValueError):
        normalize_identifier(IdentifierType.SERIAL_NUMBER, raw)


@pytest.mark.parametrize(
    "raw", ["", "GG:BB:CC:DD:EE:FF", "aa:bb-cc:dd:ee:ff", "123", "aabb.ccdd.eeff00"]
)
def test_invalid_mac(raw):
    with pytest.raises(ValueError):
        normalize_identifier(IdentifierType.MAC_LAN, raw)


def test_claim_lookup_collision_scope_soft_delete(db, asset, asset_model):
    first = claim(asset)
    db.add(first)
    db.commit()
    db.add(claim(asset, raw_value="aabb.ccdd.eeff"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    other = AssetUnit(asset_code="AP-002", device_model_id=asset_model.id)
    db.add(other)
    db.flush()
    # Same MAC on another asset or another interface type is a collision, not a global unique key.
    db.add_all([claim(other), claim(asset, identifier_type=IdentifierType.BSSID)])
    db.commit()
    collisions = list(
        db.scalars(
            select(AssetIdentifier).where(
                AssetIdentifier.identifier_type == IdentifierType.MAC_LAN,
                AssetIdentifier.normalized_value == "AA:BB:CC:DD:EE:FF",
                AssetIdentifier.deleted_at.is_(None),
            )
        )
    )
    assert len(collisions) == 2 and {row.asset_id for row in collisions} == {asset.id, other.id}
    first.deleted_at = datetime.now(UTC)
    db.commit()
    db.add(claim(asset))
    db.commit()
    assert db.scalar(select(func.count()).select_from(AssetIdentifier)) == 4
    assert db.get(AssetIdentifier, first.id).deleted_at is not None


@pytest.mark.parametrize(
    "values",
    [
        {"normalized_value": "bad"},
        {"raw_value": "00:11:22:33:44:55"},
        {"normalized_value": "aa:bb:cc:dd:ee:ff"},
        {"source": "OTHER"},
        {"verification_status": "OTHER"},
        {"identifier_type": "OTHER"},
        {"normalized_value": None},
        {"raw_value": ""},
        {"version": 0},
        {"asset_id": uuid.UUID(int=0)},
    ],
)
def test_raw_claim_constraints(db, asset, values):
    fields = (
        dict(
            id=uuid.uuid4(),
            asset_id=asset.id,
            identifier_type="MAC_LAN",
            raw_value="aa-bb-cc-dd-ee-ff",
            normalized_value="AA:BB:CC:DD:EE:FF",
            source="MANUAL",
        )
        | values
    )
    with pytest.raises(IntegrityError):
        db.execute(AssetIdentifier.__table__.insert().values(**fields))


def test_identifier_normalization_type_changes_and_retention(db, asset):
    identifier = claim(asset, identifier_type=IdentifierType.HOSTNAME, raw_value=" Host.Example ")
    db.add(identifier)
    db.commit()
    assert identifier.normalized_value == "host.example"
    identifier.identifier_type = IdentifierType.SERIAL_NUMBER
    identifier.raw_value = " SN-AbC "
    db.commit()
    assert identifier.normalized_value == "SN-AbC" and identifier.version == 2
    for statement in (
        text("DELETE FROM asset_identifiers"),
        update(AssetIdentifier).values(asset_id=uuid.uuid4()),
    ):
        with pytest.raises(IntegrityError):
            db.execute(statement)
        db.rollback()


@pytest.mark.parametrize("entity", ["asset", "identifier"])
def test_optimistic_concurrency(factory, db, asset, entity):
    record = asset if entity == "asset" else claim(asset)
    db.add(record)
    db.commit()
    with factory() as other:
        stale = other.get(type(record), record.id)
        record.notes = "approved change"
        db.commit()
        stale.notes = "stale overwrite"
        with pytest.raises(StaleDataError):
            other.commit()
    assert record.version == 2
    db.expire_all()
    assert record.notes == "approved change"


def test_audit_snapshots_atomicity_and_retention(db, asset, user):
    before = {"notes": None, "version": 1}
    asset.notes = "Approved synthetic note"
    event = AssetChangeEvent(
        asset_id=asset.id,
        actor_id=user.id,
        event_type=AssetEventType.UPDATE,
        before_json=before,
        after_json={"notes": asset.notes, "version": 2},
    )
    db.add(event)
    db.commit()
    db.expire_all()
    assert event.before_json == before and event.after_json["notes"] == asset.notes
    assert event.asset_id == asset.id and event.actor_id == user.id and event.recorded_at
    asset.notes = "Must rollback"
    db.add(
        AssetChangeEvent(
            asset_id=asset.id,
            actor_id=uuid.uuid4(),
            event_type=AssetEventType.UPDATE,
            before_json=event.after_json,
            after_json={"notes": asset.notes},
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert asset.notes == "Approved synthetic note"
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 1
    for statement in (
        text("DELETE FROM asset_change_events"),
        text("UPDATE asset_change_events SET event_type='ARCHIVE'"),
    ):
        with pytest.raises(IntegrityError):
            db.execute(statement)
        db.rollback()


def test_postgres_asset_jsonb_and_indexes(factory):
    engine = factory.kw["bind"]
    inspector = inspect(engine)
    assert {"ix_asset_identifiers_lookup", "uq_asset_identifiers_active"} <= {
        row["name"] for row in inspector.get_indexes("asset_identifiers")
    }
    assert not {"current_location", "current_location_id"} & {
        row["name"] for row in inspector.get_columns("assets")
    }
    if engine.dialect.name == "postgresql":
        columns = {row["name"]: row for row in inspector.get_columns("asset_change_events")}
        assert str(columns["before_json"]["type"]) == "JSONB"
        assert str(columns["after_json"]["type"]) == "JSONB"


@pytest.mark.parametrize("event_type", list(AssetEventType))
def test_each_audit_event_type(db, asset, user, event_type):
    event = AssetChangeEvent(
        asset_id=asset.id,
        actor_id=user.id,
        event_type=event_type,
        before_json=None,
        after_json={"asset_code": asset.asset_code},
    )
    db.add(event)
    db.commit()
    db.expire_all()
    assert event.before_json is None and event.after_json == {"asset_code": "AP-001"}
    assert event.event_type == event_type and event.recorded_at


@pytest.mark.parametrize(
    "fields",
    [
        {"event_type": "INVALID"},
        {"asset_id": uuid.UUID(int=0)},
        {"actor_id": None},
        {"after_json": None},
    ],
)
def test_invalid_audit_rejected(db, asset, user, fields):
    values = (
        dict(
            asset_id=asset.id,
            actor_id=user.id,
            event_type=AssetEventType.CREATE,
            after_json={"asset_code": "AP-001"},
        )
        | fields
    )
    db.add(AssetChangeEvent(**values))
    with pytest.raises(IntegrityError):
        db.commit()


def test_asset_migration_preserves_all_existing_rows(factory, db, asset_model, user):
    # All old tables contain synthetic rows, including JSON, FK, session and storage metadata.
    db.add_all(
        [
            AuthSession(user_id=user.id, csrf_hash="a" * 64, expires_at=datetime.now(UTC)),
            AuditEvent(actor_id=user.id, action="synthetic", details={"test": "preservation"}),
            DeviceReferenceImage(
                device_model_id=asset_model.id,
                uploaded_by=user.id,
                storage_key="synthetic.png",
                sha256="a" * 64,
                mime_type="image/png",
                byte_size=100,
            ),
            StorageCleanupJob(storage_key="synthetic-cleanup.png"),
        ]
    )
    db.commit()
    old_tables = [
        Base.metadata.tables[name]
        for name in (
            "users",
            "auth_sessions",
            "audit_events",
            "device_categories",
            "manufacturers",
            "device_models",
            "device_reference_images",
            "storage_cleanup_jobs",
        )
    ]
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.downgrade(config, "0003_image_cleanup")
        before = {
            table.name: list(connection.execute(select(table).order_by(table.c.id)))
            for table in old_tables
        }
        connection.commit()
        command.upgrade(config, "head")
        command.check(config)
        for table in old_tables:
            assert before[table.name] == list(
                connection.execute(select(table).order_by(table.c.id))
            )
        assert connection.scalar(select(func.count()).select_from(AssetUnit)) == 0
        connection.commit()
        command.downgrade(config, "0003_image_cleanup")
        assert "assets" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        command.check(config)
        for table in old_tables:
            assert before[table.name] == list(
                connection.execute(select(table).order_by(table.c.id))
            )
