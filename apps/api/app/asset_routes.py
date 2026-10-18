"""Authenticated physical-unit CRUD; no import, photo or movement endpoints."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, func, or_, select

from app.asset_schemas import (
    AssetCreate,
    AssetEventOutput,
    AssetOutput,
    AssetPatch,
    AssetVersion,
    IdentifierCreate,
    IdentifierMutation,
    IdentifierOutput,
    IdentifierPatch,
)
from app.asset_service import (
    create_asset,
    get_asset,
    identifier_output,
    mutate_identifier,
    update_asset,
)
from app.assets import (
    AssetChangeEvent,
    AssetIdentifier,
    AssetUnit,
    IdentifierType,
    LifecycleStatus,
    normalize_identifier,
)
from app.catalog_schemas import ErrorOutput, Page
from app.catalog_service import list_records
from app.dependencies import CurrentUser, Database, require_roles
from app.models import Role, User

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
router = APIRouter(
    prefix="/api/v1/assets",
    tags=["Physical assets"],
    responses={
        code: {"model": ErrorOutput, "description": description}
        for code, description in {
            401: "Authentication required",
            403: "Role, Origin or session CSRF rejected",
            404: "Asset or identifier not found",
            409: "Duplicate, reference or version conflict",
            422: "Invalid input or unknown model",
        }.items()
    },
)


class AssetFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: str = Field(default="", max_length=200)
    model_id: uuid.UUID | None = None
    status: LifecycleStatus | None = None


class AssetQuery(AssetFilters):
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=25, ge=1, le=100)


def asset_statement(db: Database, query: AssetFilters) -> Select[tuple[AssetUnit]]:
    statement = select(AssetUnit)
    if query.model_id is not None:
        statement = statement.where(AssetUnit.device_model_id == query.model_id)
    if query.status is not None:
        statement = statement.where(AssetUnit.lifecycle_status == query.status)
    search = query.search.strip().lower()
    if search:
        terms = [func.lower(AssetIdentifier.normalized_value).contains(search, autoescape=True)]
        try:
            mac = normalize_identifier(IdentifierType.MAC_LAN, search)
            terms.append(AssetIdentifier.normalized_value == mac)
        except ValueError:
            pass
        claim_match = (
            select(1)
            .where(
                AssetIdentifier.asset_id == AssetUnit.id,
                AssetIdentifier.deleted_at.is_(None),
                or_(*terms),
            )
            .correlate(AssetUnit)
            .exists()
        )
        statement = statement.where(
            or_(
                func.lower(AssetUnit.asset_code).contains(search, autoescape=True),
                claim_match,
            )
        )
    return statement.order_by(AssetUnit.asset_code, AssetUnit.id)


@router.get("", response_model=Page[AssetOutput])
def assets(
    db: Database, user: CurrentUser, query: Annotated[AssetQuery, Query()]
) -> dict[str, Any]:
    return list_records(db, asset_statement(db, query), query.page, query.page_size)


@router.post("", response_model=AssetOutput, status_code=201)
def add_asset(data: AssetCreate, db: Database, user: Admin) -> AssetUnit:
    return create_asset(db, data.model_dump(), user)


@router.get("/{asset_id}", response_model=AssetOutput)
def detail(asset_id: uuid.UUID, db: Database, user: CurrentUser) -> AssetUnit:
    return get_asset(db, asset_id)


@router.patch("/{asset_id}", response_model=AssetOutput)
def patch(asset_id: uuid.UUID, data: AssetPatch, db: Database, user: Admin) -> AssetUnit:
    return update_asset(
        db, asset_id, data.version, data.model_dump(exclude_unset=True, exclude={"version"}), user
    )


@router.post("/{asset_id}/archive", response_model=AssetOutput)
def archive(asset_id: uuid.UUID, data: AssetVersion, db: Database, user: Admin) -> AssetUnit:
    return update_asset(
        db,
        asset_id,
        data.version,
        {"lifecycle_status": LifecycleStatus.ARCHIVED},
        user,
        archive=True,
    )


@router.get("/{asset_id}/identifiers", response_model=list[IdentifierOutput])
def identifiers(asset_id: uuid.UUID, db: Database, user: CurrentUser) -> list[IdentifierOutput]:
    get_asset(db, asset_id)
    claims = db.scalars(
        select(AssetIdentifier)
        .where(
            AssetIdentifier.asset_id == asset_id,
            AssetIdentifier.deleted_at.is_(None),
        )
        .order_by(AssetIdentifier.created_at, AssetIdentifier.id)
    )
    return [identifier_output(db, claim) for claim in claims]


class EventQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=10, ge=1, le=100)


@router.get("/{asset_id}/events", response_model=Page[AssetEventOutput])
def asset_events(
    asset_id: uuid.UUID,
    db: Database,
    user: CurrentUser,
    query: Annotated[EventQuery, Query()],
) -> dict[str, Any]:
    """Read-only metadata history for the same roles allowed to read the unit."""
    get_asset(db, asset_id)
    statement = (
        select(AssetChangeEvent)
        .where(AssetChangeEvent.asset_id == asset_id)
        .order_by(
            AssetChangeEvent.recorded_at.desc(),
            AssetChangeEvent.after_json["asset"]["version"].as_integer().desc(),
            AssetChangeEvent.id.desc(),
        )
    )
    return list_records(db, statement, query.page, query.page_size)


@router.post("/{asset_id}/identifiers", response_model=IdentifierMutation, status_code=201)
def add_identifier(
    asset_id: uuid.UUID, data: IdentifierCreate, db: Database, user: Admin
) -> IdentifierMutation:
    asset, claim = mutate_identifier(
        db, asset_id, data.asset_version, data.model_dump(exclude={"asset_version"}), user
    )
    return IdentifierMutation(identifier=identifier_output(db, claim), asset_version=asset.version)


@router.patch("/{asset_id}/identifiers/{identifier_id}", response_model=IdentifierMutation)
def patch_identifier(
    asset_id: uuid.UUID, identifier_id: uuid.UUID, data: IdentifierPatch, db: Database, user: Admin
) -> IdentifierMutation:
    asset, claim = mutate_identifier(
        db,
        asset_id,
        data.asset_version,
        data.model_dump(exclude_unset=True, exclude={"version", "asset_version"}),
        user,
        identifier_id=identifier_id,
        version=data.version,
    )
    return IdentifierMutation(identifier=identifier_output(db, claim), asset_version=asset.version)


class DeleteQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Annotated[int, Field(ge=1, le=2_147_483_647)]
    asset_version: Annotated[int, Field(ge=1, le=2_147_483_647)]


@router.delete("/{asset_id}/identifiers/{identifier_id}", response_model=IdentifierMutation)
def delete_identifier(
    asset_id: uuid.UUID,
    identifier_id: uuid.UUID,
    db: Database,
    user: Admin,
    query: Annotated[DeleteQuery, Query()],
) -> IdentifierMutation:
    asset, claim = mutate_identifier(
        db,
        asset_id,
        query.asset_version,
        {},
        user,
        identifier_id=identifier_id,
        version=query.version,
        remove=True,
    )
    return IdentifierMutation(identifier=identifier_output(db, claim), asset_version=asset.version)
