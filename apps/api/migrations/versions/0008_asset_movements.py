"""Add movements without changing existing assets."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_asset_movements"
down_revision = "0007_asset_location"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_movements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "from_location_id", sa.Uuid(), sa.ForeignKey("locations.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "to_location_id",
            sa.Uuid(),
            sa.ForeignKey("locations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "APPROVED",
                "REJECTED",
                "CANCELLED",
                native_enum=False,
                create_constraint=True,
                name="movement_status",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column(
            "requested_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_asset_version", sa.Integer(), nullable=False),
        sa.Column(
            "request_snapshot_json", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.String(2000)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint(
            "version > 0 AND expected_asset_version > 0 AND expected_asset_version < 2147483647",
            name="ck_asset_movements_version",
        ),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 2000 AND reason = trim(reason)",
            name="ck_asset_movements_reason",
        ),
        sa.CheckConstraint(
            "from_location_id IS NULL OR from_location_id != to_location_id",
            name="ck_asset_movements_destination",
        ),
        sa.CheckConstraint(
            "review_reason IS NULL OR (length(review_reason) BETWEEN 1 AND 2000 AND "
            "review_reason = trim(review_reason))",
            name="ck_asset_movements_review_reason",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL AND "
            "review_reason IS NULL) OR (status != 'PENDING' AND reviewed_by IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL)",
            name="ck_asset_movements_review",
        ),
        sa.CheckConstraint(
            "(status = 'APPROVED' AND approved_at IS NOT NULL AND effective_at IS NOT "
            "NULL AND approved_at = reviewed_at AND effective_at = approved_at) OR "
            "(status != 'APPROVED' AND approved_at IS NULL AND effective_at IS NULL)",
            name="ck_asset_movements_approval",
        ),
    )
    for column in ("asset_id", "status", "requested_at"):
        op.create_index("ix_asset_movements_" + column, "asset_movements", [column])
    install_guards()


def install_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE OR REPLACE FUNCTION av_movement_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Movement history is retained' USING ERRCODE = '23514';
            ELSIF TG_OP = 'INSERT' THEN
                IF NEW.status != 'PENDING' OR NEW.version != 1 THEN
                    RAISE EXCEPTION 'Movement must start pending' USING ERRCODE = '23514';
                END IF;
            ELSE
                IF NEW.id IS DISTINCT FROM OLD.id
                    OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
                    OR NEW.from_location_id IS DISTINCT FROM OLD.from_location_id
                    OR NEW.to_location_id IS DISTINCT FROM OLD.to_location_id
                    OR NEW.reason IS DISTINCT FROM OLD.reason
                    OR NEW.requested_by IS DISTINCT FROM OLD.requested_by
                    OR NEW.requested_at IS DISTINCT FROM OLD.requested_at
                    OR NEW.expected_asset_version IS DISTINCT FROM OLD.expected_asset_version
                    OR NEW.request_snapshot_json IS DISTINCT FROM OLD.request_snapshot_json THEN
                    RAISE EXCEPTION 'Movement request is immutable' USING ERRCODE = '23514';
                END IF;
                IF OLD.status != 'PENDING' OR NEW.status NOT IN ('APPROVED','REJECTED','CANCELLED')
                   OR NEW.version != OLD.version + 1 THEN
                    RAISE EXCEPTION 'Invalid movement transition' USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER av_movement_guard BEFORE INSERT OR UPDATE OR DELETE ON "
            "asset_movements FOR EACH ROW EXECUTE FUNCTION av_movement_guard()"
        )
    else:
        op.execute("""CREATE TRIGGER av_movement_insert BEFORE INSERT ON asset_movements
            WHEN NEW.status != 'PENDING' OR NEW.version != 1
            BEGIN SELECT RAISE(ABORT, 'Movement must start pending'); END""")
        op.execute("""CREATE TRIGGER av_movement_update BEFORE UPDATE ON asset_movements
            WHEN NEW.id IS NOT OLD.id
                 OR NEW.asset_id IS NOT OLD.asset_id
                 OR NEW.from_location_id IS NOT OLD.from_location_id
                 OR NEW.to_location_id IS NOT OLD.to_location_id
                 OR NEW.reason IS NOT OLD.reason
                 OR NEW.requested_by IS NOT OLD.requested_by
                 OR NEW.requested_at IS NOT OLD.requested_at
                 OR NEW.expected_asset_version IS NOT OLD.expected_asset_version
                 OR NEW.request_snapshot_json IS NOT OLD.request_snapshot_json
            OR OLD.status != 'PENDING' OR NEW.status NOT IN ('APPROVED','REJECTED','CANCELLED')
            OR NEW.version != OLD.version + 1
            BEGIN SELECT RAISE(ABORT, 'Invalid movement rewrite or transition'); END""")
        op.execute("""CREATE TRIGGER av_movement_delete BEFORE DELETE ON asset_movements
            BEGIN SELECT RAISE(ABORT, 'Movement history is retained'); END""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM asset_movements")):
        raise RuntimeError("Cannot downgrade populated movements; preserve and review first")
    op.drop_table("asset_movements")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION av_movement_guard()")
