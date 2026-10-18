"""Durable filesystem cleanup intents; existing catalog data is unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0003_image_cleanup"
down_revision = "0002_device_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_cleanup_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("storage_key", sa.String(255), unique=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_storage_cleanup_jobs_created_at", "storage_cleanup_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_table("storage_cleanup_jobs")
