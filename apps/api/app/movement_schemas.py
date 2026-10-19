"""Strict request, review and read contracts for the movement workflow."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.asset_location_routes import Reason
from app.asset_schemas import BoundedVersion
from app.catalog_schemas import Input
from app.movements import MovementStatus


class MovementCreate(Input):
    asset_version: BoundedVersion
    to_location_id: uuid.UUID
    reason: Reason


class MovementDecision(Input):
    version: BoundedVersion
    reason: Reason


class MovementOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_id: uuid.UUID
    from_location_id: uuid.UUID | None
    to_location_id: uuid.UUID
    status: MovementStatus
    reason: str
    requested_by: uuid.UUID
    requested_at: datetime
    expected_asset_version: int
    request_snapshot_json: dict[str, Any]
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_reason: str | None
    approved_at: datetime | None
    effective_at: datetime | None
    version: int


class MovementQuery(Input):
    status: MovementStatus | None = None
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=20, ge=1, le=100)


class MovementInboxQuery(MovementQuery):
    asset_id: uuid.UUID | None = None
