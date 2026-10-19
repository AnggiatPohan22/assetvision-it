"""Location hierarchy only; no asset placements or inferred location backfill."""

import sqlalchemy as sa
from alembic import op

revision = "0006_locations"
down_revision = "0005_asset_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("locations.id", ondelete="RESTRICT")),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "SITE",
                "BUILDING",
                "FLOOR",
                "ROOM",
                "AREA",
                "SPOT",
                native_enum=False,
                create_constraint=True,
                name="location_kind",
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("gps_accuracy_m", sa.Float()),
        sa.Column("gps_recorded_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint("length(name) > 0", name="ck_locations_name_nonempty"),
        sa.CheckConstraint(
            "name = trim(name) AND name NOT LIKE '%  %' AND name NOT LIKE '%\t%'"
            " AND name NOT LIKE '%\n%' AND name NOT LIKE '%\r%'",
            name="ck_locations_name_canonical",
        ),
        sa.CheckConstraint("version > 0", name="ck_locations_version"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id != id", name="ck_locations_parent"),
        sa.CheckConstraint(
            "length(code) BETWEEN 1 AND 50 AND code = lower(trim(code))", name="ck_locations_code"
        ),
        sa.CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL "
            "AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
            name="ck_locations_coordinates",
        ),
        sa.CheckConstraint(
            "gps_accuracy_m IS NULL OR (latitude IS NOT NULL "
            "AND gps_accuracy_m >= 0 AND gps_accuracy_m <= 10000000)",
            name="ck_locations_accuracy",
        ),
        sa.CheckConstraint(
            "gps_recorded_at IS NULL OR latitude IS NOT NULL", name="ck_locations_gps_time"
        ),
    )
    op.create_index("ix_locations_parent_id", "locations", ["parent_id"])
    for suffix, cols, condition in (
        ("root_code", ["code"], "parent_id IS NULL"),
        ("parent_code", ["parent_id", "code"], "parent_id IS NOT NULL"),
    ):
        op.create_index(
            f"uq_locations_{suffix}",
            "locations",
            cols,
            unique=True,
            postgresql_where=sa.text(condition),
            sqlite_where=sa.text(condition),
        )
    install_guards()


def install_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE OR REPLACE FUNCTION av_location_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(649237804);
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Archive locations instead' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF NEW.id IS DISTINCT FROM OLD.id THEN
                    RAISE EXCEPTION 'Location identity is immutable' USING ERRCODE = '23514';
                END IF;
            END IF;
            IF NEW.code !~ '^[a-z0-9]+(-[a-z0-9]+)*$' THEN
                RAISE EXCEPTION 'Invalid location code' USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
                WITH RECURSIVE ancestors(id, parent_id) AS (
                    SELECT id, parent_id FROM locations WHERE id = NEW.parent_id
                    UNION
                    SELECT l.id, l.parent_id FROM locations l JOIN ancestors a ON l.id = a.parent_id
                ) SELECT 1 FROM ancestors WHERE id = NEW.id
            ) THEN
                RAISE EXCEPTION 'Location hierarchy cycle' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER av_location_guard BEFORE INSERT OR UPDATE OR DELETE ON locations "
            "FOR EACH ROW EXECUTE FUNCTION av_location_guard()"
        )
    else:
        for operation in ("INSERT", "UPDATE"):
            op.execute(f"""CREATE TRIGGER av_location_{operation.lower()}
                BEFORE {operation} ON locations BEGIN
                SELECT RAISE(ABORT, 'Invalid location code') WHERE
                    NEW.code GLOB '*[^a-z0-9-]*' OR NEW.code GLOB '-*' OR
                    NEW.code GLOB '*-' OR NEW.code LIKE '%--%';
                SELECT RAISE(ABORT, 'Location hierarchy cycle') WHERE EXISTS (
                    WITH RECURSIVE ancestors(id, parent_id) AS (
                        SELECT id, parent_id FROM locations WHERE id = NEW.parent_id
                        UNION
                        SELECT l.id, l.parent_id FROM locations l
                            JOIN ancestors a ON l.id = a.parent_id
                    ) SELECT 1 FROM ancestors WHERE id = NEW.id
                ); END""")
        op.execute("""CREATE TRIGGER av_location_identity BEFORE UPDATE ON locations
            WHEN NEW.id != OLD.id
            BEGIN SELECT RAISE(ABORT, 'Location identity is immutable'); END""")
        op.execute("""CREATE TRIGGER av_location_delete BEFORE DELETE ON locations
            BEGIN SELECT RAISE(ABORT, 'Archive locations instead'); END""")


def downgrade() -> None:
    # Refuse to destroy location definitions. Empty-table downgrade remains reversible.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM locations")):
        raise RuntimeError("Cannot downgrade populated locations; preserve/export and review first")
    op.drop_table("locations")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION av_location_guard()")
