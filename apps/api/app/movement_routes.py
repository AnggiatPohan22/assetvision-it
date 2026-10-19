"""Movement history, inbox and authorized transitions."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.asset_service import get_asset
from app.catalog_schemas import ErrorOutput, Page
from app.catalog_service import list_records
from app.dependencies import CurrentUser, Database, require_roles
from app.location_routes import LocationRoute
from app.models import Role, User
from app.movement_schemas import (
    MovementCreate,
    MovementDecision,
    MovementInboxQuery,
    MovementOutput,
    MovementQuery,
)
from app.movement_service import decide_movement, get_movement, request_movement
from app.movements import AssetMovement, MovementStatus

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Writer = Annotated[User, Depends(require_roles(Role.ADMIN, Role.OFFICER))]
router = APIRouter(
    prefix="/api/v1",
    tags=["Asset movements"],
    route_class=LocationRoute,
    responses={code: {"model": ErrorOutput} for code in (401, 403, 404, 409, 413, 415, 422)},
)


def movement_list(db: Database, query: MovementQuery, asset_id: uuid.UUID | None) -> dict[str, Any]:
    statement = select(AssetMovement)
    if asset_id is not None:
        statement = statement.where(AssetMovement.asset_id == asset_id)
    if query.status is not None:
        statement = statement.where(AssetMovement.status == query.status)
    statement = statement.order_by(AssetMovement.requested_at.desc(), AssetMovement.id.desc())
    return list_records(db, statement, query.page, query.page_size)


@router.get("/assets/{asset_id}/movements", response_model=Page[MovementOutput])
def asset_movements(
    asset_id: uuid.UUID, db: Database, user: CurrentUser, query: Annotated[MovementQuery, Query()]
) -> dict[str, Any]:
    get_asset(db, asset_id)
    return movement_list(db, query, asset_id)


@router.post("/assets/{asset_id}/movements", response_model=MovementOutput, status_code=201)
def create_request(
    asset_id: uuid.UUID, data: MovementCreate, db: Database, user: Writer
) -> AssetMovement:
    return request_movement(
        db, asset_id, data.asset_version, data.to_location_id, data.reason, user
    )


@router.get("/movements", response_model=Page[MovementOutput])
def inbox(
    db: Database, user: Admin, query: Annotated[MovementInboxQuery, Query()]
) -> dict[str, Any]:
    return movement_list(db, query, query.asset_id)


@router.get("/movements/{movement_id}", response_model=MovementOutput)
def detail(movement_id: uuid.UUID, db: Database, user: CurrentUser) -> AssetMovement:
    return get_movement(db, movement_id)


@router.post("/movements/{movement_id}/approve", response_model=MovementOutput)
def approve(
    movement_id: uuid.UUID, data: MovementDecision, db: Database, user: Admin
) -> AssetMovement:
    return decide_movement(
        db, movement_id, data.version, MovementStatus.APPROVED, data.reason, user
    )


@router.post("/movements/{movement_id}/reject", response_model=MovementOutput)
def reject(
    movement_id: uuid.UUID, data: MovementDecision, db: Database, user: Admin
) -> AssetMovement:
    return decide_movement(
        db, movement_id, data.version, MovementStatus.REJECTED, data.reason, user
    )


@router.post("/movements/{movement_id}/cancel", response_model=MovementOutput)
def cancel(
    movement_id: uuid.UUID, data: MovementDecision, db: Database, user: Writer
) -> AssetMovement:
    return decide_movement(
        db, movement_id, data.version, MovementStatus.CANCELLED, data.reason, user
    )
