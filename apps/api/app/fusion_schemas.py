"""Internal immutable evidence snapshots; never accept these as trusted HTTP payloads."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from app.identifier_values import IdentifierType, normalize_identifier
from app.ocr_schemas import IdentifierCandidate
from app.recognition_schemas import Contract, SearchResult

BoundedText = Annotated[str, Field(min_length=1, max_length=255)]
IdentityKind = Literal["SERIAL_NUMBER", "MAC_LAN", "MAC_WLAN", "BSSID"]


class Claim(Contract):
    kind: IdentityKind
    value: BoundedText
    verification: Literal["VERIFIED", "UNVERIFIED", "DISPUTED"]
    source: Literal["MANUAL", "IMPORT", "CONTROLLER"]

    @model_validator(mode="after")
    def canonical(self) -> "Claim":
        if normalize_identifier(IdentifierType(self.kind), self.value) != self.value:
            raise ValueError("Canonical identifier required")
        return self


class IdentityEvidence(Contract):
    candidate: IdentifierCandidate
    # Set only by a trusted caller after checking the label/source, never by OCR score.
    human_checked: StrictBool = False
    manufacturer_id: UUID | None = None


class LocationEvidence(Contract):
    location_id: UUID
    observed_at: AwareDatetime


class UnitSnapshot(Contract):
    asset_id: UUID
    asset_version: Annotated[StrictInt, Field(ge=1)]
    device_model_id: UUID
    manufacturer_id: UUID
    archived: StrictBool = False
    current_location_id: UUID | None = None
    location_verified_at: AwareDatetime | None = None
    claims: tuple[Claim, ...] = Field(default=(), max_length=128)
    # Latest non-dismissed observation, selected by the existing Sprint 2 policy.
    latest_observation: LocationEvidence | None = None
    # Latest approved placement/movement event, never a pending request.
    approved_location: LocationEvidence | None = None


class FusionInput(Contract):
    snapshot_at: AwareDatetime
    observed_at: AwareDatetime
    observed_location_id: UUID | None = None
    visual: SearchResult | None = None
    identifiers: tuple[IdentityEvidence, ...] = Field(default=(), max_length=128)
    units: tuple[UnitSnapshot, ...] = Field(default=(), max_length=500)
    # Caller must supply all units/active claims, including archived/colliding units.
    complete_snapshot: Literal[True]

    @model_validator(mode="after")
    def consistent(self) -> "FusionInput":
        if self.observed_at > self.snapshot_at:
            raise ValueError("Observation cannot be newer than snapshot")
        if len({u.asset_id for u in self.units}) != len(self.units):
            raise ValueError("Duplicate unit snapshot")
        for unit in self.units:
            dates: list[datetime | None] = [unit.location_verified_at]
            dates.extend(
                x.observed_at
                for x in (unit.latest_observation, unit.approved_location)
                if x is not None
            )
            if any(t is not None and t > self.snapshot_at for t in dates):
                raise ValueError("Evidence cannot be newer than snapshot")
        return self


class UnitCandidate(Contract):
    asset_id: UUID
    asset_version: int
    device_model_id: UUID
    rank: int
    reasons: tuple[str, ...]


class FusionResult(Contract):
    status: Literal["PROBABLE_ASSET", "AMBIGUOUS", "CONFLICT", "UNKNOWN"]
    model_status: Literal["KNOWN_MODEL_CANDIDATE", "UNKNOWN_MODEL", "UNCERTAIN"]
    model_candidates: tuple[UUID, ...]
    candidates: tuple[UnitCandidate, ...]
    reasons: tuple[str, ...]
    snapshot_at: AwareDatetime
    observed_at: AwareDatetime
    requires_review: Literal[True] = True
    policy_version: Literal["evidence-fusion-v1"] = "evidence-fusion-v1"
