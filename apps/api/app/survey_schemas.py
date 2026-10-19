"""Browser inputs contain references/text only, never trusted model or master evidence."""

import uuid
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, StringConstraints, model_validator

from app.ocr_schemas import ManualCorrection
from app.recognition_schemas import Contract

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class SurveyCreate(Contract):
    request_id: uuid.UUID
    device_job_id: uuid.UUID
    label_job_id: uuid.UUID | None = None
    observed_location_id: uuid.UUID | None = None
    observed_at: AwareDatetime | None = None
    correction: ManualCorrection | None = None
    notes: Note
    force_unknown: StrictBool = False


class SurveyReview(Contract):
    version: Literal[1]
    decision: Literal["MATCH", "UNKNOWN", "CONFLICT", "MORE_PHOTOS"]
    selected_asset_id: uuid.UUID | None = None
    asset_version: Annotated[StrictInt, Field(ge=1)] | None = None
    manufacturer_id: uuid.UUID | None = None
    checked_manual_indices: tuple[Annotated[StrictInt, Field(ge=0, le=127)], ...] = Field(
        default=(), max_length=128
    )
    label_checked: StrictBool = False
    notes: Note

    @model_validator(mode="after")
    def policy(self) -> "SurveyReview":
        if self.decision == "MATCH":
            if not self.selected_asset_id or self.asset_version is None or not self.label_checked:
                raise ValueError("MATCH requires unit/version and explicit label inspection")
            if not self.checked_manual_indices or len(set(self.checked_manual_indices)) != len(
                self.checked_manual_indices
            ):
                raise ValueError("Choose distinct manually checked identifier indices")
        elif (
            self.selected_asset_id
            or self.asset_version
            or self.checked_manual_indices
            or (self.label_checked or self.manufacturer_id)
        ):
            raise ValueError("Non-match decisions cannot select identity evidence")
        return self
