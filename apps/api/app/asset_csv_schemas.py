"""Bounded CSV request and row reports. Preview has no persistent import record."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, field_validator

from app.catalog_schemas import Input

MAX_CSV_BYTES = 256 * 1024
MAX_REQUEST_BYTES = 1024 * 1024
MAX_ROWS = 500


class CsvInput(Input):
    csv_text: Annotated[str, Field(min_length=1, max_length=MAX_CSV_BYTES)]

    @field_validator("csv_text")
    @classmethod
    def bounded_utf8(cls, value: str) -> str:
        try:
            if len(value.encode("utf-8")) > MAX_CSV_BYTES:
                raise ValueError("CSV exceeds 256 KiB")
        except UnicodeEncodeError:
            raise ValueError("CSV must be valid UTF-8") from None
        return value


class CsvCommit(CsvInput):
    idempotency_key: uuid.UUID
    allow_identifier_collisions: StrictBool = False


class CsvCollision(BaseModel):
    identifier_type: str
    normalized_value: str
    asset_ids: list[uuid.UUID] = Field(default_factory=list)
    csv_rows: list[int] = Field(default_factory=list)


class CsvRowResult(BaseModel):
    row: int
    asset_code: str
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    collisions: list[CsvCollision] = Field(default_factory=list)
    location_hint: str | None = None
    asset_id: uuid.UUID | None = None
    version: int | None = None


class CsvPreview(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    has_collisions: bool
    rows: list[CsvRowResult]


class CsvCommitResult(BaseModel):
    import_id: uuid.UUID
    status: Literal["COMMITTED", "REJECTED"]
    created_count: int
    failed_count: int
    rows: list[CsvRowResult]
    errors: list[str] = Field(default_factory=list)
