"""Asset writes and snapshots commit together; parent version covers all metadata."""

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.asset_schemas import AssetOutput, IdentifierOutput
from app.assets import (
    AssetChangeEvent,
    AssetEventType,
    AssetIdentifier,
    AssetUnit,
    LifecycleStatus,
    normalize_identifier,
)
from app.catalog import DeviceModel
from app.models import User


@contextmanager
def transaction(db: Session) -> Generator[None]:
    try:
        yield
        db.commit()
    except StaleDataError:
        db.rollback()
        raise HTTPException(409, "Asset metadata changed; reload and retry") from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Asset conflict; duplicate code/claim or invalid reference"
        ) from None
    except ValueError:
        db.rollback()
        raise HTTPException(422, "Invalid identifier value for its type") from None
    except Exception:
        db.rollback()
        raise


def get_asset(db: Session, asset_id: uuid.UUID, *, lock: bool = False) -> AssetUnit:
    statement = select(AssetUnit).where(AssetUnit.id == asset_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    asset = db.scalar(statement)
    if asset is None:
        raise HTTPException(404, "Asset not found")
    return asset


def check_version(record: AssetUnit | AssetIdentifier, version: int) -> None:
    if record.version != version:
        raise HTTPException(409, "Asset metadata changed; reload and retry")
    if version == 2_147_483_647:
        raise HTTPException(409, "Version limit reached")


def validate_model(db: Session, model_id: uuid.UUID) -> None:
    model = db.scalar(
        select(DeviceModel).where(DeviceModel.id == model_id).with_for_update(read=True)
    )
    if model is None:
        raise HTTPException(422, "Unknown device_model_id")
    if not model.is_active:
        raise HTTPException(409, "Inactive device_model_id")


def snapshot(asset: AssetUnit, claim: AssetIdentifier | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"asset": AssetOutput.model_validate(asset).model_dump(mode="json")}
    if claim is not None:
        result["identifier"] = IdentifierOutput.model_validate(claim).model_dump(
            mode="json", exclude={"collision_asset_ids"}
        )
    return result


def audit(
    db: Session,
    asset: AssetUnit,
    user: User,
    kind: AssetEventType,
    before: dict[str, Any] | None,
    claim: AssetIdentifier | None = None,
) -> None:
    db.flush()
    db.refresh(asset)
    if claim is not None:
        db.refresh(claim)
    db.add(
        AssetChangeEvent(
            asset_id=asset.id,
            actor_id=user.id,
            event_type=kind,
            before_json=before,
            after_json=snapshot(asset, claim),
        )
    )


def create_asset(db: Session, values: dict[str, Any], user: User) -> AssetUnit:
    with transaction(db):
        validate_model(db, values["device_model_id"])
        asset = AssetUnit(**values)
        db.add(asset)
        audit(db, asset, user, AssetEventType.CREATE, None)
    return asset


def update_asset(
    db: Session,
    asset_id: uuid.UUID,
    version: int,
    values: dict[str, Any],
    user: User,
    *,
    archive: bool = False,
) -> AssetUnit:
    with transaction(db):
        asset = get_asset(db, asset_id, lock=True)
        check_version(asset, version)
        if archive and asset.lifecycle_status == LifecycleStatus.ARCHIVED:
            return asset
        before = snapshot(asset)
        if "device_model_id" in values and values["device_model_id"] != asset.device_model_id:
            validate_model(db, values["device_model_id"])
        for key, value in values.items():
            setattr(asset, key, value)
        kind = (
            AssetEventType.ARCHIVE
            if before["asset"]["lifecycle_status"] != LifecycleStatus.ARCHIVED
            and asset.lifecycle_status == LifecycleStatus.ARCHIVED
            else AssetEventType.UPDATE
        )
        asset.version += 1
        audit(db, asset, user, kind, before)
    return asset


def mutate_identifier(
    db: Session,
    asset_id: uuid.UUID,
    asset_version: int,
    values: dict[str, Any],
    user: User,
    *,
    identifier_id: uuid.UUID | None = None,
    version: int | None = None,
    remove: bool = False,
) -> tuple[AssetUnit, AssetIdentifier]:
    with transaction(db):
        asset = get_asset(db, asset_id, lock=True)
        check_version(asset, asset_version)
        claim = None
        if identifier_id is not None:
            claim = db.scalar(
                select(AssetIdentifier)
                .where(
                    AssetIdentifier.id == identifier_id,
                    AssetIdentifier.asset_id == asset_id,
                )
                .execution_options(populate_existing=True)
            )
            if claim is None:
                raise HTTPException(404, "Identifier not found on this asset")
            check_version(claim, version)
            if claim.deleted_at is not None:
                if remove:
                    return asset, claim
                raise HTTPException(409, "Identifier was removed")
        before = snapshot(asset, claim)
        if claim is None:
            claim = AssetIdentifier(asset_id=asset_id, **values)
            db.add(claim)
            kind = AssetEventType.IDENTIFIER_ADD
        elif remove:
            claim.deleted_at = datetime.now(UTC)
            claim.version += 1
            kind = AssetEventType.IDENTIFIER_REMOVE
        else:
            for key, value in values.items():
                setattr(claim, key, value)
            claim.version += 1
            kind = AssetEventType.IDENTIFIER_UPDATE
        # Validate the merged type/raw pair before the ORM flush and safe-error mapping.
        normalize_identifier(claim.identifier_type, claim.raw_value)
        asset.version += 1
        audit(db, asset, user, kind, before, claim)
    return asset, claim


def identifier_output(db: Session, claim: AssetIdentifier) -> IdentifierOutput:
    result = IdentifierOutput.model_validate(claim)
    if claim.deleted_at is None:
        result.collision_asset_ids = list(
            db.scalars(
                select(AssetIdentifier.asset_id)
                .where(
                    AssetIdentifier.identifier_type == claim.identifier_type,
                    AssetIdentifier.normalized_value == claim.normalized_value,
                    AssetIdentifier.asset_id != claim.asset_id,
                    AssetIdentifier.deleted_at.is_(None),
                )
                .distinct()
                .order_by(AssetIdentifier.asset_id)
            )
        )
    return result
