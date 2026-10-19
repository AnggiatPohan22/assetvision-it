"""Read-only chronological projection over existing immutable event sources."""

import enum
import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, literal, select, union_all
from sqlalchemy.orm import Session

from app.asset_locations import AssetLocationEvent
from app.asset_service import get_asset
from app.assets import AssetChangeEvent
from app.catalog_schemas import Input


class TimelineSource(enum.StrEnum):
    LOCATION = "LOCATION"
    METADATA = "METADATA"


class TimelineQuery(Input):
    source: TimelineSource | None = None
    event_type: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=20, ge=1, le=100)


class TimelineEventOutput(BaseModel):
    id: uuid.UUID
    source: TimelineSource
    asset_id: uuid.UUID
    actor_id: uuid.UUID
    event_type: str
    occurred_at: datetime
    recorded_at: datetime
    correlation_id: uuid.UUID | None
    payload_json: dict[str, Any]


def timeline(db: Session, asset_id: uuid.UUID, query: TimelineQuery) -> dict[str, Any]:
    get_asset(db, asset_id)
    event_rows = union_all(
        select(
            AssetLocationEvent.id.label("id"),
            literal("LOCATION").label("source"),
            AssetLocationEvent.event_type.label("event_type"),
            AssetLocationEvent.occurred_at.label("occurred_at"),
            AssetLocationEvent.recorded_at.label("recorded_at"),
        ).where(AssetLocationEvent.asset_id == asset_id),
        select(
            AssetChangeEvent.id.label("id"),
            literal("METADATA").label("source"),
            cast(AssetChangeEvent.event_type, String).label("event_type"),
            AssetChangeEvent.recorded_at.label("occurred_at"),
            AssetChangeEvent.recorded_at.label("recorded_at"),
        ).where(AssetChangeEvent.asset_id == asset_id),
    ).subquery()
    statement = select(event_rows)
    if query.source is not None:
        statement = statement.where(event_rows.c.source == query.source.value)
    if query.event_type is not None:
        statement = statement.where(event_rows.c.event_type == query.event_type)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = (
        db.execute(
            statement.order_by(
                event_rows.c.occurred_at.desc(),
                event_rows.c.recorded_at.desc(),
                event_rows.c.source.desc(),
                event_rows.c.id.desc(),
            )
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        .mappings()
        .all()
    )
    location_ids = [r["id"] for r in rows if r["source"] == "LOCATION"]
    metadata_ids = [r["id"] for r in rows if r["source"] == "METADATA"]
    locations = (
        {
            e.id: e
            for e in db.scalars(
                select(AssetLocationEvent).where(AssetLocationEvent.id.in_(location_ids))
            )
        }
        if location_ids
        else {}
    )
    metadata = (
        {
            e.id: e
            for e in db.scalars(
                select(AssetChangeEvent).where(AssetChangeEvent.id.in_(metadata_ids))
            )
        }
        if metadata_ids
        else {}
    )
    items = []
    for row in rows:
        event = locations[row["id"]] if row["source"] == "LOCATION" else metadata[row["id"]]
        payload = (
            event.payload_json
            if row["source"] == "LOCATION"
            else {"before_json": event.before_json, "after_json": event.after_json}
        )
        items.append(
            TimelineEventOutput(
                id=event.id,
                source=row["source"],
                asset_id=event.asset_id,
                actor_id=event.actor_id,
                event_type=row["event_type"],
                occurred_at=row["occurred_at"],
                recorded_at=row["recorded_at"],
                correlation_id=event.correlation_id if row["source"] == "LOCATION" else None,
                payload_json=payload,
            )
        )
    return {
        "items": items,
        "total": total,
        "page": query.page,
        "page_size": query.page_size,
        "total_pages": (total + query.page_size - 1) // query.page_size,
    }
