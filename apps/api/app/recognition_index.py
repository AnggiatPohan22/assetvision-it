"""Atomic, optimistic index publication and fail-closed model-only search."""

import hashlib
import json
import math
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.catalog import DeviceModel, DeviceReferenceImage
from app.models import AuditEvent, Role, User
from app.recognition_encoder import EncoderUnavailable, ImageEncoder, decode_image, normalized
from app.recognition_models import EmbeddingIndex, EmbeddingIndexState, ImageEmbedding
from app.recognition_schemas import (
    CalibrationPolicy,
    EncoderSpec,
    ModelCandidate,
    RebuildRequest,
    SearchRequest,
    SearchResult,
    reviewed_calibration,
)
from app.storage import StorageError, StorageProvider


@dataclass(frozen=True)
class Reference:
    id: uuid.UUID
    model_id: uuid.UUID
    storage_key: str
    sha256: str
    byte_size: int
    mime_type: str


@dataclass(frozen=True)
class CatalogSnapshot:
    fingerprint: str
    references: tuple[Reference, ...]


def catalog_snapshot(db: Session) -> CatalogSnapshot:
    # One SQL statement includes inactive models and models without photos. Membership/version
    # changes invalidate the generation rather than silently altering its candidate universe.
    rows = (
        db.execute(
            select(
                DeviceModel.id,
                DeviceModel.version,
                DeviceModel.is_active,
                DeviceReferenceImage.id.label("image_id"),
                DeviceReferenceImage.storage_key,
                DeviceReferenceImage.sha256,
                DeviceReferenceImage.byte_size,
                DeviceReferenceImage.mime_type,
            )
            .outerjoin(DeviceReferenceImage, DeviceReferenceImage.device_model_id == DeviceModel.id)
            .order_by(DeviceModel.id, DeviceReferenceImage.id)
            .limit(5001)
        )
        .mappings()
        .all()
    )
    if len(rows) > 5000:
        raise HTTPException(409, "Catalog exceeds bounded index snapshot capacity")
    payload = [
        {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()} for row in rows
    ]
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    references = tuple(
        Reference(
            row["image_id"],
            row["id"],
            row["storage_key"],
            row["sha256"],
            row["byte_size"],
            row["mime_type"],
        )
        for row in rows
        if row["is_active"] and row["image_id"] is not None
    )
    if len(references) > 2000:
        raise HTTPException(409, "Index exceeds 2000 reference images")
    return CatalogSnapshot(digest, references)


def actor(db: Session, actor_id: uuid.UUID, *, admin: bool = False) -> User:
    user = db.scalar(
        select(User).where(User.id == actor_id).execution_options(populate_existing=True)
    )
    if user is None or not user.is_active or (admin and user.role != Role.ADMIN):
        raise HTTPException(
            403, "Active ADMIN required" if admin else "Active authenticated user required"
        )
    return user


def head(db: Session, *, lock: bool = False) -> EmbeddingIndexState:
    statement = select(EmbeddingIndexState).where(EmbeddingIndexState.id == 1)
    if lock:
        statement = statement.with_for_update()
    value = db.scalar(statement.execution_options(populate_existing=True))
    if value is None:
        raise HTTPException(503, "Embedding schema/head unavailable")
    return value


def clean_session(db: Session) -> None:
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, "Index operations require a clean transaction boundary")


