"""Transactional catalog writes, safe errors, and optimistic concurrency."""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.catalog import DeviceCategory, DeviceModel, Manufacturer
from app.catalog_schemas import Patch
from app.models import AuditEvent, User

type Record = DeviceCategory | Manufacturer | DeviceModel


def get_record[T: Record](db: Session, entity: type[T], record_id: uuid.UUID) -> T:
    record = db.get(entity, record_id)
    if record is None:
        raise HTTPException(404, "Catalog record not found")
    return record


def list_records[T](
    db: Session,
    statement: Select[tuple[T]],
    page: int,
    page_size: int,
) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    return {
        "items": list(db.scalars(statement.offset((page - 1) * page_size).limit(page_size))),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def validate_references(db: Session, values: dict[str, Any]) -> None:
    for key, entity in (("category_id", DeviceCategory), ("manufacturer_id", Manufacturer)):
        if key not in values:
            continue
        record = db.scalar(
            select(entity).where(entity.id == values[key]).with_for_update(read=True)
        )
        if record is None:
            raise HTTPException(422, f"Unknown {key}")
        if not record.is_active:
            raise HTTPException(409, f"Inactive {key}")


def commit_record[T: Record](db: Session, record: T, user: User, action: str) -> T:
    try:
        db.flush()
        db.add(
            AuditEvent(
                actor_id=user.id,
                action=f"catalog_{action}",
                details={
                    "table": record.__tablename__,
                    "id": str(record.id),
                    "version": str(record.version),
                },
            )
        )
        db.commit()
    except StaleDataError:
        db.rollback()
        raise HTTPException(409, "Catalog record changed; reload and retry") from None
    except IntegrityError:
        db.rollback()
        # Includes concurrent uniqueness/FK races. Never expose SQL or constraint internals.
        raise HTTPException(
            409, "Catalog conflict; duplicate name/code or invalid reference"
        ) from None
    db.refresh(record)
    return record


def create_record[T: Record](db: Session, entity: type[T], values: dict[str, Any], user: User) -> T:
    if entity is DeviceModel:
        validate_references(db, values)
    record = entity(**values, created_by=user.id, updated_by=user.id)
    db.add(record)
    return commit_record(db, record, user, "create")


def check_version(record: Record, version: int) -> None:
    if record.version != version:
        raise HTTPException(409, "Catalog record changed; reload and retry")


def update_record[T: Record](db: Session, record: T, data: Patch, user: User) -> T:
    check_version(record, data.version)
    values = data.model_dump(exclude_unset=True, exclude={"version"})
    if isinstance(record, DeviceModel):
        refs = {
            key: value
            for key, value in values.items()
            if key in {"category_id", "manufacturer_id"} and value != getattr(record, key)
        }
        if values.get("is_active") is True and not record.is_active:
            refs = {
                "category_id": values.get("category_id", record.category_id),
                "manufacturer_id": values.get("manufacturer_id", record.manufacturer_id),
            }
        validate_references(db, refs)
    for key, value in values.items():
        setattr(record, key, value)
    record.updated_by = user.id
    # Force an UPDATE even for an unchanged value: version checks stay atomic at the DB.
    record.version += 1
    return commit_record(db, record, user, "update")


def archive_record(db: Session, record: DeviceModel, version: int, user: User) -> DeviceModel:
    check_version(record, version)
    if not record.is_active:
        return record
    record.is_active = False
    record.updated_by = user.id
    record.version += 1
    return commit_record(db, record, user, "archive")
