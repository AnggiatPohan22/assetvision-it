"""Private, authenticated reference image upload, list, content, and delete."""

import hashlib
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request as FormRequest
from starlette.types import Message

from app.catalog import DeviceModel, DeviceReferenceImage
from app.catalog_routes import Admin
from app.catalog_schemas import ErrorOutput, Name100
from app.catalog_service import get_record
from app.config import get_settings
from app.dependencies import CurrentUser, Database
from app.image_service import delete_image, upload_image
from app.image_validation import validate_image
from app.storage import StorageError, StorageProvider, get_storage

Storage = Annotated[StorageProvider, Depends(get_storage)]
router = APIRouter(
    prefix="/api/v1/device-models",
    tags=["Reference images"],
    responses={
        status: {"model": ErrorOutput} for status in (400, 401, 403, 404, 409, 413, 415, 422, 503)
    },
)


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, le=2_147_483_647)
    angle: Name100 | None = None


class ImageOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    device_model_id: uuid.UUID
    sha256: str
    mime_type: str
    byte_size: int
    angle: str | None
    is_primary: bool
    uploaded_by: uuid.UUID
    created_at: datetime
    content_url: str


class UploadOutput(BaseModel):
    image: ImageOutput
    model_version: int


class ImageListOutput(BaseModel):
    items: list[ImageOutput]
    model_version: int


def output(record: DeviceReferenceImage) -> ImageOutput:
    fields = {key: getattr(record, key) for key in ImageOutput.model_fields if key != "content_url"}
    return ImageOutput(
        **fields,
        content_url=(
            f"/api/v1/device-models/{record.device_model_id}/reference-images/{record.id}/content"
        ),
    )


async def multipart_image(request: Request) -> tuple[bytes, str, UploadMetadata]:
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(415, "Upload requires multipart/form-data")
    limit = get_settings().image_max_bytes
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit + 65536:
            raise HTTPException(413, "Upload request exceeds configured limit")
        chunks.append(chunk)
    body = b"".join(chunks)

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    # Parse only after auth/CSRF and a streamed total-body cap, including chunked requests.
    parsed_request = FormRequest(request.scope, receive)
    try:
        async with parsed_request.form(max_files=1, max_fields=2, max_part_size=4096) as form:
            if set(form) - {"file", "version", "angle"} or any(
                len(form.getlist(key)) != 1 for key in form
            ):
                raise HTTPException(422, "Only one file, version, and optional angle are allowed")
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise HTTPException(422, "Exactly one image file is required")
            metadata = UploadMetadata.model_validate(
                {key: form[key] for key in ("version", "angle") if key in form}
            )
            data = await upload.read(limit + 1)
            if len(data) > limit:
                raise HTTPException(413, "Image exceeds configured byte limit")
            return data, upload.content_type or "", metadata
    except ValidationError as error:
        issues = [{**issue, "loc": ("body", *issue["loc"])} for issue in error.errors()]
        raise RequestValidationError(issues) from None
    except StarletteHTTPException as error:
        if error.status_code == 400:
            raise HTTPException(400, "Invalid multipart upload") from None
        raise


@router.post(
    "/{model_id}/reference-images",
    response_model=UploadOutput,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file", "version"],
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "version": {"type": "integer", "minimum": 1, "maximum": 2_147_483_647},
                            "angle": {"type": "string", "maxLength": 100},
                        },
                    }
                }
            },
        }
    },
)
async def upload_reference(
    model_id: uuid.UUID, request: Request, db: Database, user: Admin, storage: Storage
) -> UploadOutput:
    await run_in_threadpool(get_record, db, DeviceModel, model_id)
    data, content_type, metadata = await multipart_image(request)
    image = await run_in_threadpool(validate_image, data, content_type)
    record, version = await run_in_threadpool(
        upload_image, db, storage, model_id, metadata.version, metadata.angle, image, user
    )
    return UploadOutput(image=output(record), model_version=version)


@router.get("/{model_id}/reference-images", response_model=ImageListOutput)
def list_images(model_id: uuid.UUID, db: Database, user: CurrentUser) -> ImageListOutput:
    model = get_record(db, DeviceModel, model_id)
    records = db.scalars(
        select(DeviceReferenceImage)
        .where(DeviceReferenceImage.device_model_id == model_id)
        .order_by(DeviceReferenceImage.created_at, DeviceReferenceImage.id)
    )
    return ImageListOutput(
        items=[output(record) for record in records], model_version=model.version
    )


@router.get(
    "/{model_id}/reference-images/{image_id}/content",
    response_class=Response,
    responses={
        200: {
            "description": "Private sanitized image bytes; no-store and nosniff.",
            "content": {
                mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("image/jpeg", "image/png", "image/webp")
            },
        }
    },
)
def serve_image(
    model_id: uuid.UUID, image_id: uuid.UUID, db: Database, user: CurrentUser, storage: Storage
) -> Response:
    record = db.scalar(
        select(DeviceReferenceImage).where(
            DeviceReferenceImage.id == image_id, DeviceReferenceImage.device_model_id == model_id
        )
    )
    if record is None:
        raise HTTPException(404, "Reference image not found")
    try:
        data = storage.read(record.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, "Reference image content not found") from None
    except StorageError:
        raise HTTPException(503, "Image storage is unavailable") from None
    if len(data) != record.byte_size or hashlib.sha256(data).hexdigest() != record.sha256:
        raise HTTPException(503, "Stored image integrity check failed")
    return Response(
        data,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{image_id.hex}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/{model_id}/reference-images/{image_id}",
    status_code=204,
    responses={
        204: {
            "description": "Metadata removed; failed file unlink is queued for cleanup retry.",
            "headers": {
                "X-Model-Version": {
                    "description": "New model version after deletion.",
                    "schema": {"type": "integer"},
                }
            },
        }
    },
)
def remove_image(
    model_id: uuid.UUID,
    image_id: uuid.UUID,
    db: Database,
    user: Admin,
    storage: Storage,
    version: Annotated[int, Query(ge=1)],
    response: Response,
) -> None:
    response.headers["X-Model-Version"] = str(
        delete_image(db, storage, model_id, image_id, version, user)
    )
