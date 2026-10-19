"""Atomic retained predictions and reviews. Recognition never mutates asset master data."""

import hashlib
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.asset_service import transaction
from app.catalog import DeviceModel
from app.evidence_fusion import fuse_evidence
from app.fusion_schemas import FusionInput, IdentityEvidence
from app.locations import Location
from app.models import AuditEvent, Role, User
from app.ocr_parser import parse_lines
from app.ocr_schemas import OCRLine, OCRResult
from app.ocr_service import read_label
from app.recognition_index import actor
from app.recognition_observations import RecognitionJob, RecognitionReview, SurveyObservation
from app.recognition_schemas import SearchResult
from app.survey_schemas import SurveyCreate, SurveyReview
from app.survey_snapshot import snapshot


@contextmanager
def survey_transaction(db: Session) -> Generator[None]:
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, "Clean survey transaction boundary required")
    db.rollback()
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.connection(execution_options={"isolation_level": "SERIALIZABLE"})
    try:
        with transaction(db):
            yield
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) in {"40001", "40P01"}:
            raise HTTPException(409, "Registry changed concurrently; reload evidence") from None
        raise


def audit(db: Session, user: User, action: str, record_id: uuid.UUID) -> None:
    db.add(AuditEvent(actor_id=user.id, action=action, details={"record_id": str(record_id)}))


def writer(db: Session, user: User, *, admin: bool = False) -> User:
    current = actor(db, user.id, admin=admin)
    if current.role not in {Role.ADMIN, Role.OFFICER}:
        raise HTTPException(403, "Observation requires OFFICER or ADMIN")
    return current


def job(db: Session, job_id: uuid.UUID, kind: str, user: User) -> RecognitionJob:
    record = db.get(RecognitionJob, job_id)
    if record is None or record.created_by != user.id or record.kind != kind:
        raise HTTPException(404, "Owned recognition evidence not found")
    return record


def get_observation(db: Session, observation_id: uuid.UUID, user: User) -> SurveyObservation:
    record = db.get(SurveyObservation, observation_id, populate_existing=True)
    if record is None:
        raise HTTPException(404, "Observation not found")
    return record


def output(db: Session, record: SurveyObservation) -> dict[str, Any]:
    review = db.scalar(
        select(RecognitionReview).where(RecognitionReview.observation_id == record.id)
    )
    return {
        "id": record.id,
        "version": 1,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "observed_at": record.observed_at,
        "observed_location_id": record.observed_location_id,
        "device_job_id": record.device_job_id,
        "label_job_id": record.label_job_id,
        "notes": record.notes,
        "evidence": record.evidence_json,
        "asset_id": review.selected_asset_id if review else None,
        "review_status": review.decision if review else "PENDING",
        "review": {
            "id": review.id,
            "reviewer_id": review.reviewer_id,
            "reviewed_at": review.reviewed_at,
            "decision": review.decision,
            "selected_asset_id": review.selected_asset_id,
            "selected_model_id": review.selected_model_id,
            "notes": review.notes,
            "evidence": review.evidence_json,
        }
        if review
        else None,
    }


def create_observation(db: Session, data: SurveyCreate, user: User) -> SurveyObservation:
    digest = hashlib.sha256(data.model_dump_json().encode()).hexdigest()
    with survey_transaction(db):
        writer(db, user)
        # Serialize retries for this actor. Unique request_id also prevents cross-actor reuse.
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        existing = db.scalar(
            select(SurveyObservation).where(SurveyObservation.request_id == data.request_id)
        )
        if existing:
            if existing.created_by != user.id or existing.payload_sha256 != digest:
                raise HTTPException(409, "Request key reused; inspect original observation")
            return existing
        model_job = job(db, data.device_job_id, "MODEL", user)
        label_job = job(db, data.label_job_id, "OCR", user) if data.label_job_id else None
        units, fingerprint, codes = snapshot(db)
        location = (
            db.get(Location, data.observed_location_id) if data.observed_location_id else None
        )
        if data.observed_location_id and (location is None or not location.is_active):
            raise HTTPException(409, "Observed location unavailable or archived")
        now = datetime.now(UTC)
        observed_at = (data.observed_at or now).astimezone(UTC)
        if observed_at > now:
            raise HTTPException(422, "Observation time cannot be in the future")
        visual = SearchResult.model_validate(model_job.result_json)
        ocr = OCRResult.model_validate(label_job.result_json) if label_job else None
        if data.correction:
            if ocr:
                manual = parse_lines(
                    tuple(
                        OCRLine(text=line, score=1.0)
                        for line in data.correction.corrected_text.split("\n")
                    ),
                    manual=True,
                )
                ocr = ocr.model_copy(
                    update={
                        "corrected_text": data.correction.corrected_text,
                        "manual_candidates": manual,
                        "status": "REVIEW_REQUIRED" if manual else ocr.status,
                        "reason": "MANUAL_CORRECTION_REQUIRES_REVIEW",
                    }
                )
            else:
                ocr = read_label(None, None, None, data.correction)
        candidates = (ocr.ocr_candidates + ocr.manual_candidates) if ocr else ()
        if len(candidates) > 128:
            raise HTTPException(422, "Combined label evidence exceeds 128 candidates")
        fusion = fuse_evidence(
            FusionInput(
                snapshot_at=now,
                observed_at=observed_at,
                observed_location_id=data.observed_location_id,
                visual=None if data.force_unknown else visual,
                identifiers=()
                if data.force_unknown
                else tuple(IdentityEvidence(candidate=c) for c in candidates),
                units=units,
                complete_snapshot=True,
            )
        )
        chosen = {c.asset_id for c in fusion.candidates}
        record = SurveyObservation(
            id=uuid.uuid4(),
            request_id=data.request_id,
            payload_sha256=digest,
            created_by=user.id,
            created_at=now,
            observed_at=observed_at,
            observed_location_id=data.observed_location_id,
            device_job_id=model_job.id,
            label_job_id=label_job.id if label_job else None,
            notes=data.notes,
            evidence_json={
                "visual": visual.model_dump(mode="json"),
                "ocr": ocr.model_dump(mode="json") if ocr else None,
                "fusion": fusion.model_dump(mode="json"),
                "force_unknown": data.force_unknown,
                "snapshot_fingerprint": fingerprint,
                "unit_snapshots": [
                    u.model_dump(mode="json") for u in units if u.asset_id in chosen
                ],
                "asset_codes": {str(i): codes[str(i)] for i in chosen},
                "model_names": {
                    str(m.id): m.model_name
                    for m in db.scalars(
                        select(DeviceModel).where(
                            DeviceModel.id.in_(
                                set(fusion.model_candidates)
                                | {u.device_model_id for u in units if u.asset_id in chosen}
                            )
                        )
                    )
                },
                "location_name": location.name if location else None,
            },
        )
        db.add(record)
        audit(db, user, "recognition_observation_create", record.id)
    return record


