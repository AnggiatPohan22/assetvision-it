"""Physical units and identity claims; no automatic asset seed."""

import enum
import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, validates

from app.db import Base


class LifecycleStatus(enum.StrEnum):
    IN_STOCK = "IN_STOCK"
    IN_USE = "IN_USE"
    MAINTENANCE = "MAINTENANCE"
    RETIRED = "RETIRED"
    ARCHIVED = "ARCHIVED"


class AssetCondition(enum.StrEnum):
    UNKNOWN = "UNKNOWN"
    GOOD = "GOOD"
    DAMAGED = "DAMAGED"
    UNUSABLE = "UNUSABLE"


class IdentifierType(enum.StrEnum):
    SERIAL_NUMBER = "SERIAL_NUMBER"
    MAC_LAN = "MAC_LAN"
    MAC_WLAN = "MAC_WLAN"
    BSSID = "BSSID"
    HOSTNAME = "HOSTNAME"
    MANAGEMENT_ID = "MANAGEMENT_ID"


class IdentifierSource(enum.StrEnum):
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"
    CONTROLLER = "CONTROLLER"


class VerificationStatus(enum.StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"


class AssetEventType(enum.StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    ARCHIVE = "ARCHIVE"
    IDENTIFIER_ADD = "IDENTIFIER_ADD"
    IDENTIFIER_UPDATE = "IDENTIFIER_UPDATE"
    IDENTIFIER_REMOVE = "IDENTIFIER_REMOVE"


def enum_column(kind: type[enum.StrEnum], name: str) -> Enum:
    return Enum(kind, native_enum=False, create_constraint=True, name=name)


class VersionedRecord:
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}


class AssetUnit(VersionedRecord, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "length(asset_code) BETWEEN 1 AND 50 AND asset_code = upper(trim(asset_code))",
            name="ck_assets_code",
        ),
        CheckConstraint("version > 0", name="ck_assets_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_code: Mapped[str] = mapped_column(String(50), unique=True)
    device_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_models.id", ondelete="RESTRICT"), index=True
    )
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        enum_column(LifecycleStatus, "asset_lifecycle_status"),
        default=LifecycleStatus.IN_STOCK,
        server_default="IN_STOCK",
        index=True,
    )
    condition: Mapped[AssetCondition] = mapped_column(
        enum_column(AssetCondition, "asset_condition"),
        default=AssetCondition.UNKNOWN,
        server_default="UNKNOWN",
    )
    notes: Mapped[str | None] = mapped_column(Text)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @validates("asset_code")
    def validate_code(self, key: str, value: str) -> str:
        # Normalize on creation; database triggers enforce immutability for every writer.
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,49}", value):
            raise ValueError(
                "Asset code must be 1-50 ASCII letters, digits, hyphens or underscores"
            )
        return value


MAC_TYPES = {IdentifierType.MAC_LAN, IdentifierType.MAC_WLAN, IdentifierType.BSSID}


def normalize_identifier(kind: IdentifierType, raw: str) -> str:
    value = raw.strip()
    if not value or len(value) > 255 or any(ord(char) < 32 for char in value):
        raise ValueError("Identifier must contain 1-255 printable characters")
    if kind in MAC_TYPES:
        if not re.fullmatch(
            r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}|"
            r"(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}|(?:[0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4})",
            value,
        ):
            raise ValueError("Invalid MAC address")
        compact = re.sub(r"[:.\-]", "", value).upper()
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))
    if kind == IdentifierType.SERIAL_NUMBER and value.upper() in {"UNKNOWN", "N/A", "NA", "-"}:
        raise ValueError("Missing serial numbers must not be represented by placeholder claims")
    # Serial and management IDs preserve case; their upstream case rules are unknown.
    return value.lower() if kind == IdentifierType.HOSTNAME else value


class AssetIdentifier(VersionedRecord, Base):
    __tablename__ = "asset_identifiers"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_asset_identifiers_version"),
        CheckConstraint(
            "length(normalized_value) BETWEEN 1 AND 255 "
            "AND normalized_value = trim(normalized_value) "
            "AND length(trim(raw_value)) BETWEEN 1 AND 255",
            name="ck_asset_identifiers_nonempty",
        ),
        CheckConstraint(
            "identifier_type != 'SERIAL_NUMBER' OR upper(normalized_value) "
            "NOT IN ('UNKNOWN', 'N/A', 'NA', '-')",
            name="ck_asset_identifiers_serial",
        ),
        Index("ix_asset_identifiers_lookup", "identifier_type", "normalized_value"),
        Index(
            "uq_asset_identifiers_active",
            "asset_id",
            "identifier_type",
            "normalized_value",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    identifier_type: Mapped[IdentifierType] = mapped_column(
        enum_column(IdentifierType, "asset_identifier_type")
    )
    normalized_value: Mapped[str] = mapped_column(String(255))
    raw_value: Mapped[str] = mapped_column(String(255))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, "asset_identifier_verification"),
        default=VerificationStatus.UNVERIFIED,
        server_default="UNVERIFIED",
    )
    source: Mapped[IdentifierSource] = mapped_column(
        enum_column(IdentifierSource, "asset_identifier_source")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@event.listens_for(AssetIdentifier, "before_insert")
@event.listens_for(AssetIdentifier, "before_update")
def canonicalize_claim(mapper: Any, connection: Any, target: AssetIdentifier) -> None:
    target.normalized_value = normalize_identifier(
        IdentifierType(target.identifier_type), target.raw_value
    )


class AssetChangeEvent(Base):
    """Snapshot payloads are supplied atomically by the asset service transaction."""

    __tablename__ = "asset_change_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[AssetEventType] = mapped_column(
        enum_column(AssetEventType, "asset_event_type")
    )
    before_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
    )
    after_json: Mapped[dict[str, Any]] = mapped_column(
        JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
