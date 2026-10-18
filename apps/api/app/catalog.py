"""Catalog definitions only: a device model is never a physical asset unit."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, validates

from app.db import Base


class Environment(enum.StrEnum):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    BOTH = "both"


def canonical_name(value: str) -> str:
    """Store a display name with one space between words, preserving case."""
    return " ".join(value.split())


def name_constraints(column: str, prefix: str) -> tuple[CheckConstraint, ...]:
    # Core SQL writers must supply canonical names too; computed keys cannot be forged.
    return (
        CheckConstraint(f"length({column}) > 0", name=f"ck_{prefix}_name_nonempty"),
        CheckConstraint(
            f"{column} = trim({column}) AND {column} NOT LIKE '%  %'"
            f" AND {column} NOT LIKE '%\t%' AND {column} NOT LIKE '%\n%'"
            f" AND {column} NOT LIKE '%\r%'",
            name=f"ck_{prefix}_name_canonical",
        ),
    )


class CatalogRecord:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}


class DeviceCategory(CatalogRecord, Base):
    __tablename__ = "device_categories"
    __table_args__ = (
        *name_constraints("name", "device_categories"),
        CheckConstraint(
            "length(code) > 0 AND code = lower(trim(code)) AND code NOT LIKE '% %'",
            name="ck_device_categories_code",
        ),
        CheckConstraint("version > 0", name="ck_device_categories_version"),
    )
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    @validates("name")
    def normalize_name(self, key: str, value: str) -> str:
        return canonical_name(value)

    @validates("code")
    def normalize_code(self, key: str, value: str) -> str:
        return value.strip().lower()


class Manufacturer(CatalogRecord, Base):
    __tablename__ = "manufacturers"
    __table_args__ = (
        *name_constraints("name", "manufacturers"),
        CheckConstraint("version > 0", name="ck_manufacturers_version"),
    )
    name: Mapped[str] = mapped_column(String(150))
    normalized_name: Mapped[str] = mapped_column(
        String(150), Computed("lower(trim(name))", persisted=True), unique=True
    )
    website: Mapped[str | None] = mapped_column(String(2048))

    @validates("name")
    def normalize_name(self, key: str, value: str) -> str:
        return canonical_name(value)


class DeviceModel(CatalogRecord, Base):
    __tablename__ = "device_models"
    __table_args__ = (
        UniqueConstraint(
            "manufacturer_id", "normalized_model_name", name="uq_device_models_manufacturer_name"
        ),
        *name_constraints("model_name", "device_models"),
        CheckConstraint("version > 0", name="ck_device_models_version"),
    )
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manufacturers.id"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("device_categories.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(200))
    normalized_model_name: Mapped[str] = mapped_column(
        String(200), Computed("lower(trim(model_name))", persisted=True), index=True
    )
    aliases: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    description: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[Environment] = mapped_column(
        Enum(
            Environment,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            name="device_environment",
        )
    )
    specs: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=dict
    )

    @validates("model_name")
    def normalize_name(self, key: str, value: str) -> str:
        return canonical_name(value)


class DeviceReferenceImage(Base):
    __tablename__ = "device_reference_images"
    __table_args__ = (
        CheckConstraint("byte_size > 0", name="ck_device_reference_images_byte_size"),
        CheckConstraint("length(sha256) = 64", name="ck_device_reference_images_sha256"),
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_device_reference_images_mime_type",
        ),
        CheckConstraint(
            "length(storage_key) > 0 AND storage_key NOT LIKE '/%'"
            " AND storage_key NOT LIKE '%..%' AND storage_key NOT LIKE '%:%'"
            " AND replace(storage_key, '\\', '') = storage_key",
            name="ck_device_reference_images_storage_key",
        ),
        Index(
            "uq_device_reference_images_primary",
            "device_model_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("device_models.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(50))
    byte_size: Mapped[int] = mapped_column(Integer)
    angle: Mapped[str | None] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StorageCleanupJob(Base):
    """Durable cleanup intent for an unattached upload or deleted reference file."""

    __tablename__ = "storage_cleanup_jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
