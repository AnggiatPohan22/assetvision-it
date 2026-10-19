"""Immutable recognition jobs, initial predictions and one append-only human decision."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Payload = JSON().with_variant(JSONB(), "postgresql")


class RecognitionJob(Base):
    __tablename__ = "recognition_jobs"
    __table_args__ = (CheckConstraint("kind IN ('MODEL','OCR')", name="ck_recognition_jobs_kind"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(10))
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(30))
    result_json: Mapped[dict[str, Any]] = mapped_column(Payload)


class SurveyObservation(Base):
    __tablename__ = "survey_observations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    device_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recognition_jobs.id"))
    label_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recognition_jobs.id"))
    notes: Mapped[str] = mapped_column(String(2000))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(Payload)


class RecognitionReview(Base):
    __tablename__ = "recognition_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('MATCH','UNKNOWN','CONFLICT','MORE_PHOTOS')",
            name="ck_recognition_reviews_decision",
        ),
        CheckConstraint(
            "(decision = 'MATCH' AND selected_asset_id IS NOT NULL AND "
            "selected_model_id IS NOT NULL) OR (decision != 'MATCH' AND "
            "selected_asset_id IS NULL AND selected_model_id IS NULL)",
            name="ck_recognition_reviews_selection",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey_observations.id"), unique=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str] = mapped_column(String(20))
    selected_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id"))
    selected_model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("device_models.id"))
    notes: Mapped[str] = mapped_column(String(2000))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(Payload)