def rebuild_index(
    db: Session,
    storage: StorageProvider,
    encoder: ImageEncoder,
    request: RebuildRequest,
    actor_id: uuid.UUID,
    calibration_report: dict[str, Any] | None = None,
) -> EmbeddingIndex:
    clean_session(db)
    try:
        actor(db, actor_id, admin=True)
        before_head = head(db)
        if before_head.version != request.expected_version:
            raise HTTPException(409, "Index head changed; inspect before rebuilding")
        snapshot = catalog_snapshot(db)
        spec = EncoderSpec.model_validate(encoder.spec)
        policy = None
        if calibration_report is not None:
            if request.calibration_reference_fingerprint != snapshot.fingerprint:
                raise HTTPException(409, "Reviewed calibration does not match catalog references")
            actual_counts = dict(Counter(str(ref.model_id) for ref in snapshot.references))
            reported_counts = calibration_report.get("per_model_counts", {})
            if (
                not isinstance(reported_counts, dict)
                or {
                    key: value.get("reference") if isinstance(value, dict) else None
                    for key, value in reported_counts.items()
                }
                != actual_counts
            ):
                raise HTTPException(422, "Evaluation reference counts/model IDs mismatch")
            try:
                policy = reviewed_calibration(calibration_report, spec, snapshot.fingerprint)
            except (ValueError, TypeError):
                raise HTTPException(
                    422, "Calibration evidence is not eligible or mismatched"
                ) from None
        elif request.calibration_reference_fingerprint is not None:
            raise HTTPException(422, "Calibration report required with calibration fingerprint")
        # CPU/file work holds no database row locks or transaction. Publication rechecks both
        # source snapshot and head version, and never retries with a newer version silently.
        db.rollback()
        vectors: list[tuple[Reference, list[float]]] = []
        for reference in snapshot.references:
            data = storage.read(reference.storage_key)
            if (
                len(data) != reference.byte_size
                or hashlib.sha256(data).hexdigest() != reference.sha256
            ):
                raise HTTPException(409, "Reference bytes differ from catalog metadata")
            image = decode_image(data, reference.mime_type)
            with image:
                vector = normalized(encoder.encode(image), spec.dimensions)
            vectors.append((reference, vector))
        if encoder.spec != spec:
            raise HTTPException(409, "Encoder version changed during rebuild")
        # Lock order is index head then read-only catalog snapshot; no catalog writer takes
        # this head lock. A concurrent catalog change may make the published index stale;
        # every search checks the fingerprint again and rejects it rather than mixing data.
        state = head(db, lock=True)
        actor(db, actor_id, admin=True)
        if state.version != request.expected_version:
            raise HTTPException(409, "Another rebuild won; reload head before retrying")
        if catalog_snapshot(db) != snapshot:
            raise HTTPException(409, "Catalog changed during rebuild; inspect and retry explicitly")
        record = EmbeddingIndex(
            id=uuid.uuid4(),
            encoder_spec=spec.model_dump(mode="json"),
            reference_fingerprint=snapshot.fingerprint,
            reference_count=len(vectors),
            calibration=policy.model_dump(mode="json") if policy else None,
            created_by=actor_id,
        )
        db.add(record)
        db.flush()
        for reference, vector in vectors:
            db.add(
                ImageEmbedding(
                    index_id=record.id,
                    reference_image_id=reference.id,
                    reference_snapshot_id=reference.id,
                    device_model_id=reference.model_id,
                    source_sha256=reference.sha256,
                    vector_data=vector,
                )
            )
        state.current_index_id = record.id
        state.version += 1
        db.add(
            AuditEvent(
                actor_id=actor_id,
                action="recognition_index_rebuild",
                details={
                    "index_id": str(record.id),
                    "generation_version": str(state.version),
                    "reference_count": str(len(vectors)),
                    "reference_fingerprint": snapshot.fingerprint,
                    "encoder_fingerprint": spec.fingerprint,
                    "calibrated": str(policy is not None).lower(),
                    "reason": request.reason,
                },
            )
        )
        db.commit()
        db.refresh(record)
        return record
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(
            409, "Index/source conflict; no partial generation was published"
        ) from None
    except (StorageError, OSError, EncoderUnavailable):
        db.rollback()
        raise HTTPException(503, "Index encoder or reference storage unavailable") from None
    except ValueError:
        db.rollback()
        raise HTTPException(422, "Invalid encoder specification or vector") from None
    except Exception:
        db.rollback()
        raise


