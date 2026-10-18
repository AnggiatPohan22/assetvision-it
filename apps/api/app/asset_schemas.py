"""Bounded physical asset contracts; missing serial means no identifier claim."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.assets import (
    AssetCondition,
    IdentifierSource,
    IdentifierType,
    LifecycleStatus,
    VerificationStatus,
    normalize_identifier,
)
from app.catalog_schemas import Description, Input, Version

AssetCode = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,49}$", max_length=50),
]
BoundedVersion = Annotated[Version, Field(le=2_147_483_647)]


class AssetCreate(Input):
    asset_code: AssetCode
    device_model_id: uuid.UUID
    lifecycle_status: LifecycleStatus = LifecycleStatus.IN_STOCK
    condition: AssetCondition = AssetCondition.UNKNOWN
    notes: Description | None = None
    purchase_date: date | None = None
    installed_at: AwareDatetime | None = None


class Changes(Input):
    version: BoundedVersion

    @model_validator(mode="before")
    @classmethod
    def valid_changes(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if not values.keys() - {"version", "asset_version"}:
                raise ValueError("Provide at least one field to update")
            nullable = {"notes", "purchase_date", "installed_at"}
            if any(v is None and k not in nullable for k, v in values.items()):
                raise ValueError("Only notes and optional dates may be null")
        return values


class AssetPatch(Changes):
    device_model_id: uuid.UUID | None = None
    lifecycle_status: LifecycleStatus | None = None
    condition: AssetCondition | None = None
    notes: Description | None = None
    purchase_date: date | None = None
    installed_at: AwareDatetime | None = None


class AssetOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_code: str
    device_model_id: uuid.UUID
    lifecycle_status: LifecycleStatus
    condition: AssetCondition
    notes: str | None
    purchase_date: date | None
    installed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class AssetVersion(Input):
    version: BoundedVersion


def printable(value: str) -> str:
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("Identifier must contain printable characters")
    return value


RawValue = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255),
    AfterValidator(printable),
]


class IdentifierCreate(Input):
    asset_version: BoundedVersion
    identifier_type: IdentifierType
    raw_value: RawValue
    source: IdentifierSource
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    notes: Description | None = None

    @model_validator(mode="after")
    def valid_identifier(self) -> "IdentifierCreate":
        normalize_identifier(self.identifier_type, self.raw_value)
        return self


class IdentifierPatch(Changes):
    asset_version: BoundedVersion
    identifier_type: IdentifierType | None = None
    raw_value: RawValue | None = None
    source: IdentifierSource | None = None
    verification_status: VerificationStatus | None = None
    notes: Description | None = None


class IdentifierOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_id: uuid.UUID
    identifier_type: IdentifierType
    raw_value: str
    normalized_value: str
    source: IdentifierSource
    verification_status: VerificationStatus
    notes: str | None
    created_at: datetime
    deleted_at: datetime | None
    version: int
    collision_asset_ids: list[uuid.UUID] = Field(default_factory=list)


class IdentifierMutation(BaseModel):
    identifier: IdentifierOutput
    asset_version: int


class AssetEventOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_id: uuid.UUID
    actor_id: uuid.UUID
    event_type: str
    before_json: dict[str, Any] | None
    after_json: dict[str, Any]
    recorded_at: datetime
