"""Bounded master snapshot under hierarchy/asset locks; no model/location identity inference."""

import hashlib
import json
from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.asset_locations import AssetLocationEvent
from app.assets import AssetIdentifier, AssetUnit, LifecycleStatus
from app.catalog import DeviceModel
from app.fusion_schemas import Claim, LocationEvidence, UnitSnapshot
from app.location_service import lock_hierarchy
from app.observation_service import utc_stamp
from app.observations import LocationObservation, ObservationReviewStatus
from app.recognition_index import catalog_snapshot, head


def snapshot(db: Session) -> tuple[tuple[UnitSnapshot, ...], str, dict[str, str]]:
    lock_hierarchy(db)
    assets = list(
        db.scalars(
            select(AssetUnit)
            .order_by(AssetUnit.id)
            .limit(501)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(assets) > 500:
        raise HTTPException(409, "Complete registry snapshot exceeds 500 units")
    models = {
        m.id: m
        for m in db.scalars(
            select(DeviceModel).where(DeviceModel.id.in_({a.device_model_id for a in assets}))
        )
    }
    claims: dict[UUID, list[Claim]] = defaultdict(list)
    rows = list(
        db.scalars(
            select(AssetIdentifier)
            .where(
                AssetIdentifier.deleted_at.is_(None),
                AssetIdentifier.identifier_type.in_(
                    ("SERIAL_NUMBER", "MAC_LAN", "MAC_WLAN", "BSSID")
                ),
            )
            .order_by(AssetIdentifier.id)
            .limit(64001)
        )
    )
    if len(rows) > 64000:
        raise HTTPException(409, "Complete identifier snapshot exceeds capacity")
    for claim in rows:
        claims[claim.asset_id].append(
            Claim(
                kind=claim.identifier_type,
                value=claim.normalized_value,
                verification=claim.verification_status,
                source=claim.source,
            )
        )
    latest_id = (
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
    latest = {
        asset_id: obs
        for asset_id, obs in db.execute(
            select(AssetUnit.id, LocationObservation)
            .outerjoin(LocationObservation, LocationObservation.id == latest_id)
            .where(AssetUnit.id.in_([a.id for a in assets]))
        )
    }
    event_id = (
        select(AssetLocationEvent.id)
        .where(
            AssetLocationEvent.asset_id == AssetUnit.id,
            AssetLocationEvent.event_type.in_(("INITIAL_PLACEMENT", "MOVEMENT_APPROVED")),
        )
        .order_by(
            AssetLocationEvent.occurred_at.desc(),
            AssetLocationEvent.recorded_at.desc(),
            AssetLocationEvent.id.desc(),
        )
        .correlate(AssetUnit)
        .limit(1)
        .scalar_subquery()
    )
    events = {
        asset_id: event
        for asset_id, event in db.execute(
            select(AssetUnit.id, AssetLocationEvent)
            .outerjoin(AssetLocationEvent, AssetLocationEvent.id == event_id)
            .where(AssetUnit.id.in_([a.id for a in assets]))
        )
    }
    units = []
    for asset in assets:
        if len(claims[asset.id]) > 128:
            raise HTTPException(409, "Unit exceeds bounded identifier capacity")
        observation = latest.get(asset.id)
        event = events.get(asset.id)
        destination = event.payload_json.get("to_location_id") if event else None
        units.append(
            UnitSnapshot(
                asset_id=asset.id,
                asset_version=asset.version,
                device_model_id=asset.device_model_id,
                manufacturer_id=models[asset.device_model_id].manufacturer_id,
                archived=asset.lifecycle_status == LifecycleStatus.ARCHIVED,
                current_location_id=asset.current_location_id,
                location_verified_at=utc_stamp(asset.location_verified_at)
                if asset.location_verified_at
                else None,
                claims=tuple(claims[asset.id]),
                latest_observation=LocationEvidence(
                    location_id=observation.observed_location_id,
                    observed_at=utc_stamp(observation.observed_at),
                )
                if observation
                else None,
                approved_location=LocationEvidence(
                    location_id=UUID(destination), observed_at=utc_stamp(event.occurred_at)
                )
                if event and destination
                else None,
            )
        )
    payload = [u.model_dump(mode="json") for u in units]
    state = head(db)
    digest = hashlib.sha256(
        json.dumps(
            {
                "units": payload,
                "catalog": catalog_snapshot(db).fingerprint,
                "index_version": state.version,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return tuple(units), digest, {str(a.id): a.asset_code for a in assets}
