"""Bounded private upload with durable cleanup reservation and persistent per-user throttling."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.requests import Request as FormRequest
from starlette.types import Message

from app.catalog import StorageCleanupJob
from app.config import get_settings
from app.image_service import cleanup_job
from app.models import AuditEvent, User
from app.recognition_encoder import decode_image
from app.recognition_index import actor
from app.recognition_observations import RecognitionJob, SurveyObservation
from app.storage import StorageCollisionError, StorageError, StorageProvider


def throttle(db: Session, user: User, kind: str | None = None) -> None:
    try:
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        now = datetime.now(UTC)
        count = (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.actor_id == user.id,
                    AuditEvent.action == "recognition_attempt",
                    AuditEvent.created_at >= now - timedelta(minutes=1),
                )
            )
            or 0
        )
        attached = (
            select(SurveyObservation.id)
            .where(
                (SurveyObservation.device_job_id == RecognitionJob.id)
                | (SurveyObservation.label_job_id == RecognitionJob.id)
            )
            .exists()
        )
        orphans = (
            db.scalar(
                select(func.count())
                .select_from(RecognitionJob)
                .where(RecognitionJob.created_by == user.id, RecognitionJob.kind == kind, ~attached)
            )
            or 0
        )
        if kind is not None and orphans >= 20:
            raise HTTPException(409, "Unattached upload limit reached; inspect saved evidence")
        if count >= 10:
            raise HTTPException(
                429, "Recognition limit reached; wait one minute", headers={"Retry-After": "60"}
            )
        db.add(
            AuditEvent(actor_id=user.id, action="recognition_attempt", created_at=now, details={})
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


async def read_upload(request: Request) -> tuple[bytes, str]:
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(415, "Recognition upload requires multipart/form-data")
    limit = get_settings().image_max_bytes
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit + 65536:
            raise HTTPException(413, "Recognition upload exceeds limit")
        body.extend(chunk)

    async def receive() -> Message:
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    try:
        parsed = FormRequest(request.scope, receive)
        async with parsed.form(max_files=1, max_fields=0, max_part_size=4096) as form:
            if set(form) != {"file"} or len(form.getlist("file")) != 1:
                raise HTTPException(422, "Exactly one image file required")
            upload = form["file"]
            if not isinstance(upload, UploadFile):
                raise HTTPException(422, "Image file required")
            data = await upload.read(limit + 1)
            if len(data) > limit:
                raise HTTPException(413, "Recognition file exceeds limit")
            return data, upload.content_type or ""
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Invalid multipart upload") from None


def save_job(
    db: Session,
    storage: StorageProvider,
    user: User,
    kind: str,
    data: bytes,
    mime_type: str,
    result: dict[str, Any],
) -> RecognitionJob:
    # Original bounded bytes retained privately; browser content is always sanitized separately.
    with decode_image(data, mime_type):
        pass
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
    key = f"{uuid.uuid4().hex}.{extension}"
    reservation = StorageCleanupJob(id=uuid.uuid4(), storage_key=key)
    db.add(reservation)
    db.commit()
    try:
        reserved = db.scalar(
            select(StorageCleanupJob)
            .where(StorageCleanupJob.id == reservation.id)
            .with_for_update()
        )
        if reserved is None:
            raise HTTPException(409, "Upload reservation expired")
        current = actor(db, user.id)
        if current.role not in {"ADMIN", "OFFICER"}:
            raise HTTPException(403, "Recognition upload requires a writer")
        storage.put(key, data)
        record = RecognitionJob(
            id=uuid.uuid4(),
            created_by=user.id,
            created_at=datetime.now(UTC),
            kind=kind,
            storage_key=key,
            sha256=hashlib.sha256(data).hexdigest(),
            mime_type=mime_type,
            result_json=result,
        )
        db.add(record)
        db.add(
            AuditEvent(
                actor_id=user.id,
                action="recognition_upload",
                details={"job_id": str(record.id), "kind": kind},
            )
        )
        db.delete(reserved)
        db.commit()
        return record
    except Exception as error:
        db.rollback()
        if isinstance(error, StorageCollisionError):
            reserved = db.get(StorageCleanupJob, reservation.id)
            if reserved:
                db.delete(reserved)
                db.commit()
        else:
            cleanup_job(db, storage, reservation.id)
        if isinstance(error, StorageError):
            raise HTTPException(503, "Recognition storage unavailable") from None
        raise
