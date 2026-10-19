"""Authenticated hierarchy reads; ADMIN-only writes through existing session/CSRF."""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.routing import APIRoute
from sqlalchemy import func, or_, select

from app.catalog_schemas import ErrorOutput, Input, Page
from app.catalog_service import list_records
from app.dependencies import CurrentUser, Database, require_roles
from app.location_schemas import LocationCreate, LocationOutput, LocationPatch, LocationTree
from app.location_service import get_location, save_location
from app.locations import Location, LocationKind
from app.models import Role, User


class LocationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            if request.method in {"POST", "PATCH"}:
                if (
                    request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    != "application/json"
                ):
                    raise HTTPException(415, "Location writes require JSON")
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 16384:
                        raise HTTPException(413, "Location request exceeds 16 KiB")
                    body.extend(chunk)
                request._body = bytes(body)
            return await original(request)

        return bounded


router = APIRouter(
    prefix="/api/v1/locations",
    tags=["locations"],
    route_class=LocationRoute,
    responses={code: {"model": ErrorOutput} for code in (401, 403, 404, 409, 413, 415, 422)},
)
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


class LocationQuery(Input):
    parent_id: uuid.UUID | None = None
    roots_only: bool = False
    kind: LocationKind | None = None
    is_active: bool | None = None
    search: str = Query(default="", max_length=200)
    page: int = Query(default=1, ge=1, le=1000000)
    page_size: int = Query(default=20, ge=1, le=100)


@router.get("", response_model=Page[LocationOutput])
def locations(
    db: Database, user: CurrentUser, query: Annotated[LocationQuery, Query()]
) -> dict[str, Any]:
    if query.roots_only and query.parent_id is not None:
        raise HTTPException(422, "roots_only and parent_id are mutually exclusive")
    statement = select(Location)
    if query.roots_only:
        statement = statement.where(Location.parent_id.is_(None))
    for key in ("parent_id", "kind", "is_active"):
        value = getattr(query, key)
        if value is not None:
            statement = statement.where(getattr(Location, key) == value)
    search = " ".join(query.search.split()).lower()
    if search:
        statement = statement.where(
            or_(
                func.lower(Location.name).contains(search, autoescape=True),
                Location.code.contains(search, autoescape=True),
            )
        )
    return list_records(
        db, statement.order_by(Location.code, Location.id), query.page, query.page_size
    )


@router.get("/tree", response_model=LocationTree)
def tree(db: Database, user: CurrentUser) -> dict[str, Any]:
    # Adjacency format avoids recursive JSON depth limits and preserves archived ancestors.
    records = list(db.scalars(select(Location).order_by(Location.code, Location.id).limit(5001)))
    if len(records) > 5000:
        raise HTTPException(409, "Tree exceeds 5000 locations; use the paginated list")
    return {"items": records, "total": len(records)}


@router.post("", response_model=LocationOutput, status_code=201)
def create_location(data: LocationCreate, db: Database, user: Admin) -> Location:
    return save_location(db, user, data)


@router.get("/{location_id}", response_model=LocationOutput)
def detail(location_id: uuid.UUID, db: Database, user: CurrentUser) -> Location:
    return get_location(db, location_id)


@router.patch("/{location_id}", response_model=LocationOutput)
def patch_location(
    location_id: uuid.UUID, data: LocationPatch, db: Database, user: Admin
) -> Location:
    return save_location(db, user, data, location_id)
