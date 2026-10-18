"""Authenticated catalog CRUD. File/reference-image routes belong to Task 1A-03."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from sqlalchemy import func, or_, select

from app.catalog import DeviceCategory, DeviceModel, Environment, Manufacturer, canonical_name
from app.catalog_schemas import (
    ArchiveInput,
    CategoryCreate,
    CategoryOutput,
    CategoryPatch,
    ErrorOutput,
    ManufacturerCreate,
    ManufacturerOutput,
    ManufacturerPatch,
    ModelCreate,
    ModelOutput,
    ModelPatch,
    Page,
    normalize_name,
)
from app.catalog_service import (
    archive_record,
    create_record,
    get_record,
    list_records,
    update_record,
)
from app.dependencies import CurrentUser, Database, require_roles
from app.models import Role, User

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
router = APIRouter(
    prefix="/api/v1",
    tags=["Device catalog"],
    responses={
        code: {"model": ErrorOutput, "description": description}
        for code, description in {
            401: "Authentication required",
            403: "Role, Origin, or session CSRF rejected",
            404: "Catalog record not found",
            409: "Duplicate, inactive reference, or concurrent change",
            422: "Invalid input or unknown catalog reference",
        }.items()
    },
)


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: Annotated[str, BeforeValidator(normalize_name)] = Field(default="", max_length=200)
    is_active: bool | None = None
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=25, ge=1, le=100)


class ModelQuery(ListQuery):
    category_id: uuid.UUID | None = None
    manufacturer_id: uuid.UUID | None = None
    environment: Environment | None = None


@router.get("/device-categories", response_model=Page[CategoryOutput])
def categories(
    db: Database,
    user: CurrentUser,
    query: Annotated[ListQuery, Query()],
) -> dict[str, Any]:
    statement = select(DeviceCategory)
    if query.is_active is not None:
        statement = statement.where(DeviceCategory.is_active == query.is_active)
    search = canonical_name(query.search).lower()
    if search:
        statement = statement.where(
            or_(
                func.lower(DeviceCategory.name).contains(search, autoescape=True),
                DeviceCategory.code.contains(search, autoescape=True),
            )
        )
    statement = statement.order_by(func.lower(DeviceCategory.name), DeviceCategory.id)
    return list_records(db, statement, query.page, query.page_size)


@router.post("/device-categories", response_model=CategoryOutput, status_code=201)
def create_category(data: CategoryCreate, db: Database, user: Admin) -> DeviceCategory:
    return create_record(db, DeviceCategory, data.model_dump(), user)


@router.get("/device-categories/{record_id}", response_model=CategoryOutput)
def category_detail(record_id: uuid.UUID, db: Database, user: CurrentUser) -> DeviceCategory:
    return get_record(db, DeviceCategory, record_id)


@router.patch("/device-categories/{record_id}", response_model=CategoryOutput)
def patch_category(
    record_id: uuid.UUID,
    data: CategoryPatch,
    db: Database,
    user: Admin,
) -> DeviceCategory:
    return update_record(db, get_record(db, DeviceCategory, record_id), data, user)


@router.get("/manufacturers", response_model=Page[ManufacturerOutput])
def manufacturers(
    db: Database,
    user: CurrentUser,
    query: Annotated[ListQuery, Query()],
) -> dict[str, Any]:
    statement = select(Manufacturer)
    if query.is_active is not None:
        statement = statement.where(Manufacturer.is_active == query.is_active)
    search = canonical_name(query.search).lower()
    if search:
        statement = statement.where(Manufacturer.normalized_name.contains(search, autoescape=True))
    statement = statement.order_by(Manufacturer.normalized_name, Manufacturer.id)
    return list_records(db, statement, query.page, query.page_size)


@router.post("/manufacturers", response_model=ManufacturerOutput, status_code=201)
def create_manufacturer(data: ManufacturerCreate, db: Database, user: Admin) -> Manufacturer:
    return create_record(db, Manufacturer, data.model_dump(), user)


@router.get("/manufacturers/{record_id}", response_model=ManufacturerOutput)
def manufacturer_detail(record_id: uuid.UUID, db: Database, user: CurrentUser) -> Manufacturer:
    return get_record(db, Manufacturer, record_id)


@router.patch("/manufacturers/{record_id}", response_model=ManufacturerOutput)
def patch_manufacturer(
    record_id: uuid.UUID,
    data: ManufacturerPatch,
    db: Database,
    user: Admin,
) -> Manufacturer:
    return update_record(db, get_record(db, Manufacturer, record_id), data, user)


@router.get("/device-models", response_model=Page[ModelOutput])
def models(
    db: Database,
    user: CurrentUser,
    query: Annotated[ModelQuery, Query()],
) -> dict[str, Any]:
    statement = select(DeviceModel).join(Manufacturer)
    for key in ("is_active", "category_id", "manufacturer_id", "environment"):
        value = getattr(query, key)
        if value is not None:
            statement = statement.where(getattr(DeviceModel, key) == value)
    search = canonical_name(query.search).lower()
    if search:
        alias_function = (
            func.jsonb_array_elements_text
            if db.get_bind().dialect.name == "postgresql"
            else func.json_each
        )
        aliases = alias_function(DeviceModel.aliases).table_valued("value")
        alias_match = (
            select(1)
            .select_from(aliases)
            .where(func.lower(aliases.c.value).contains(search, autoescape=True))
            .correlate(DeviceModel)
            .exists()
        )
        statement = statement.where(
            or_(
                func.lower(DeviceModel.model_name).contains(search, autoescape=True),
                Manufacturer.normalized_name.contains(search, autoescape=True),
                alias_match,
            )
        )
    statement = statement.order_by(DeviceModel.normalized_model_name, DeviceModel.id)
    return list_records(db, statement, query.page, query.page_size)


@router.post("/device-models", response_model=ModelOutput, status_code=201)
def create_model(data: ModelCreate, db: Database, user: Admin) -> DeviceModel:
    return create_record(db, DeviceModel, data.model_dump(), user)


@router.get("/device-models/{record_id}", response_model=ModelOutput)
def model_detail(record_id: uuid.UUID, db: Database, user: CurrentUser) -> DeviceModel:
    return get_record(db, DeviceModel, record_id)


@router.patch("/device-models/{record_id}", response_model=ModelOutput)
def patch_model(record_id: uuid.UUID, data: ModelPatch, db: Database, user: Admin) -> DeviceModel:
    return update_record(db, get_record(db, DeviceModel, record_id), data, user)


@router.post("/device-models/{record_id}/archive", response_model=ModelOutput)
def archive_model(
    record_id: uuid.UUID, data: ArchiveInput, db: Database, user: Admin
) -> DeviceModel:
    return archive_record(db, get_record(db, DeviceModel, record_id), data.version, user)
