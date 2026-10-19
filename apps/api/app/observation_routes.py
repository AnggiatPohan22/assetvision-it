"""Observation evidence, ADMIN review, location status and immutable asset timeline."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.asset_service import get_asset
from app.catalog_schemas import ErrorOutput, Page
from app.catalog_service import list_records
from app.dependencies import CurrentUser, Database, require_roles
from app.location_routes import LocationRoute
from app.models import Role, User
from app.observation_schemas import (
    AssetLocationStatus,
    ObservationCreate,
    ObservationInboxQuery,
    ObservationOutput,
    ObservationQuery,
    ObservationReview,
)
from app.observation_service import (
    create_observation,
    get_observation,
    location_status,
    review_observation,
)
from app.observations import LocationObservation
from app.timeline import TimelineEventOutput, TimelineQuery, timeline

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Writer = Annotated[User, Depends(require_roles(Role.ADMIN, Role.OFFICER))]
router = APIRouter(
    prefix="/api/v1",
    tags=["Timeline and observations"],
    route_class=LocationRoute,
    responses={code: {"model": ErrorOutput} for code in (401, 403, 404, 409, 413, 415, 422)},
)


def observation_list(
    db: Database, query: ObservationQuery, asset_id: uuid.UUID | None = None, unlinked: bool = False
) -> dict[str, Any]:
    statement = select(LocationObservation)
    if unlinked:
        statement = statement.where(LocationObservation.asset_id.is_(None))
    elif asset_id is not None:
        statement = statement.where(LocationObservation.asset_id == asset_id)
    for field in ("review_status", "comparison_status"):
        value = getattr(query, field)
        if value is not None:
            statement = statement.where(getattr(LocationObservation, field) == value)
    return list_records(
        db,
        statement.order_by(
            LocationObservation.observed_at.desc(),
            LocationObservation.recorded_at.desc(),
            LocationObservation.id.desc(),
        ),
        query.page,
        query.page_size,
    )


@router.post("/location-observations", response_model=ObservationOutput, status_code=201)
def create(data: ObservationCreate, db: Database, user: Writer) -> LocationObservation:
    return create_observation(db, data, user)


@router.get("/location-observations", response_model=Page[ObservationOutput])
def inbox(
    db: Database, user: Admin, query: Annotated[ObservationInboxQuery, Query()]
) -> dict[str, Any]:
    if query.unlinked_only and query.asset_id is not None:
        raise HTTPException(422, "unlinked_only and asset_id are mutually exclusive")
    return observation_list(db, query, query.asset_id, query.unlinked_only)


@router.get("/location-observations/{observation_id}", response_model=ObservationOutput)
def detail(observation_id: uuid.UUID, db: Database, user: Admin) -> LocationObservation:
    return get_observation(db, observation_id)


@router.post("/location-observations/{observation_id}/review", response_model=ObservationOutput)
def review(
    observation_id: uuid.UUID, data: ObservationReview, db: Database, user: Admin
) -> LocationObservation:
    return review_observation(db, observation_id, data, user)


@router.get("/assets/{asset_id}/location-observations", response_model=Page[ObservationOutput])
def history(
    asset_id: uuid.UUID,
    db: Database,
    user: CurrentUser,
    query: Annotated[ObservationQuery, Query()],
) -> dict[str, Any]:
    get_asset(db, asset_id)
    return observation_list(db, query, asset_id)


@router.get("/assets/{asset_id}/location-status", response_model=AssetLocationStatus)
def status(asset_id: uuid.UUID, db: Database, user: CurrentUser) -> AssetLocationStatus:
    return location_status(db, asset_id)


@router.get("/assets/{asset_id}/timeline", response_model=Page[TimelineEventOutput])
def asset_timeline(
    asset_id: uuid.UUID, db: Database, user: CurrentUser, query: Annotated[TimelineQuery, Query()]
) -> dict[str, Any]:
    return timeline(db, asset_id, query)