def search_models(
    db: Session,
    encoder: ImageEncoder | None,
    data: bytes,
    mime_type: str,
    request: SearchRequest,
    actor_id: uuid.UUID,
) -> SearchResult:
    clean_session(db)
    actor(db, actor_id)
    state = head(db)
    generation = state.version
    index_id = state.current_index_id
    # Validate untrusted bytes even when no index is available; never persist the query.
    with decode_image(data, mime_type) as image:
        if index_id is None:
            return SearchResult(
                status="UNKNOWN_MODEL",
                reason="EMPTY_INDEX",
                index_id=None,
                generation_version=generation,
                encoder=None,
            )
        record = db.get(EmbeddingIndex, index_id, populate_existing=True)
        if record is None:
            raise HTTPException(503, "Published index unavailable")
        try:
            spec = EncoderSpec.model_validate(record.encoder_spec)
        except ValidationError:
            raise HTTPException(503, "Published encoder metadata invalid") from None
        base = {"index_id": index_id, "generation_version": generation, "encoder": spec}

        def uncertain(reason: str) -> SearchResult:
            return SearchResult(status="UNCERTAIN", reason=reason, **base)

        if catalog_snapshot(db).fingerprint != record.reference_fingerprint:
            return uncertain("STALE_REFERENCE_INDEX")
        rows = list(db.scalars(select(ImageEmbedding).where(ImageEmbedding.index_id == index_id)))
        if len(rows) != record.reference_count:
            return uncertain("INCOMPLETE_INDEX")
        if not rows:
            return SearchResult(status="UNKNOWN_MODEL", reason="NO_ACTIVE_REFERENCES", **base)
        if encoder is None:
            return uncertain("ENCODER_NOT_CONFIGURED")
        if encoder.spec != spec:
            return uncertain("ENCODER_VERSION_MISMATCH")
        try:
            query = normalized(encoder.encode(image), spec.dimensions)
            best: dict[uuid.UUID, tuple[float, uuid.UUID]] = {}
            for row in rows:
                vector = normalized(row.vector_data, spec.dimensions)
                # Stored vectors are unit vectors; reject corrupt/non-normalized artifacts.
                if abs(math.fsum(x * x for x in row.vector_data) - 1) > 1e-6:
                    return uncertain("INVALID_INDEX_VECTOR")
                score = max(
                    -1.0, min(1.0, math.fsum(a * b for a, b in zip(query, vector, strict=True)))
                )
                old = best.get(row.device_model_id)
                if (
                    old is None
                    or score > old[0]
                    or (score == old[0] and row.reference_snapshot_id.int < old[1].int)
                ):
                    best[row.device_model_id] = score, row.reference_snapshot_id
        except EncoderUnavailable:
            return uncertain("ENCODER_UNAVAILABLE")
        except (ValueError, TypeError):
            return uncertain("INVALID_ENCODER_OR_INDEX_VECTOR")
    # Fresh reads after CPU work detect catalog changes and concurrent generation replacement.
    actor(db, actor_id)
    after = head(db)
    if after.version != generation or after.current_index_id != index_id:
        return uncertain("INDEX_CHANGED_DURING_QUERY")
    if catalog_snapshot(db).fingerprint != record.reference_fingerprint:
        return uncertain("STALE_REFERENCE_INDEX")
    if encoder.spec != spec:
        return uncertain("ENCODER_VERSION_MISMATCH")
    ranked = sorted(best.items(), key=lambda item: (-item[1][0], item[0].int))[: request.top_k]
    candidates = tuple(
        ModelCandidate(
            device_model_id=model_id,
            rank=rank,
            similarity=values[0],
            reference_image_snapshot_id=values[1],
        )
        for rank, (model_id, values) in enumerate(ranked, 1)
    )
    if record.calibration is None:
        return SearchResult(
            status="UNCERTAIN", reason="UNCALIBRATED_SIMILARITY_ONLY", candidates=candidates, **base
        )
    try:
        policy = CalibrationPolicy.model_validate(record.calibration)
    except ValidationError:
        return uncertain("INVALID_CALIBRATION")
    if (
        policy.encoder_fingerprint != spec.fingerprint
        or policy.reference_fingerprint != record.reference_fingerprint
    ):
        return uncertain("CALIBRATION_VERSION_MISMATCH")
    if ranked[0][1][0] < policy.threshold:
        return SearchResult(
            status="UNKNOWN_MODEL",
            reason="BELOW_CALIBRATED_THRESHOLD",
            calibrated=True,
            threshold=policy.threshold,
            **base,
        )
    return SearchResult(
        status="KNOWN_MODEL_CANDIDATE",
        reason="CALIBRATED_MODEL_CANDIDATES_ONLY",
        calibrated=True,
        threshold=policy.threshold,
        candidates=candidates,
        **base,
    )
