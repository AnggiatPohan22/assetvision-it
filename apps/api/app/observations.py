"""Retained field evidence and explicitly recorded review decisions."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.assets import VersionedRecord
from app.db import Base


class ObservationComparison(enum.StrEnum):
    UNLINKED = "UNLINKED"
    UNPLACED = "UNPLACED"
    MATCH = "MATCH"
    LOCATION_CONFLICT = "LOCATION_CONFLICT"


class ObservationReviewStatus(enum.StrEnum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"


class LocationObservation(VersionedRecord, Base):
    __tablename__ = "location_observations"
    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_location_observations_version",
        ),
        CheckConstraint(
            "length(evidence_note) BETWEEN 1 AND 2000 AND evidence_note = trim(evidence_note)",
            name="ck_location_observations_note",
        ),
        CheckConstraint(
            "(asset_id IS NULL AND asset_version_at_recording IS NULL AND "
            "official_location_id_at_recording IS NULL AND comparison_status = "
            "'UNLINKED') OR (asset_id IS NOT NULL AND asset_version_at_recording IS NOT"
            " NULL AND asset_version_at_recording > 0 AND comparison_status != "
            "'UNLINKED')",
            name="ck_location_observations_asset",
        ),
        CheckConstraint(
            "comparison_status = 'UNLINKED' OR (comparison_status = 'UNPLACED' AND "
            "official_location_id_at_recording IS NULL) OR (comparison_status = 'MATCH'"
            " AND official_location_id_at_recording IS NOT NULL AND "
            "official_location_id_at_recording = observed_location_id) OR "
            "(comparison_status = 'LOCATION_CONFLICT' AND "
            "official_location_id_at_recording IS NOT NULL AND "
            "official_location_id_at_recording != observed_location_id)",
            name="ck_location_observations_comparison",
        ),
        CheckConstraint(
            "(review_status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL"
            " AND review_reason IS NULL) OR (review_status != 'PENDING' AND reviewed_by"
            " IS NOT NULL AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL)",
            name="ck_location_observations_review",
        ),
        CheckConstraint(
            "review_reason IS NULL OR (length(review_reason) BETWEEN 1 AND 2000 AND "
            "review_reason = trim(review_reason))",
            name="ck_location_observations_review_reason",
        ),
        Index("ix_location_observations_latest", "asset_id", "observed_at", "recorded_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    observed_location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT")
    )
    observed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_note: Mapped[str] = mapped_column(String(2000))
    official_location_id_at_recording: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT")
    )
    asset_version_at_recording: Mapped[int | None] = mapped_column(Integer)
    comparison_status: Mapped[ObservationComparison] = mapped_column(
        Enum(
            ObservationComparison,
            native_enum=False,
            create_constraint=True,
            name="observation_comparison",
        ),
    )
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    review_status: Mapped[ObservationReviewStatus] = mapped_column(
        Enum(
            ObservationReviewStatus,
            native_enum=False,
            create_constraint=True,
            name="observation_review_status",
        ),
        default=ObservationReviewStatus.PENDING,
        server_default="PENDING",
        index=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(String(2000))
