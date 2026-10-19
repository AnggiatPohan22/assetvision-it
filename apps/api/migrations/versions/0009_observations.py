"""Add retained observations without changing existing business data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_observations"
down_revision = "0008_asset_movements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "location_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="RESTRICT")),
        sa.Column(
            "observed_location_id",
            sa.Uuid(),
            sa.ForeignKey("locations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "observed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_note", sa.String(2000), nullable=False),
        sa.Column(
            "official_location_id_at_recording",
            sa.Uuid(),
            sa.ForeignKey("locations.id", ondelete="RESTRICT"),
        ),
        sa.Column("asset_version_at_recording", sa.Integer()),
        sa.Column(
            "comparison_status",
            sa.Enum(
                "UNLINKED",
                "UNPLACED",
                "MATCH",
                "LOCATION_CONFLICT",
                native_enum=False,
                create_constraint=True,
                name="observation_comparison",
            ),
            nullable=False,
        ),
        sa.Column("snapshot_json", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column(
            "review_status",
            sa.Enum(
                "PENDING",
                "ACKNOWLEDGED",
                "DISMISSED",
                native_enum=False,
                create_constraint=True,
                name="observation_review_status",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.String(2000)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint(
            "version > 0",
            name="ck_location_observations_version",
        ),
        sa.CheckConstraint(
            "length(evidence_note) BETWEEN 1 AND 2000 AND evidence_note = trim(evidence_note)",
            name="ck_location_observations_note",
        ),
        sa.CheckConstraint(
            "(asset_id IS NULL AND asset_version_at_recording IS NULL AND "
            "official_location_id_at_recording IS NULL AND comparison_status = "
            "'UNLINKED') OR (asset_id IS NOT NULL AND asset_version_at_recording IS NOT"
            " NULL AND asset_version_at_recording > 0 AND comparison_status != "
            "'UNLINKED')",
            name="ck_location_observations_asset",
        ),
        sa.CheckConstraint(
            "comparison_status = 'UNLINKED' OR (comparison_status = 'UNPLACED' AND "
            "official_location_id_at_recording IS NULL) OR (comparison_status = 'MATCH'"
            " AND official_location_id_at_recording IS NOT NULL AND "
            "official_location_id_at_recording = observed_location_id) OR "
            "(comparison_status = 'LOCATION_CONFLICT' AND "
            "official_location_id_at_recording IS NOT NULL AND "
            "official_location_id_at_recording != observed_location_id)",
            name="ck_location_observations_comparison",
        ),
        sa.CheckConstraint(
            "(review_status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL"
            " AND review_reason IS NULL) OR (review_status != 'PENDING' AND reviewed_by"
            " IS NOT NULL AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL)",
            name="ck_location_observations_review",
        ),
        sa.CheckConstraint(
            "review_reason IS NULL OR (length(review_reason) BETWEEN 1 AND 2000 AND "
            "review_reason = trim(review_reason))",
            name="ck_location_observations_review_reason",
        ),
    )
    op.create_index(
        "ix_location_observations_latest",
        "location_observations",
        ["asset_id", "observed_at", "recorded_at", "id"],
    )
    for column in ("observed_at", "review_status"):
        op.create_index("ix_location_observations_" + column, "location_observations", [column])
    install_guards()


def install_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE OR REPLACE FUNCTION av_observation_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Observation evidence is retained' USING ERRCODE = '23514';
            ELSIF TG_OP = 'INSERT' THEN
                IF NEW.review_status != 'PENDING' OR NEW.version != 1 THEN
                    RAISE EXCEPTION 'Observation starts pending' USING ERRCODE = '23514';
                END IF;
            ELSE
                IF NEW.id IS DISTINCT FROM OLD.id
                    OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
                    OR NEW.observed_location_id IS DISTINCT FROM OLD.observed_location_id
                    OR NEW.observed_by IS DISTINCT FROM OLD.observed_by
                    OR NEW.observed_at IS DISTINCT FROM OLD.observed_at
                    OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
                    OR NEW.evidence_note IS DISTINCT FROM OLD.evidence_note
                    OR NEW.official_location_id_at_recording IS DISTINCT FROM
                        OLD.official_location_id_at_recording
                    OR NEW.asset_version_at_recording IS DISTINCT FROM
                        OLD.asset_version_at_recording
                    OR NEW.comparison_status IS DISTINCT FROM OLD.comparison_status
                    OR NEW.snapshot_json IS DISTINCT FROM OLD.snapshot_json THEN
                    RAISE EXCEPTION 'Observation evidence is immutable' USING ERRCODE = '23514';
                END IF;
                IF OLD.review_status != 'PENDING'
                   OR NEW.review_status NOT IN ('ACKNOWLEDGED','DISMISSED')
                   OR NEW.version != OLD.version + 1 THEN
                    RAISE EXCEPTION 'Invalid observation review' USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER av_observation_guard BEFORE INSERT OR UPDATE OR DELETE "
            "ON location_observations FOR EACH ROW EXECUTE FUNCTION av_observation_guard()"
        )
    else:
        op.execute("""CREATE TRIGGER av_observation_insert BEFORE INSERT ON location_observations
            WHEN NEW.review_status != 'PENDING' OR NEW.version != 1
            BEGIN SELECT RAISE(ABORT, 'Observation starts pending'); END""")
        op.execute("""CREATE TRIGGER av_observation_update BEFORE UPDATE ON location_observations
            WHEN NEW.id IS NOT OLD.id
                 OR NEW.asset_id IS NOT OLD.asset_id
                 OR NEW.observed_location_id IS NOT OLD.observed_location_id
                 OR NEW.observed_by IS NOT OLD.observed_by
                 OR NEW.observed_at IS NOT OLD.observed_at
                 OR NEW.recorded_at IS NOT OLD.recorded_at
                 OR NEW.evidence_note IS NOT OLD.evidence_note
                 OR NEW.official_location_id_at_recording IS NOT
                    OLD.official_location_id_at_recording
                 OR NEW.asset_version_at_recording IS NOT
                    OLD.asset_version_at_recording
                 OR NEW.comparison_status IS NOT OLD.comparison_status
                 OR NEW.snapshot_json IS NOT OLD.snapshot_json
            OR OLD.review_status != 'PENDING'
            OR NEW.review_status NOT IN ('ACKNOWLEDGED','DISMISSED')
            OR NEW.version != OLD.version + 1
            BEGIN SELECT RAISE(ABORT, 'Invalid observation rewrite or review'); END""")
        op.execute("""CREATE TRIGGER av_observation_delete BEFORE DELETE ON location_observations
            BEGIN SELECT RAISE(ABORT, 'Observation evidence is retained'); END""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM location_observations")):
        raise RuntimeError("Cannot downgrade populated observations; preserve and review first")
    op.drop_table("location_observations")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION av_observation_guard()")
