"""Retained movement state machine."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.assets import VersionedRecord
from app.db import Base


class MovementStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class AssetMovement(VersionedRecord, Base):
    __tablename__ = "asset_movements"
    __table_args__ = (
        CheckConstraint(
            "version > 0 AND expected_asset_version > 0 AND expected_asset_version < 2147483647",
            name="ck_asset_movements_version",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 1 AND 2000 AND reason = trim(reason)",
            name="ck_asset_movements_reason",
        ),
        CheckConstraint(
            "from_location_id IS NULL OR from_location_id != to_location_id",
            name="ck_asset_movements_destination",
        ),
        CheckConstraint(
            "review_reason IS NULL OR (length(review_reason) BETWEEN 1 AND 2000 AND "
            "review_reason = trim(review_reason))",
            name="ck_asset_movements_review_reason",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL AND "
            "review_reason IS NULL) OR (status != 'PENDING' AND reviewed_by IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL)",
            name="ck_asset_movements_review",
        ),
        CheckConstraint(
            "(status = 'APPROVED' AND approved_at IS NOT NULL AND effective_at IS NOT "
            "NULL AND approved_at = reviewed_at AND effective_at = approved_at) OR "
            "(status != 'APPROVED' AND approved_at IS NULL AND effective_at IS NULL)",
            name="ck_asset_movements_approval",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    from_location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT")
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT")
    )
    status: Mapped[MovementStatus] = mapped_column(
        Enum(MovementStatus, native_enum=False, create_constraint=True, name="movement_status"),
        default=MovementStatus.PENDING,
        server_default="PENDING",
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(2000))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expected_asset_version: Mapped[int] = mapped_column(Integer)
    request_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(String(2000))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
