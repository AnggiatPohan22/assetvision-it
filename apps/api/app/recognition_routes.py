"""Authenticated recognition uploads, retained observations and ADMIN-only human review."""

import hashlib
import io
import threading
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from starlette.concurrency import run_in_threadpool

from app.catalog_routes import Admin
from app.catalog_service import list_records
from app.config import get_settings
from app.dependencies import CurrentUser, Database
from app.image_routes import Storage
from app.observation_routes import Writer
from app.ocr_adapter import PaddleCPUEngine
from app.ocr_service import OCREngine, OCRUnavailable, read_label
from app.recognition_encoder import EncoderUnavailable, ImageEncoder, decode_image
from app.recognition_http_encoder import ProcessCPUEncoder
from app.recognition_index import search_models
from app.recognition_observations import RecognitionJob, RecognitionReview, SurveyObservation
from app.recognition_schemas import SearchRequest
from app.recognition_uploads import read_upload, save_job, throttle
from app.storage import StorageError
from app.survey_schemas import SurveyCreate, SurveyReview
from app.survey_service import create_observation, get_observation, output, review_observation


# Deliberate unconfigured default preserves the Task3-01 production NO_GO.
# Dependency boundaries allow optional, pinned local adapters without browser-supplied settings.
def get_encoder() -> ImageEncoder | None:
    settings = get_settings()
    if settings.recognition_encoder_name:
        try:
            return ProcessCPUEncoder(
                settings.recognition_encoder_name, settings.recognition_weights_root
            )
        except (EncoderUnavailable, ValueError):
            return None
    return None


def get_ocr_engine() -> OCREngine | None:
    root = get_settings().ocr_models_root
    if root:
        try:
            return PaddleCPUEngine(root, timeout_seconds=15)
        except OCRUnavailable:
            return None
    return None


Encoder = Annotated[ImageEncoder | None, Depends(get_encoder)]
OCR = Annotated[OCREngine | None, Depends(get_ocr_engine)]
analysis_slot = threading.BoundedSemaphore(1)
preview_slots = threading.BoundedSemaphore(2)
router = APIRouter(prefix="/api/v1/recognition", tags=["Recognition"])


def job_output(record: RecognitionJob) -> dict[str, Any]:
    return {
        "id": record.id,
        "kind": record.kind,
        "created_at": record.created_at,
        "created_by": record.created_by,
        "source_image_sha256": record.sha256,
        "content_url": f"/api/v1/recognition/jobs/{record.id}/content",
        "result": record.result_json,
    }


@router.post("/model-candidates", status_code=201)
async def model_candidates(
    request: Request, db: Database, user: Writer, storage: Storage, encoder: Encoder
) -> dict[str, Any]:
    await run_in_threadpool(throttle, db, user, "MODEL")
    data, mime = await read_upload(request)
    if not analysis_slot.acquire(blocking=False):
        raise HTTPException(429, "Recognition analysis busy", headers={"Retry-After": "10"})
    try:
        try:
            result = await run_in_threadpool(
                search_models, db, encoder, data, mime, SearchRequest(), user.id
            )
        except EncoderUnavailable:
            result = await run_in_threadpool(
                search_models, db, None, data, mime, SearchRequest(), user.id
            )
    finally:
        analysis_slot.release()
    record = await run_in_threadpool(
        save_job, db, storage, user, "MODEL", data, mime, result.model_dump(mode="json")
    )
    return job_output(record)


@router.post("/ocr", status_code=201)
async def ocr(
    request: Request, db: Database, user: Writer, storage: Storage, engine: OCR
) -> dict[str, Any]:
    await run_in_threadpool(throttle, db, user, "OCR")
    data, mime = await read_upload(request)
    if not analysis_slot.acquire(blocking=False):
        raise HTTPException(429, "Recognition analysis busy", headers={"Retry-After": "10"})
    try:
        result = await run_in_threadpool(read_label, data, mime, engine)
    finally:
        analysis_slot.release()
    record = await run_in_threadpool(
        save_job, db, storage, user, "OCR", data, mime, result.model_dump(mode="json")
    )
    return job_output(record)


def visible_job(job_id: uuid.UUID, db: Database, user: CurrentUser) -> RecognitionJob:
    record = db.get(RecognitionJob, job_id)
    attached = db.scalar(
        select(SurveyObservation.id)
        .where(
            or_(SurveyObservation.device_job_id == job_id, SurveyObservation.label_job_id == job_id)
        )
        .limit(1)
    )
    if record is None or (record.created_by != user.id and user.role != "ADMIN" and not attached):
        raise HTTPException(404, "Recognition evidence not found")
    return record


