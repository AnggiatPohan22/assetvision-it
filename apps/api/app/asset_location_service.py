"""Initial placement is an explicit ADMIN decision, atomic with its evidence."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.asset_locations import AssetLocationEvent
from app.asset_service import check_version, get_asset, transaction
from app.assets import AssetUnit, LifecycleStatus
from app.location_schemas import LocationOutput
from app.location_service import lock_hierarchy
from app.locations import Location
from app.models import User


def initial_placement(
    db: Session, asset_id: uuid.UUID, version: int, location_id: uuid.UUID, reason: str, user: User
) -> AssetUnit:
    with transaction(db):
        # Same lock order as hierarchy writers; archive cannot race eligibility validation.
        lock_hierarchy(db)
        asset = get_asset(db, asset_id, lock=True)
        check_version(asset, version)
        if asset.current_location_id is not None or db.scalar(
            select(AssetLocationEvent.id).where(AssetLocationEvent.asset_id == asset.id).limit(1)
        ):
            raise HTTPException(409, "Asset was already placed; use the movement workflow")
        if asset.lifecycle_status == LifecycleStatus.ARCHIVED:
            raise HTTPException(409, "Archived assets cannot be placed")
        location = db.get(Location, location_id, populate_existing=True)
        if location is None:
            raise HTTPException(422, "Unknown location_id")
        if not location.is_active:
            raise HTTPException(409, "Location is archived")
        now = datetime.now(UTC)
        previous_version = asset.version
        asset.current_location_id = location.id
        asset.location_verified_at = now
        asset.version += 1
        db.add(
            AssetLocationEvent(
                asset_id=asset.id,
                actor_id=user.id,
                event_type="INITIAL_PLACEMENT",
                occurred_at=now,
                correlation_id=uuid.uuid4(),
                payload_json={
                    "from_location_id": None,
                    "to_location_id": str(location.id),
                    "location": LocationOutput.model_validate(location).model_dump(mode="json"),
                    "reason": reason,
                    "expected_asset_version": previous_version,
                    "asset_version": asset.version,
                    "effective_at": now.isoformat(),
                    "decision": "ADMIN_INITIAL_PLACEMENT",
                },
            )
        )
        db.flush()
    return asset
