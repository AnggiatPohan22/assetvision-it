"""Serialized hierarchy writes with version checks and transactional audit."""

import json
import uuid

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.location_schemas import LocationCreate, LocationOutput, LocationPatch
from app.locations import Location
from app.models import AuditEvent, User

# Shared with the frozen migration trigger; acquire BEFORE any hierarchy read.
HIERARCHY_LOCK = 649237804


def lock_hierarchy(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": HIERARCHY_LOCK})


def get_location(db: Session, location_id: uuid.UUID) -> Location:
    record = db.get(Location, location_id, populate_existing=True)
    if record is None:
        raise HTTPException(404, "Location not found")
    return record


def validate_parent(db: Session, record_id: uuid.UUID | None, parent_id: uuid.UUID | None) -> None:
    seen = {record_id} if record_id else set()
    first = True
    while parent_id is not None:
        if parent_id in seen:
            raise HTTPException(409, "Location hierarchy cannot contain cycles")
        seen.add(parent_id)
        parent = db.get(Location, parent_id, populate_existing=True)
        if parent is None:
            raise HTTPException(422, "Unknown parent location")
        if first and not parent.is_active:
            raise HTTPException(409, "Parent location is archived")
        first = False
        parent_id = parent.parent_id


def snapshot(record: Location) -> str:
    return LocationOutput.model_validate(record).model_dump_json()


def write_audit(db: Session, record: Location, user: User, before: str | None) -> None:
    action = "create" if before is None else "update"
    if before and json.loads(before)["is_active"] and not record.is_active:
        action = "archive"
    db.add(
        AuditEvent(
            actor_id=user.id,
            action=f"location_{action}",
            details={
                "id": str(record.id),
                "before": before or "null",
                "after": snapshot(record),
            },
        )
    )


def save_location(
    db: Session,
    user: User,
    data: LocationCreate | LocationPatch,
    location_id: uuid.UUID | None = None,
) -> Location:
    try:
        lock_hierarchy(db)
        before = None
        if location_id is None:
            assert isinstance(data, LocationCreate)
            validate_parent(db, None, data.parent_id)
            record = Location(**data.model_dump(), created_by=user.id, updated_by=user.id)
            db.add(record)
        else:
            assert isinstance(data, LocationPatch)
            record = get_location(db, location_id)
            if record.version != data.version:
                raise HTTPException(409, "Location changed; reload and retry")
            before = snapshot(record)
            values = {key: getattr(record, key) for key in LocationCreate.model_fields}
            changes = data.model_dump(exclude_unset=True, exclude={"version"})
            values.update(changes)
            try:
                # SQLite timestamps are naive on read, though all API inputs are aware.
                if "gps_recorded_at" not in changes:
                    from datetime import UTC

                    stamp = values["gps_recorded_at"]
                    if stamp is not None and stamp.tzinfo is None:
                        values["gps_recorded_at"] = stamp.replace(tzinfo=UTC)
                validated = LocationCreate.model_validate(values)
            except ValidationError:
                raise HTTPException(422, "Invalid combined location coordinates") from None
            if validated.parent_id != record.parent_id or (
                validated.is_active and not record.is_active
            ):
                validate_parent(db, record.id, validated.parent_id)
            for key, value in validated.model_dump().items():
                setattr(record, key, value)
            record.updated_by = user.id
            record.version += 1
        db.flush()
        write_audit(db, record, user, before)
        db.commit()
        db.refresh(record)
        return record
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(
            409, "Location conflict; reload and check code/parent/version"
        ) from None
    except Exception:
        db.rollback()
        raise
