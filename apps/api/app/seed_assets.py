"""Explicit, atomic Sprint 1B demo batch. Never overwrite or repair existing records."""

import argparse
import json
import uuid

from sqlalchemy import or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.asset_service import audit, snapshot
from app.assets import AssetChangeEvent, AssetEventType, AssetIdentifier, AssetUnit, IdentifierType
from app.catalog import DeviceCategory, DeviceModel, Environment, Manufacturer
from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditEvent, Role, User

NAMESPACE = uuid.UUID("9d1306ea-311e-492a-a471-7fe82c3d3c50")
MARKER = "SYNTHETIC Sprint 1B demo; NOT production data"
SERIALS = (
    "123456789",
    "2158763",
    "SYNTH-1B-003",
    None,
    None,
    "SYNTH-1B-006",
    "SYNTH-1B-007",
    "SYNTH-1B-008",
)
CODES = tuple(f"AP-{number:03}" for number in range(1, 9))


class SeedConflict(ValueError):
    pass


def seed_id(code: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, code)


def demo_claims(number: int) -> list[tuple[IdentifierType, str]]:
    claims = [
        (IdentifierType.MAC_LAN, f"02:00:00:1B:00:{number:02X}"),
        (IdentifierType.HOSTNAME, f"synthetic-ap-{number:03}.invalid"),
    ]
    if SERIALS[number - 1] is not None:
        claims.append((IdentifierType.SERIAL_NUMBER, SERIALS[number - 1]))
    return claims


def add_catalog(
    db: Session, record: DeviceCategory | Manufacturer | DeviceModel, actor: User
) -> None:
    record.created_by = actor.id
    record.updated_by = actor.id
    db.add(record)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="catalog_create",
            details={
                "table": record.__tablename__,
                "id": str(record.id),
                "version": str(record.version),
                "seed": MARKER,
            },
        )
    )


def seed_assets(db: Session, actor_id: uuid.UUID) -> dict[str, int]:
    """Caller owns the transaction; refusal/SQL/audit errors must roll it all back."""
    if get_settings().app_env == "production":
        raise SeedConflict("Synthetic asset seed is disabled in production")
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(649237803)"))
    actor = db.scalar(select(User).where(User.id == actor_id).with_for_update(read=True))
    if actor is None or not actor.is_active or actor.role != Role.ADMIN:
        raise SeedConflict("An existing active ADMIN actor is required")

    # Refuse occupied example codes unless every row proves it is this complete demo batch.
    units = list(db.scalars(select(AssetUnit).where(AssetUnit.asset_code.in_(CODES))))
    for unit in units:
        birth = db.scalar(
            select(AssetChangeEvent).where(
                AssetChangeEvent.asset_id == unit.id,
                AssetChangeEvent.event_type == AssetEventType.CREATE,
            )
        )
        if (
            unit.id != seed_id(unit.asset_code)
            or birth is None
            or birth.after_json.get("asset", {}).get("notes") != MARKER
        ):
            raise SeedConflict("Example asset codes are occupied; no existing data may be adopted")
    if units and len(units) != 8:
        raise SeedConflict("Incomplete demo batch; refusing automatic repair")

    category = db.scalar(
        select(DeviceCategory)
        .where(DeviceCategory.code == "access-point")
        .with_for_update(read=True)
    )
    maker = db.scalar(
        select(Manufacturer)
        .where(Manufacturer.normalized_name == "ruijie")
        .with_for_update(read=True)
    )
    if (category is not None and not category.is_active) or (
        maker is not None and not maker.is_active
    ):
        raise SeedConflict("Required catalog references are archived; refusing reactivation")
    created_catalog = 0
    if category is None:
        category = DeviceCategory(code="access-point", name="Access Point", description=MARKER)
        add_catalog(db, category, actor)
        created_catalog += 1
    if maker is None:
        maker = Manufacturer(name="Ruijie")
        add_catalog(db, maker, actor)
        created_catalog += 1
    model = db.scalar(
        select(DeviceModel)
        .where(
            DeviceModel.manufacturer_id == maker.id,
            DeviceModel.normalized_model_name == "ap680-l",
        )
        .with_for_update()
    )
    if model is None:
        model = DeviceModel(
            manufacturer_id=maker.id,
            category_id=category.id,
            model_name="AP680-L",
            description=MARKER,
            environment=Environment.OUTDOOR,
            aliases=[],
            specs={},
        )
        add_catalog(db, model, actor)
        created_catalog += 1
    if not model.is_active or model.category_id != category.id:
        raise SeedConflict(
            "Existing model is archived or has a different category; no changes made"
        )
    model_units = set(db.scalars(select(AssetUnit.id).where(AssetUnit.device_model_id == model.id)))
    if units:
        if model_units != {seed_id(code) for code in CODES}:
            raise SeedConflict("Demo model membership changed; refusing automatic repair")
        # Preserve all subsequent user edits, even archived units or removed/changed claims.
        return {
            "created_assets": 0,
            "created_identifiers": 0,
            "created_catalog": 0,
            "existing_assets": 8,
        }
    if model_units:
        raise SeedConflict("Model already has physical units; refusing to add demo data")
    for number in range(1, 9):
        for kind, value in demo_claims(number):
            if (
                db.scalar(
                    select(AssetIdentifier.id).where(
                        AssetIdentifier.identifier_type == kind,
                        AssetIdentifier.normalized_value == value,
                        AssetIdentifier.deleted_at.is_(None),
                    )
                )
                is not None
            ):
                raise SeedConflict(
                    "Demo identifier collides with existing evidence; no changes made"
                )
    # Also refuse deterministic UUID collisions even if a code was manipulated outside the API.
    if (
        db.scalar(
            select(AssetUnit.id).where(
                or_(
                    AssetUnit.id.in_([seed_id(code) for code in CODES]),
                    AssetUnit.asset_code.in_(CODES),
                )
            )
        )
        is not None
    ):
        raise SeedConflict("Demo identity conflict; no existing data may be overwritten")

    count = 0
    for number, code in enumerate(CODES, 1):
        unit = AssetUnit(id=seed_id(code), asset_code=code, device_model_id=model.id, notes=MARKER)
        db.add(unit)
        audit(db, unit, actor, AssetEventType.CREATE, None)
        for kind, value in demo_claims(number):
            before = snapshot(unit)
            claim = AssetIdentifier(
                asset_id=unit.id,
                identifier_type=kind,
                raw_value=value,
                source="IMPORT",
                verification_status="UNVERIFIED",
                notes=MARKER,
            )
            db.add(claim)
            unit.version += 1
            audit(db, unit, actor, AssetEventType.IDENTIFIER_ADD, before, claim)
            count += 1
    db.flush()
    return {
        "created_assets": 8,
        "created_identifiers": count,
        "created_catalog": created_catalog,
        "existing_assets": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Add eight synthetic AP units atomically")
    parser.add_argument("--actor-id", required=True, type=uuid.UUID)
    parser.add_argument("--confirm-synthetic", required=True, action="store_true")
    args = parser.parse_args()
    try:
        with SessionLocal.begin() as db:
            result = seed_assets(db, args.actor_id)
    except SeedConflict as error:
        raise SystemExit(str(error)) from None
    except SQLAlchemyError:
        raise SystemExit(
            "Seed transaction rolled back: database/audit conflict; no partial seed"
        ) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