def review_observation(
    db: Session, observation_id: uuid.UUID, data: SurveyReview, user: User
) -> SurveyObservation:
    with survey_transaction(db):
        writer(db, user, admin=True)
        record = db.scalar(
            select(SurveyObservation)
            .where(SurveyObservation.id == observation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if record is None:
            raise HTTPException(404, "Observation not found")
        if db.scalar(
            select(RecognitionReview.id).where(RecognitionReview.observation_id == record.id)
        ):
            raise HTTPException(409, "Observation already reviewed; reload")
        review_evidence: dict[str, Any] = {"policy_version": "unique-checked-identifier-v1"}
        selected_model_id = None
        if data.decision == "MATCH":
            if record.evidence_json["force_unknown"]:
                raise HTTPException(409, "Unknown observation needs new evidence, not forced match")
            units, fingerprint, _ = snapshot(db)
            if fingerprint != record.evidence_json["snapshot_fingerprint"]:
                raise HTTPException(409, "Registry evidence changed; record a fresh observation")
            selected = next((u for u in units if u.asset_id == data.selected_asset_id), None)
            if (
                selected is None
                or selected.archived
                or selected.asset_version != data.asset_version
            ):
                raise HTTPException(409, "Asset version changed or archived; reload")
            ocr_data = record.evidence_json["ocr"]
            ocr = OCRResult.model_validate(ocr_data) if ocr_data else None
            if not ocr or any(i >= len(ocr.manual_candidates) for i in data.checked_manual_indices):
                raise HTTPException(422, "Choose identifiers from retained manual correction")
            identifiers = tuple(
                IdentityEvidence(
                    candidate=ocr.manual_candidates[i],
                    human_checked=True,
                    manufacturer_id=data.manufacturer_id,
                )
                for i in data.checked_manual_indices
            )
            for identity in identifiers:
                c = identity.candidate
                if (
                    c.kind not in {"SERIAL_NUMBER", "MAC_LAN", "MAC_WLAN"}
                    or (
                        c.kind == "SERIAL_NUMBER"
                        and data.manufacturer_id != selected.manufacturer_id
                    )
                    or not any(
                        claim.kind == c.kind
                        and claim.value == c.normalized_value
                        and claim.verification == "VERIFIED"
                        for claim in selected.claims
                    )
                ):
                    raise HTTPException(
                        409, "Strong typed, scoped and verified master claim required"
                    )
            fusion = fuse_evidence(
                FusionInput(
                    snapshot_at=datetime.now(UTC),
                    observed_at=record.observed_at.replace(tzinfo=UTC),
                    observed_location_id=record.observed_location_id,
                    visual=SearchResult.model_validate(record.evidence_json["visual"]),
                    identifiers=identifiers,
                    units=units,
                    complete_snapshot=True,
                )
            )
            if (
                fusion.status != "PROBABLE_ASSET"
                or len(fusion.candidates) != 1
                or (fusion.candidates[0].asset_id != selected.asset_id)
            ):
                raise HTTPException(409, "Conflicting or ambiguous evidence cannot be verified")
            selected_model_id = selected.device_model_id
            review_evidence.update(
                {
                    "fusion": fusion.model_dump(mode="json"),
                    "checked_manual_indices": list(data.checked_manual_indices),
                    "manufacturer_id": str(data.manufacturer_id) if data.manufacturer_id else None,
                    "asset_version": selected.asset_version,
                    "snapshot_fingerprint": fingerprint,
                    "result_status": "VERIFIED_ASSET",
                    "label_checked": True,
                }
            )
        else:
            review_evidence["result_status"] = {
                "UNKNOWN": "UNKNOWN",
                "CONFLICT": "CONFLICT",
                "MORE_PHOTOS": "NEEDS_MORE_EVIDENCE",
            }[data.decision]
        review = RecognitionReview(
            id=uuid.uuid4(),
            observation_id=record.id,
            reviewer_id=user.id,
            reviewed_at=datetime.now(UTC),
            decision=data.decision,
            selected_asset_id=data.selected_asset_id,
            selected_model_id=selected_model_id,
            notes=data.notes,
            evidence_json=review_evidence,
        )
        db.add(review)
        audit(db, user, "recognition_observation_review", review.id)
    return record