@router.get("/jobs")
def pending_jobs(db: Database, user: CurrentUser) -> dict[str, Any]:
    attached = (
        select(SurveyObservation.id)
        .where(
            or_(
                SurveyObservation.device_job_id == RecognitionJob.id,
                SurveyObservation.label_job_id == RecognitionJob.id,
            )
        )
        .exists()
    )
    jobs = list(
        db.scalars(
            select(RecognitionJob)
            .where(RecognitionJob.created_by == user.id, ~attached)
            .order_by(RecognitionJob.created_at.desc(), RecognitionJob.id)
            .limit(41)
        )
    )
    if len(jobs) > 40:
        raise HTTPException(409, "Pending evidence exceeds bounded capacity")
    return {"items": [job_output(j) for j in jobs]}


@router.get("/jobs/{job_id}")
def job_detail(job_id: uuid.UUID, db: Database, user: CurrentUser) -> dict[str, Any]:
    return job_output(visible_job(job_id, db, user))


@router.get("/jobs/{job_id}/content")
def content(job_id: uuid.UUID, db: Database, user: CurrentUser, storage: Storage) -> Response:
    record = visible_job(job_id, db, user)
    try:
        data = storage.read(record.storage_key)
    except (StorageError, FileNotFoundError):
        raise HTTPException(503, "Recognition image unavailable") from None
    if hashlib.sha256(data).hexdigest() != record.sha256:
        raise HTTPException(503, "Recognition image integrity check failed")
    if not preview_slots.acquire(blocking=False):
        raise HTTPException(429, "Image preview busy", headers={"Retry-After": "1"})
    try:
        with decode_image(data, record.mime_type, max_bytes=8 * 1024 * 1024) as image:
            image.thumbnail((1600, 1600))
            target = io.BytesIO()
            image.save(target, format="JPEG", quality=85)
            preview = target.getvalue()
    finally:
        preview_slots.release()
    return Response(
        preview,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def json_input(request: Request, db: Database, user: Writer) -> bytes:
    await run_in_threadpool(throttle, db, user)
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, "Recognition writes require JSON")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 65536:
            raise HTTPException(413, "Recognition JSON exceeds 64KiB")
        body.extend(chunk)
    return bytes(body)


@router.post("/observations", status_code=201)
async def create(request: Request, db: Database, user: Writer) -> dict[str, Any]:
    body = await json_input(request, db, user)
    try:
        data = SurveyCreate.model_validate_json(body)
    except ValueError:
        raise HTTPException(422, "Invalid observation input") from None
    record = await run_in_threadpool(create_observation, db, data, user)
    return output(db, record)


@router.get("/observations")
def inbox(
    db: Database,
    user: CurrentUser,
    page: int = Query(default=1, ge=1, le=1000000),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    result = list_records(
        db,
        select(SurveyObservation).order_by(
            SurveyObservation.created_at.desc(), SurveyObservation.id.desc()
        ),
        page,
        page_size,
    )
    items = []
    for row in result["items"]:
        review = db.scalar(
            select(RecognitionReview).where(RecognitionReview.observation_id == row.id)
        )
        items.append(
            {
                "id": row.id,
                "created_at": row.created_at,
                "notes": row.notes,
                "review_status": review.decision if review else "PENDING",
                "result_status": row.evidence_json["fusion"]["status"],
                "location_name": row.evidence_json["location_name"],
            }
        )
    result["items"] = items
    return result


@router.get("/observations/{observation_id}")
def detail(observation_id: uuid.UUID, db: Database, user: CurrentUser) -> dict[str, Any]:
    return output(db, get_observation(db, observation_id, user))


@router.post("/observations/{observation_id}/review")
async def review(
    observation_id: uuid.UUID, request: Request, db: Database, user: Admin
) -> dict[str, Any]:
    body = await json_input(request, db, user)
    try:
        data = SurveyReview.model_validate_json(body)
    except ValueError:
        raise HTTPException(422, "Invalid review input") from None
    record = await run_in_threadpool(review_observation, db, observation_id, data, user)
    return output(db, record)


@router.get("/metrics")
def metrics(db: Database, user: Admin) -> dict[str, Any]:
    # Operational counts, never fabricated recognition accuracy or benchmark metrics.
    return {
        "observations": db.scalar(select(func.count()).select_from(SurveyObservation)),
        "reviews": db.scalar(select(func.count()).select_from(RecognitionReview)),
        "accuracy": None,
        "evaluation_status": "NO_GO_REAL_DATASET_REQUIRED",
    }
