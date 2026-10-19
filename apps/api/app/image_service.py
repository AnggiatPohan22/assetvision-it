"""Reference image transactions and durable, retryable filesystem cleanup."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.catalog import DeviceModel, DeviceReferenceImage, StorageCleanupJob
from app.catalog_service import check_version
from app.config import get_settings
from app.image_validation import ValidatedImage
from app.models import AuditEvent, User
from app.recognition_observations import RecognitionJob
from app.storage import StorageCollisionError, StorageError, StorageProvider

logger = logging.getLogger("assetvision.storage")


def lock_model(db: Session, model_id: uuid.UUID, version: int) -> DeviceModel:
    model = db.scalar(
        select(DeviceModel)
        .where(DeviceModel.id == model_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if model is None:
        raise HTTPException(404, "Catalog record not found")
    check_version(model, version)
    return model


def cleanup_job(db: Session, storage: StorageProvider, job_id: uuid.UUID) -> bool:
    """Never delete a referenced key, including an ambiguous upload commit outcome."""
    try:
        job = db.scalar(
            select(StorageCleanupJob)
            .where(StorageCleanupJob.id == job_id)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            db.rollback()
            return False
        if (
            db.scalar(
                select(DeviceReferenceImage.id).where(
                    DeviceReferenceImage.storage_key == job.storage_key
                )
            )
            is None
        ) and db.scalar(
            select(RecognitionJob.id).where(RecognitionJob.storage_key == job.storage_key)
        ) is None:
            storage.delete(job.storage_key)
        db.delete(job)
        db.commit()
        return True
    except (StorageError, SQLAlchemyError):
        db.rollback()
        logger.warning("storage_cleanup_pending")
        return False


def cleanup_pending(db: Session, storage: StorageProvider) -> int:
    # Grace protects the short interval between reservation commit and row-lock acquisition.
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    ids = list(
        db.scalars(
            select(StorageCleanupJob.id)
            .where(StorageCleanupJob.created_at < cutoff)
            .order_by(StorageCleanupJob.created_at, StorageCleanupJob.id)
            .limit(100)
        )
    )
    db.rollback()
    return sum(cleanup_job(db, storage, job_id) for job_id in ids)


def audit_image(
    db: Session, model: DeviceModel, image: DeviceReferenceImage, user: User, action: str
) -> None:
    model.version += 1
    model.updated_by = user.id
    db.add(
        AuditEvent(
            actor_id=user.id,
            action=action,
            details={
                "model_id": str(model.id),
                "image_id": str(image.id),
                "version": str(model.version),
            },
        )
    )


def upload_image(
    db: Session,
    storage: StorageProvider,
    model_id: uuid.UUID,
    version: int,
    angle: str | None,
    image: ValidatedImage,
    user: User,
) -> tuple[DeviceReferenceImage, int]:
    image_id = uuid.uuid4()
    key = f"{image_id.hex}.{image.extension}"
    job = StorageCleanupJob(id=uuid.uuid4(), storage_key=key)
    # Intent is durable BEFORE any bytes are written; crash cleanup needs no directory scan.
    db.add(job)
    db.commit()
    job_id = job.id
    try:
        reservation = db.scalar(
            select(StorageCleanupJob).where(StorageCleanupJob.id == job_id).with_for_update()
        )
        if reservation is None:
            raise HTTPException(409, "Upload reservation expired; retry")
        model = lock_model(db, model_id, version)
        if not model.is_active:
            raise HTTPException(409, "Archived models cannot receive new images")
        count = (
            db.scalar(
                select(func.count())
                .select_from(DeviceReferenceImage)
                .where(DeviceReferenceImage.device_model_id == model_id)
            )
            or 0
        )
        if count >= get_settings().image_max_per_model:
            raise HTTPException(409, "Reference image count limit reached")
        storage.put(key, image.data)
        record = DeviceReferenceImage(
            id=image_id,
            device_model_id=model_id,
            storage_key=key,
            sha256=image.sha256,
            mime_type=image.mime_type,
            byte_size=len(image.data),
            angle=angle,
            is_primary=count == 0,
            uploaded_by=user.id,
        )
        db.add(record)
        audit_image(db, model, record, user, "reference_image_upload")
        db.delete(job)
        db.commit()
        return record, model.version
    except Exception as error:
        db.rollback()
        if isinstance(error, StorageCollisionError):
            # No file was created. Preserve the existing file and cancel only our intent.
            reservation = db.get(StorageCleanupJob, job_id)
            if reservation is not None:
                db.delete(reservation)
                db.commit()
        else:
            cleanup_job(db, storage, job_id)
        if isinstance(error, StorageError):
            raise HTTPException(503, "Image storage is unavailable") from None
        if isinstance(error, (IntegrityError, StaleDataError)):
            raise HTTPException(409, "Image conflict; reload model and retry") from None
        raise


def delete_image(
    db: Session,
    storage: StorageProvider,
    model_id: uuid.UUID,
    image_id: uuid.UUID,
    version: int,
    user: User,
) -> int:
    try:
        model = lock_model(db, model_id, version)
        record = db.scalar(
            select(DeviceReferenceImage).where(
                DeviceReferenceImage.id == image_id,
                DeviceReferenceImage.device_model_id == model_id,
            )
        )
        if record is None:
            raise HTTPException(404, "Reference image not found")
        job = StorageCleanupJob(id=uuid.uuid4(), storage_key=record.storage_key)
        db.add(job)
        db.delete(record)
        db.flush()
        if record.is_primary:
            next_image = db.scalar(
                select(DeviceReferenceImage)
                .where(DeviceReferenceImage.device_model_id == model_id)
                .order_by(DeviceReferenceImage.created_at, DeviceReferenceImage.id)
                .limit(1)
            )
            if next_image is not None:
                next_image.is_primary = True
        audit_image(db, model, record, user, "reference_image_delete")
        db.commit()
        new_version = model.version
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(409, "Image conflict; reload model and retry") from None
    # Metadata removal + cleanup intent commit first. Failed unlink is safely retryable.
    cleanup_job(db, storage, job.id)
    return new_version
