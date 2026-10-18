"""Durable CSV commit receipts; existing domain data is unchanged."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_asset_imports"
down_revision = "0004_asset_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_import_batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(request_sha256) = 64", name="ck_import_digest"),
    )
    op.create_index("ix_asset_import_batches_actor_id", "asset_import_batches", ["actor_id"])


def downgrade() -> None:
    # Removes retry receipts/staged hints only; never deletes assets or their audit history.
    op.drop_table("asset_import_batches")
