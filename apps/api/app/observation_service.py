"""Atomic evidence/review history without mutating authoritative assets."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.asset_locations import AssetLocationEvent
from app.asset_service import get_asset, transaction
from app.assets import AssetUnit
from app.location_schemas import LocationOutput
from app.location_service import lock_hierarchy
from app.locations import Location
from app.models import AuditEvent, Role, User
from app.observation_schemas import (
    AssetLocationStatus,
    ObservationCreate,
    ObservationOutput,
    ObservationReview,
)
from app.observations import LocationObservation, ObservationComparison, ObservationReviewStatus


def asset_context(asset: AssetUnit | None) -> dict[str, Any] | None:
    if asset is None:
        return None
    return {
        "asset_id": str(asset.id),
        "asset_version": asset.version,
        "current_location_id": str(asset.current_location_id)
        if asset.current_location_id
        else None,
        "location_verified_at": asset.location_verified_at.isoformat()
        if asset.location_verified_at
        else None,
    }


def write_observation_event(
    db: Session,
    observation: LocationObservation,
    user: User,
    asset: AssetUnit | None,
    *,
    reviewed: bool = False,
) -> None:
    payload = ObservationOutput.model_validate(observation).model_dump(mode="json")
    payload["asset_at_recording"] = asset_context(asset)
    now = observation.reviewed_at if reviewed else observation.recorded_at
    if observation.asset_id is None:
        db.add(
            AuditEvent(
                actor_id=user.id,
                action="location_observation_review" if reviewed else "location_observation_create",
                details={
                    "observation_id": str(observation.id),
                    "snapshot": json.dumps(payload, sort_keys=True),
                },
            )
        )
    else:
        db.add(
            AssetLocationEvent(
                asset_id=observation.asset_id,
                actor_id=user.id,
                event_type="LOCATION_OBSERVATION_REVIEWED" if reviewed else "LOCATION_OBSERVED",
                occurred_at=now if reviewed else observation.observed_at,
                recorded_at=now,
                correlation_id=uuid.uuid4(),
                payload_json=payload,
            )
        )


def create_observation(db: Session, data: ObservationCreate, user: User) -> LocationObservation:
    with transaction(db):
        if not user.is_active or user.role not in {Role.ADMIN, Role.OFFICER}:
            raise HTTPException(403, "Observation requires an active OFFICER or ADMIN")
        lock_hierarchy(db)
        asset = get_asset(db, data.asset_id, lock=True) if data.asset_id else None
        if asset is not None and asset.version != data.asset_version:
            raise HTTPException(409, "Asset changed; reload before recording the observation")
        location = db.get(Location, data.observed_location_id, populate_existing=True)
        if location is None:
            raise HTTPException(422, "Unknown observed_location_id")
        if not location.is_active:
            raise HTTPException(409, "Observed location is archived")
        now = datetime.now(UTC)
        observed_at = (data.observed_at or now).astimezone(UTC)
        if observed_at > now:
            raise HTTPException(422, "observed_at cannot be in the future")
        official_id = asset.current_location_id if asset else None
        comparison = ObservationComparison.UNLINKED
        if asset is not None:
            comparison = (
                ObservationComparison.UNPLACED
                if official_id is None
                else ObservationComparison.MATCH
                if official_id == location.id
                else ObservationComparison.LOCATION_CONFLICT
            )
        official = db.get(Location, official_id, populate_existing=True) if official_id else None
        record = LocationObservation(
            id=uuid.uuid4(),
            asset_id=asset.id if asset else None,
            observed_location_id=location.id,
            observed_by=user.id,
            observed_at=observed_at,
            recorded_at=now,
            evidence_note=data.evidence_note,
            comparison_status=comparison,
            official_location_id_at_recording=official_id,
            asset_version_at_recording=asset.version if asset else None,
            snapshot_json={
                "observed_location": LocationOutput.model_validate(location).model_dump(
                    mode="json"
                ),
                "official_location": LocationOutput.model_validate(official).model_dump(mode="json")
                if official
                else None,
                "asset": asset_context(asset),
            },
            review_status=ObservationReviewStatus.PENDING,
            version=1,
        )
        db.add(record)
        db.flush()
        write_observation_event(db, record, user, asset)
    return record


def get_observation(
    db: Session, observation_id: uuid.UUID, *, lock: bool = False
) -> LocationObservation:
    statement = select(LocationObservation).where(LocationObservation.id == observation_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    observation = db.scalar(statement)
    if observation is None:
        raise HTTPException(404, "Observation not found")
    return observation


def review_observation(
    db: Session, observation_id: uuid.UUID, data: ObservationReview, user: User
) -> LocationObservation:
    with transaction(db):
        if not user.is_active or user.role != Role.ADMIN:
            raise HTTPException(403, "Only ADMIN can review observations")
        lock_hierarchy(db)
        record = get_observation(db, observation_id, lock=True)
        if (
            record.version != data.version
            or record.review_status != ObservationReviewStatus.PENDING
        ):
            raise HTTPException(409, "Observation already reviewed or changed; reload")
        asset = get_asset(db, record.asset_id, lock=True) if record.asset_id else None
        record.review_status = data.review_status
        record.reviewed_by = user.id
        record.reviewed_at = datetime.now(UTC)
        record.review_reason = data.reason
        record.version += 1
        db.flush()
        write_observation_event(db, record, user, asset, reviewed=True)
    return record


def utc_stamp(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def location_status(db: Session, asset_id: uuid.UUID) -> AssetLocationStatus:
    # One statement gives a consistent asset/latest-evidence snapshot, without read side effects.
    latest = (
        select(LocationObservation.id)
        .where(
            LocationObservation.asset_id == AssetUnit.id,
            LocationObservation.review_status != ObservationReviewStatus.DISMISSED,
        )
        .order_by(
            LocationObservation.observed_at.desc(),
            LocationObservation.recorded_at.desc(),
            LocationObservation.id.desc(),
        )
        .correlate(AssetUnit)
        .limit(1)
        .scalar_subquery()
    )
    row = db.execute(
        select(AssetUnit, LocationObservation)
        .outerjoin(
            LocationObservation,
            LocationObservation.id == latest,
        )
        .where(AssetUnit.id == asset_id)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Asset not found")
    asset, observation = row
    if asset.current_location_id is None:
        status = "UNPLACED"
    elif observation is None:
        status = "NO_OBSERVATION"
    elif asset.location_verified_at is not None and utc_stamp(observation.observed_at) < utc_stamp(
        asset.location_verified_at
    ):
        status = "STALE_OBSERVATION"
    elif observation.observed_location_id != asset.current_location_id:
        status = "LOCATION_CONFLICT"
    else:
        status = "MATCH"
    return AssetLocationStatus(
        asset_id=asset.id,
        asset_version=asset.version,
        current_location_id=asset.current_location_id,
        location_verified_at=asset.location_verified_at,
        status=status,
        location_conflict=status == "LOCATION_CONFLICT",
        latest_observation=ObservationOutput.model_validate(observation) if observation else None,
    )
