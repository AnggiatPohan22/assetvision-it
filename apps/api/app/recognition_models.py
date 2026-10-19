"""Immutable published index generations and CAS head, separate from asset master data."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EmbeddingIndex(Base):
    __tablename__ = "embedding_indexes"
    __table_args__ = (
        CheckConstraint(
            "reference_count >= 0 AND reference_count <= 2000", name="ck_embedding_indexes_count"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    encoder_spec: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    reference_fingerprint: Mapped[str] = mapped_column(String(64))
    reference_count: Mapped[int] = mapped_column(Integer)
    calibration: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImageEmbedding(Base):
    __tablename__ = "image_embeddings"
    __table_args__ = (
        UniqueConstraint("index_id", "reference_snapshot_id", name="uq_image_embeddings_reference"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    index_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("embedding_indexes.id", ondelete="RESTRICT"), index=True
    )
    reference_image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("device_reference_images.id", ondelete="SET NULL")
    )
    reference_snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    device_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_models.id", ondelete="RESTRICT")
    )
    source_sha256: Mapped[str] = mapped_column(String(64))
    vector_data: Mapped[list[float]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmbeddingIndexState(Base):
    __tablename__ = "embedding_index_state"
    __table_args__ = (
        CheckConstraint("id = 1 AND version > 0", name="ck_embedding_index_state_singleton"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_index_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("embedding_indexes.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    __mapper_args__ = {"version_id_col": version}
