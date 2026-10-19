"""Nullable authoritative location and retained initial placement evidence; no backfill."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_asset_location"
down_revision = "0006_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # SQLite supports nullable REFERENCES on ADD COLUMN without rebuilding referenced assets.
        op.execute(
            "ALTER TABLE assets ADD COLUMN current_location_id CHAR(32) "
            "CONSTRAINT fk_assets_current_location REFERENCES locations(id)"
        )
    else:
        op.add_column("assets", sa.Column("current_location_id", sa.Uuid()))
        op.create_foreign_key(
            "fk_assets_current_location",
            "assets",
            "locations",
            ["current_location_id"],
            ["id"],
        )
    op.add_column("assets", sa.Column("location_verified_at", sa.DateTime(timezone=True)))
    op.create_index("ix_assets_current_location_id", "assets", ["current_location_id"])
    op.create_table(
        "asset_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("payload_json", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False, unique=True),
    )
    for col in ("asset_id", "recorded_at"):
        op.create_index("ix_asset_events_" + col, "asset_events", [col])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER av_asset_events_guard BEFORE UPDATE OR DELETE ON asset_events "
            "FOR EACH ROW EXECUTE FUNCTION av_history_guard()"
        )
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER av_asset_events_{operation.lower()} BEFORE {operation} "
                "ON asset_events BEGIN SELECT RAISE(ABORT, 'History is retained'); END"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM asset_events")) or bind.scalar(
        sa.text(
            "SELECT count(*) FROM assets WHERE current_location_id IS NOT NULL "
            "OR location_verified_at IS NOT NULL"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade populated asset location data; preserve and review first"
        )
    op.drop_table("asset_events")
    op.drop_index("ix_assets_current_location_id", table_name="assets")
    if bind.dialect.name == "postgresql":
        op.drop_constraint("fk_assets_current_location", "assets", type_="foreignkey")
    op.drop_column("assets", "current_location_id")
    op.drop_column("assets", "location_verified_at")
