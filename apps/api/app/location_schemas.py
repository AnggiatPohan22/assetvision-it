"""Strict bounded location contracts, validated again after merging PATCH fields."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from app.catalog_schemas import Code, Input, Name200, RecordOutput, Version
from app.locations import LocationKind

Latitude = Annotated[float, Field(strict=True, ge=-90, le=90)]
Longitude = Annotated[float, Field(strict=True, ge=-180, le=180)]
Accuracy = Annotated[float, Field(strict=True, ge=0, le=10000000)]


class LocationCreate(Input):
    parent_id: uuid.UUID | None = None
    code: Code
    name: Name200
    kind: LocationKind
    is_active: StrictBool = True
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    gps_accuracy_m: Accuracy | None = None
    gps_recorded_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def coordinates(self) -> "LocationCreate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together")
        if self.latitude is None and (
            self.gps_accuracy_m is not None or self.gps_recorded_at is not None
        ):
            raise ValueError("GPS accuracy/time require coordinates")
        return self


class LocationPatch(Input):
    version: Version
    parent_id: uuid.UUID | None = None
    code: Code | None = None
    name: Name200 | None = None
    kind: LocationKind | None = None
    is_active: StrictBool | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    gps_accuracy_m: Accuracy | None = None
    gps_recorded_at: AwareDatetime | None = None

    @model_validator(mode="before")
    @classmethod
    def changes(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if not value.keys() - {"version"}:
                raise ValueError("Provide at least one field to update")
            if any(value.get(k, "omitted") is None for k in ("code", "name", "kind", "is_active")):
                raise ValueError("Code, name, kind and is_active cannot be null")
        return value


class LocationOutput(RecordOutput):
    parent_id: uuid.UUID | None
    code: str
    name: str
    kind: LocationKind
    latitude: float | None
    longitude: float | None
    gps_accuracy_m: float | None
    gps_recorded_at: datetime | None


class LocationTree(Input):
    items: list[LocationOutput]
    total: int
