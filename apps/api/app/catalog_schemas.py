"""Bounded request/response contracts for the device catalog."""

import json
import math
import re
import uuid
from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.catalog import Environment, canonical_name


def clean_text(value: str) -> str:
    if any(
        (ord(char) < 32 and char not in "\t\n\r") or 0xD800 <= ord(char) <= 0xDFFF for char in value
    ):
        raise ValueError("Control characters are not allowed")
    return value


def normalize_name(value: Any) -> Any:
    return canonical_name(clean_text(value)) if isinstance(value, str) else value


Name100 = Annotated[
    str, BeforeValidator(normalize_name), StringConstraints(min_length=1, max_length=100)
]
Name150 = Annotated[
    str, BeforeValidator(normalize_name), StringConstraints(min_length=1, max_length=150)
]
Name200 = Annotated[
    str, BeforeValidator(normalize_name), StringConstraints(min_length=1, max_length=200)
]
Description = Annotated[str, StringConstraints(max_length=4000), AfterValidator(clean_text)]
Code = Annotated[
    str,
    BeforeValidator(lambda value: value.strip().lower() if isinstance(value, str) else value),
    StringConstraints(min_length=1, max_length=50, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
]
Version = Annotated[StrictInt, Field(ge=1)]
Scalar = Annotated[str, StringConstraints(max_length=500), AfterValidator(clean_text)] | (
    StrictBool | StrictInt | StrictFloat | None
)
Specs = Annotated[
    dict[str, Scalar | Annotated[list[Scalar], Field(max_length=20)]], Field(max_length=32)
]
Aliases = Annotated[list[Name200], Field(max_length=20)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator("website", check_fields=False)
    @classmethod
    def valid_website(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = HttpUrl(value)
            if parsed.username or parsed.password:
                raise ValueError("Website must not contain credentials")
            result = str(parsed)
            if len(result) > 2048:
                raise ValueError("Website must not exceed 2048 characters")
            return result
        return value

    @field_validator("aliases", check_fields=False)
    @classmethod
    def unique_aliases(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len({name.lower() for name in value}) != len(value):
            raise ValueError("Aliases must be unique ignoring case and whitespace")
        return value

    @field_validator("specs", check_fields=False)
    @classmethod
    def bounded_specs(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            for key, item in value.items():
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key):
                    raise ValueError(
                        "Spec keys must be 1-64 letters, digits, dots, underscores or dashes"
                    )
                for scalar in item if isinstance(item, list) else [item]:
                    if isinstance(scalar, (int, float)) and (
                        abs(scalar) > 10**12
                        or (isinstance(scalar, float) and not math.isfinite(scalar))
                    ):
                        raise ValueError("Spec numbers must be finite and within +/- 1e12")
            if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 8192:
                raise ValueError("Specs must not exceed 8192 UTF-8 bytes")
        return value


class CategoryCreate(Input):
    code: Code
    name: Name100
    description: Description | None = None
    is_active: StrictBool = True


class ManufacturerCreate(Input):
    name: Name150
    website: Annotated[str, Field(max_length=2048)] | None = None
    is_active: StrictBool = True


class ModelCreate(Input):
    manufacturer_id: uuid.UUID
    category_id: uuid.UUID
    model_name: Name200
    aliases: Aliases = Field(default_factory=list)
    description: Description | None = None
    environment: Environment
    specs: Specs = Field(default_factory=dict)
    is_active: StrictBool = True


class Patch(Input):
    version: Version
    nullable: ClassVar[set[str]] = {"description", "website"}

    @model_validator(mode="before")
    @classmethod
    def require_changes(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if not (value.keys() - {"version"}):
                raise ValueError("Provide at least one field to update")
            if any(item is None and key not in cls.nullable for key, item in value.items()):
                raise ValueError("Only description and website may be null")
        return value


class CategoryPatch(Patch):
    code: Code | None = None
    name: Name100 | None = None
    description: Description | None = None
    is_active: StrictBool | None = None


class ManufacturerPatch(Patch):
    name: Name150 | None = None
    website: Annotated[str, Field(max_length=2048)] | None = None
    is_active: StrictBool | None = None


class ModelPatch(Patch):
    manufacturer_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    model_name: Name200 | None = None
    aliases: Aliases | None = None
    description: Description | None = None
    environment: Environment | None = None
    specs: Specs | None = None
    is_active: StrictBool | None = None


class ArchiveInput(Input):
    version: Version


class RecordOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None


class CategoryOutput(RecordOutput):
    code: str
    name: str
    description: str | None


class ManufacturerOutput(RecordOutput):
    name: str
    website: str | None


class ModelOutput(RecordOutput):
    manufacturer_id: uuid.UUID
    category_id: uuid.UUID
    model_name: str
    aliases: list[str]
    description: str | None
    environment: Environment
    specs: dict[str, Any]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class ValidationIssue(BaseModel):
    loc: list[str | int]
    type: str
    msg: str


class ErrorOutput(BaseModel):
    detail: str | list[ValidationIssue]
