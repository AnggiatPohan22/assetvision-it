"""Strict evidence/review contracts; observations never overwrite asset master data."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.asset_location_routes import Reason
from app.asset_schemas import BoundedVersion
from app.catalog_schemas import Input
from app.observations import ObservationComparison, ObservationReviewStatus


class ObservationCreate(Input):
    asset_id: uuid.UUID | None = None
    asset_version: BoundedVersion | None = None
    observed_location_id: uuid.UUID
    observed_at: AwareDatetime | None = None
    evidence_note: Reason

    @model_validator(mode="after")
    def paired_asset_version(self) -> "ObservationCreate":
        if (self.asset_id is None) != (self.asset_version is None):
            raise ValueError("Linked observations require asset_id and asset_version together")
        return self


class ObservationReview(Input):
    version: BoundedVersion
    review_status: ObservationReviewStatus
    reason: Reason

    @model_validator(mode="after")
    def terminal_review(self) -> "ObservationReview":
        if self.review_status == ObservationReviewStatus.PENDING:
            raise ValueError("Choose ACKNOWLEDGED or DISMISSED")
        return self


class ObservationOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_id: uuid.UUID | None
    observed_location_id: uuid.UUID
    observed_by: uuid.UUID
    observed_at: datetime
    recorded_at: datetime
    evidence_note: str
    official_location_id_at_recording: uuid.UUID | None
    asset_version_at_recording: int | None
    comparison_status: ObservationComparison
    snapshot_json: dict[str, Any]
    review_status: ObservationReviewStatus
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_reason: str | None
    version: int


class ObservationQuery(Input):
    review_status: ObservationReviewStatus | None = None
    comparison_status: ObservationComparison | None = None
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=20, ge=1, le=100)


class ObservationInboxQuery(ObservationQuery):
    asset_id: uuid.UUID | None = None
    unlinked_only: bool = False


class AssetLocationStatus(BaseModel):
    asset_id: uuid.UUID
    asset_version: int
    current_location_id: uuid.UUID | None
    location_verified_at: datetime | None
    status: Literal["UNPLACED", "NO_OBSERVATION", "STALE_OBSERVATION", "MATCH", "LOCATION_CONFLICT"]
    location_conflict: bool
    latest_observation: ObservationOutput | None
