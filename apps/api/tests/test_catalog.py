import uuid

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.catalog import DeviceCategory, DeviceModel, DeviceReferenceImage, Environment, Manufacturer
from app.models import User
from app.seed_catalog import seed_catalog


@pytest.fixture()
def model(db: Session) -> DeviceModel:
    category = DeviceCategory(code="access-point", name="Access Point")
    manufacturer = Manufacturer(name="Ruijie")
    db.add_all([category, manufacturer])
    db.flush()
    model = DeviceModel(
        manufacturer_id=manufacturer.id, category_id=category.id,
        model_name="AP680-L", environment=Environment.OUTDOOR,
        aliases=["AP 680-L"], specs={"bands": ["2.4GHz", "5GHz"]},
    )
    db.add(model)
    db.commit()
    return model


@pytest.mark.parametrize("name", ["ap680-l", " AP680-L ", "\tAp680-L\n"])
def test_model_duplicate_rejected(db: Session, model: DeviceModel, name: str) -> None:
    db.add(DeviceModel(
        manufacturer_id=model.manufacturer_id, category_id=model.category_id,
        model_name=name, environment=Environment.BOTH,
    ))
    with pytest.raises(IntegrityError):
        db.commit()


def test_internal_whitespace_normalized(db: Session, model: DeviceModel) -> None:
    model.model_name = "AP  680\tL"
    db.commit()
    db.add(DeviceModel(
        manufacturer_id=model.manufacturer_id, category_id=model.category_id,
        model_name="ap 680 l", environment=Environment.INDOOR,
    ))
    with pytest.raises(IntegrityError):
        db.commit()


def test_same_model_other_manufacturer_and_json_roundtrip(db: Session, model: DeviceModel) -> None:
    manufacturer = Manufacturer(name="Other Synthetic Maker")
    db.add(manufacturer)
    db.flush()
    other = DeviceModel(
        manufacturer_id=manufacturer.id, category_id=model.category_id,
        model_name=model.model_name, environment=Environment.BOTH,
    )
    db.add(other)
    db.commit()
    db.expire_all()
    assert model.normalized_model_name == "ap680-l"
    assert model.aliases == ["AP 680-L"]
    assert model.specs == {"bands": ["2.4GHz", "5GHz"]}
    assert other.specs == {} and other.aliases == []
    assert model.is_active and model.created_at and model.updated_at
    assert model.id != other.id


@pytest.mark.parametrize(
    "kind", ["category", "manufacturer", "blank", "environment", "foreign_key"]
)
def test_catalog_constraints(db: Session, model: DeviceModel, kind: str) -> None:
    if kind == "category":
        db.add(DeviceCategory(code=" ACCESS-POINT ", name="Duplicate"))
    elif kind == "manufacturer":
        db.add(Manufacturer(name=" RUIJIE "))
    elif kind == "blank":
        db.add(Manufacturer(name=" \t "))
    elif kind == "environment":
        db.execute(text("UPDATE device_models SET environment='invalid' WHERE 1=0"))
        model.environment = "invalid"
    else:
        model.category_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        db.commit()


def test_database_keys_cannot_be_forged(db: Session, model: DeviceModel) -> None:
    with pytest.raises((OperationalError, ProgrammingError)):
        db.execute(text("UPDATE device_models SET normalized_model_name='forged'"))
    db.rollback()
    # Raw writers cannot evade normalization using repeated spaces.
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE device_models SET model_name='AP  680-L'"))


def test_archive_preserves_references_and_name_reservation(db: Session, model: DeviceModel) -> None:
    model.is_active = False
    db.commit()
    assert db.get(Manufacturer, model.manufacturer_id)
    assert db.get(DeviceCategory, model.category_id)
    assert db.get(DeviceModel, model.id) is model
    db.add(DeviceModel(
        manufacturer_id=model.manufacturer_id, category_id=model.category_id,
        model_name=model.model_name, environment=Environment.BOTH,
    ))
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize("table", ["manufacturers", "device_categories"])
def test_referenced_catalog_cannot_be_deleted(db: Session, model: DeviceModel, table: str) -> None:
    with pytest.raises(IntegrityError):
        db.execute(text(f"DELETE FROM {table}"))


def test_stale_catalog_update_rejected(factory, db: Session, model: DeviceModel) -> None:
    with factory() as other:
        stale = other.get(DeviceModel, model.id)
        model.description = "Approved change"
        db.commit()
        stale.description = "Stale overwrite"
        with pytest.raises(StaleDataError):
            other.commit()
    assert model.version == 2


def image(model: DeviceModel, user: User, **overrides) -> DeviceReferenceImage:
    fields = dict(
        device_model_id=model.id, uploaded_by=user.id, storage_key=f"reference/{uuid.uuid4()}.png",
        sha256="a" * 64, mime_type="image/png", byte_size=200, is_primary=False,
    )
    fields.update(overrides)
    return DeviceReferenceImage(**fields)


def test_reference_metadata_and_single_primary(db: Session, model: DeviceModel, user: User) -> None:
    db.add_all([image(model, user, is_primary=True), *[image(model, user) for _ in range(4)]])
    db.commit()
    assert db.scalar(select(func.count()).select_from(DeviceReferenceImage)) == 5
    db.add(image(model, user, is_primary=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.delete(model)
        db.commit()


@pytest.mark.parametrize("fields", [
    {"storage_key": "/host/private.png"}, {"storage_key": "../private.png"},
    {"storage_key": "C:\\private.png"}, {"storage_key": "a\\private.png"},
    {"byte_size": 0}, {"mime_type": "image/svg+xml"}, {"sha256": "bad"},
    {"uploaded_by": uuid.UUID(int=0)}, {"device_model_id": uuid.UUID(int=0)},
])
def test_invalid_image_metadata_rejected(
    db: Session, model: DeviceModel, user: User, fields: dict,
) -> None:
    db.add(image(model, user, **fields))
    with pytest.raises(IntegrityError):
        db.commit()


def test_seed_idempotent_and_preserves_edits(db: Session) -> None:
    seed_catalog(db)
    db.commit()
    categories = list(db.scalars(select(DeviceCategory)))
    manufacturers = list(db.scalars(select(Manufacturer)))
    ids = {row.id for row in categories + manufacturers}
    categories[0].name = "Edited category"
    categories[0].is_active = False
    manufacturers[0].website = "https://example.invalid"
    db.commit()
    seed_catalog(db)
    db.commit()
    assert len(list(db.scalars(select(DeviceCategory)))) == 5
    assert len(list(db.scalars(select(Manufacturer)))) == 3
    assert ids == {row.id for row in db.scalars(select(DeviceCategory))} | {
        row.id for row in db.scalars(select(Manufacturer))
    }
    assert categories[0].name == "Edited category" and not categories[0].is_active
    assert manufacturers[0].website == "https://example.invalid"
    assert db.scalar(select(func.count()).select_from(DeviceModel)) == 0


def test_postgres_uses_jsonb(factory) -> None:
    engine = factory.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-specific JSONB inspection")
    columns = {column["name"]: column for column in inspect(engine).get_columns("device_models")}
    assert str(columns["aliases"]["type"]) == "JSONB"
    assert str(columns["specs"]["type"]) == "JSONB"
