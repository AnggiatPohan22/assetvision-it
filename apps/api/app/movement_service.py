"""Atomic movement decisions and immutable evidence."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.asset_locations import AssetLocationEvent
from app.asset_service import check_version, get_asset, transaction
from app.assets import AssetUnit, LifecycleStatus
from app.location_schemas import LocationOutput
from app.location_service import lock_hierarchy
from app.locations import Location
from app.models import Role, User
from app.movement_schemas import MovementOutput
from app.movements import AssetMovement, MovementStatus


def require_writer(user: User) -> None:
    if not user.is_active or user.role not in {Role.ADMIN, Role.OFFICER}:
        raise HTTPException(403, "Movement requires an active ADMIN or OFFICER")


def active_destination(db: Session, location_id: uuid.UUID) -> Location:
    location = db.get(Location, location_id, populate_existing=True)
    if location is None:
        raise HTTPException(422, "Unknown to_location_id")
    if not location.is_active:
        raise HTTPException(409, "Destination location is archived")
    return location


def get_movement(db: Session, movement_id: uuid.UUID, *, lock: bool = False) -> AssetMovement:
    statement = select(AssetMovement).where(AssetMovement.id == movement_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    movement = db.scalar(statement)
    if movement is None:
        raise HTTPException(404, "Movement not found")
    return movement


def write_event(
    db: Session,
    movement: AssetMovement,
    user: User,
    asset: AssetUnit,
    now: datetime,
    destination: Location | None = None,
) -> None:
    payload: dict[str, Any] = MovementOutput.model_validate(movement).model_dump(mode="json")
    payload["movement_id"] = str(movement.id)
    payload["asset_version"] = asset.version
    payload["self_approval"] = (
        movement.status == MovementStatus.APPROVED and movement.requested_by == user.id
    )
    payload["self_approval_policy"] = "ALLOWED_PILOT"
    if destination is not None:
        payload["approved_destination"] = LocationOutput.model_validate(destination).model_dump(
            mode="json"
        )
    db.add(
        AssetLocationEvent(
            asset_id=movement.asset_id,
            actor_id=user.id,
            event_type="MOVEMENT_"
            + ("REQUESTED" if movement.status == MovementStatus.PENDING else movement.status.value),
            occurred_at=now,
            recorded_at=now,
            correlation_id=uuid.uuid4(),
            payload_json=payload,
        )
    )


def request_movement(
    db: Session,
    asset_id: uuid.UUID,
    asset_version: int,
    to_location_id: uuid.UUID,
    reason: str,
    user: User,
) -> AssetMovement:
    with transaction(db):
        require_writer(user)
        lock_hierarchy(db)
        asset = get_asset(db, asset_id, lock=True)
        check_version(asset, asset_version)
        if asset.lifecycle_status == LifecycleStatus.ARCHIVED:
            raise HTTPException(409, "Archived assets cannot move")
        if asset.current_location_id is None:
            raise HTTPException(409, "Asset needs explicit initial placement first")
        if asset.current_location_id == to_location_id:
            raise HTTPException(409, "Destination is already the official location")
        destination = active_destination(db, to_location_id)
        origin = db.get(Location, asset.current_location_id, populate_existing=True)
        now = datetime.now(UTC)
        movement = AssetMovement(
            id=uuid.uuid4(),
            asset_id=asset.id,
            from_location_id=asset.current_location_id,
            to_location_id=destination.id,
            expected_asset_version=asset.version,
            requested_by=user.id,
            requested_at=now,
            reason=reason,
            status=MovementStatus.PENDING,
            version=1,
            request_snapshot_json={
                "from": LocationOutput.model_validate(origin).model_dump(mode="json"),
                "to": LocationOutput.model_validate(destination).model_dump(mode="json"),
            },
        )
        db.add(movement)
        db.flush()
        write_event(db, movement, user, asset, now)
    return movement


def decide_movement(
    db: Session,
    movement_id: uuid.UUID,
    version: int,
    decision: MovementStatus,
    reason: str,
    user: User,
) -> AssetMovement:
    with transaction(db):
        require_writer(user)
        if decision not in {
            MovementStatus.APPROVED,
            MovementStatus.REJECTED,
            MovementStatus.CANCELLED,
        }:
            raise HTTPException(422, "Invalid movement decision")
        if decision != MovementStatus.CANCELLED and user.role != Role.ADMIN:
            raise HTTPException(403, "Only ADMIN can approve or reject movements")
        # Shared order: hierarchy -> movement -> asset. No writer acquires these in reverse.
        lock_hierarchy(db)
        movement = get_movement(db, movement_id, lock=True)
        if (
            decision == MovementStatus.CANCELLED
            and user.role != Role.ADMIN
            and movement.requested_by != user.id
        ):
            raise HTTPException(403, "Only the requester or ADMIN can cancel")
        if movement.status != MovementStatus.PENDING or movement.version != version:
            raise HTTPException(409, "Movement changed or already decided; reload and review")
        asset = get_asset(db, movement.asset_id, lock=True)
        destination = None
        now = datetime.now(UTC)
        if decision == MovementStatus.APPROVED:
            check_version(asset, movement.expected_asset_version)
            if asset.current_location_id != movement.from_location_id:
                raise HTTPException(
                    409, "Movement origin is stale; reject or cancel and create a new request"
                )
            if asset.lifecycle_status == LifecycleStatus.ARCHIVED:
                raise HTTPException(409, "Archived assets cannot move")
            destination = active_destination(db, movement.to_location_id)
            asset.current_location_id = destination.id
            asset.location_verified_at = now
            asset.version += 1
            movement.approved_at = now
            movement.effective_at = now
        movement.status = decision
        movement.reviewed_by = user.id
        movement.reviewed_at = now
        movement.review_reason = reason
        movement.version += 1
        db.flush()
        write_event(db, movement, user, asset, now, destination)
    return movement
