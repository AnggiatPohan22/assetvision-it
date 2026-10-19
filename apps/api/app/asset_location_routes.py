"""Bounded initial placement and read-only current-location lookup (Task 2-02)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, BeforeValidator, StringConstraints

from app.asset_location_service import initial_placement
from app.asset_schemas import AssetOutput, BoundedVersion
from app.asset_service import get_asset
from app.assets import AssetUnit
from app.catalog_schemas import ErrorOutput, Input, normalize_name
from app.dependencies import CurrentUser, Database, require_roles
from app.location_routes import LocationRoute
from app.location_schemas import LocationOutput
from app.locations import Location
from app.models import Role, User

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
router = APIRouter(
    prefix="/api/v1/assets",
    tags=["Asset locations"],
    route_class=LocationRoute,
    responses={code: {"model": ErrorOutput} for code in (401, 403, 404, 409, 413, 415, 422)},
)
Reason = Annotated[
    str, BeforeValidator(normalize_name), StringConstraints(min_length=1, max_length=2000)
]


class InitialPlacement(Input):
    version: BoundedVersion
    location_id: uuid.UUID
    reason: Reason


class AssetLocationOutput(BaseModel):
    asset_id: uuid.UUID
    version: int
    current_location_id: uuid.UUID | None
    location_verified_at: datetime | None
    location: LocationOutput | None


@router.get("/{asset_id}/location", response_model=AssetLocationOutput)
def lookup(asset_id: uuid.UUID, db: Database, user: CurrentUser) -> AssetLocationOutput:
    asset = get_asset(db, asset_id)
    location = db.get(Location, asset.current_location_id) if asset.current_location_id else None
    return AssetLocationOutput(
        asset_id=asset.id,
        version=asset.version,
        current_location_id=asset.current_location_id,
        location_verified_at=asset.location_verified_at,
        location=LocationOutput.model_validate(location) if location else None,
    )


@router.post("/{asset_id}/initial-placement", response_model=AssetOutput, status_code=201)
def place(asset_id: uuid.UUID, data: InitialPlacement, db: Database, user: Admin) -> AssetUnit:
    return initial_placement(db, asset_id, data.version, data.location_id, data.reason, user)
