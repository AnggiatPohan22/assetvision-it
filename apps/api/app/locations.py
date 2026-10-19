"""Location definitions only; authoritative asset placement is a later task."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.catalog import CatalogRecord, name_constraints
from app.db import Base


class LocationKind(enum.StrEnum):
    SITE = "SITE"
    BUILDING = "BUILDING"
    FLOOR = "FLOOR"
    ROOM = "ROOM"
    AREA = "AREA"
    SPOT = "SPOT"


class Location(CatalogRecord, Base):
    __tablename__ = "locations"
    __table_args__ = (
        *name_constraints("name", "locations"),
        CheckConstraint("version > 0", name="ck_locations_version"),
        CheckConstraint("parent_id IS NULL OR parent_id != id", name="ck_locations_parent"),
        CheckConstraint(
            "length(code) BETWEEN 1 AND 50 AND code = lower(trim(code))",
            name="ck_locations_code",
        ),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL "
            "AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
            name="ck_locations_coordinates",
        ),
        CheckConstraint(
            "gps_accuracy_m IS NULL OR (latitude IS NOT NULL "
            "AND gps_accuracy_m >= 0 AND gps_accuracy_m <= 10000000)",
            name="ck_locations_accuracy",
        ),
        CheckConstraint(
            "gps_recorded_at IS NULL OR latitude IS NOT NULL", name="ck_locations_gps_time"
        ),
        Index(
            "uq_locations_root_code",
            "code",
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
            sqlite_where=text("parent_id IS NULL"),
        ),
        Index(
            "uq_locations_parent_code",
            "parent_id",
            "code",
            unique=True,
            postgresql_where=text("parent_id IS NOT NULL"),
            sqlite_where=text("parent_id IS NOT NULL"),
        ),
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[LocationKind] = mapped_column(
        Enum(LocationKind, native_enum=False, create_constraint=True, name="location_kind")
    )
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    gps_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
