"""Physical asset schema, reserved codes, identity claims and metadata audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_asset_registry"
down_revision = "0003_image_cleanup"
branch_labels = None
depends_on = None


def choice(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("asset_code", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "device_model_id",
            sa.Uuid(),
            sa.ForeignKey("device_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "lifecycle_status",
            choice(
                "asset_lifecycle_status", "IN_STOCK", "IN_USE", "MAINTENANCE", "RETIRED", "ARCHIVED"
            ),
            nullable=False,
            server_default="IN_STOCK",
        ),
        sa.Column(
            "condition",
            choice("asset_condition", "UNKNOWN", "GOOD", "DAMAGED", "UNUSABLE"),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("notes", sa.Text()),
        sa.Column("purchase_date", sa.Date()),
        sa.Column("installed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint("version > 0", name="ck_assets_version"),
        sa.CheckConstraint(
            "length(asset_code) BETWEEN 1 AND 50 AND asset_code = upper(trim(asset_code))",
            name="ck_assets_code",
        ),
    )
    for column in ("device_model_id", "lifecycle_status"):
        op.create_index(f"ix_assets_{column}", "assets", [column])
    op.create_table(
        "asset_identifiers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "identifier_type",
            choice(
                "asset_identifier_type",
                "SERIAL_NUMBER",
                "MAC_LAN",
                "MAC_WLAN",
                "BSSID",
                "HOSTNAME",
                "MANAGEMENT_ID",
            ),
            nullable=False,
        ),
        sa.Column("normalized_value", sa.String(255), nullable=False),
        sa.Column("raw_value", sa.String(255), nullable=False),
        sa.Column(
            "verification_status",
            choice("asset_identifier_verification", "UNVERIFIED", "VERIFIED", "DISPUTED"),
            nullable=False,
            server_default="UNVERIFIED",
        ),
        sa.Column(
            "source",
            choice("asset_identifier_source", "MANUAL", "IMPORT", "CONTROLLER"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint("version > 0", name="ck_asset_identifiers_version"),
        sa.CheckConstraint(
            "length(normalized_value) BETWEEN 1 AND 255 "
            "AND normalized_value = trim(normalized_value) "
            "AND length(trim(raw_value)) BETWEEN 1 AND 255",
            name="ck_asset_identifiers_nonempty",
        ),
        sa.CheckConstraint(
            "identifier_type != 'SERIAL_NUMBER' OR upper(normalized_value) "
            "NOT IN ('UNKNOWN', 'N/A', 'NA', '-')",
            name="ck_asset_identifiers_serial",
        ),
    )
    op.create_index("ix_asset_identifiers_asset_id", "asset_identifiers", ["asset_id"])
    op.create_index(
        "ix_asset_identifiers_lookup", "asset_identifiers", ["identifier_type", "normalized_value"]
    )
    op.create_index(
        "uq_asset_identifiers_active",
        "asset_identifiers",
        ["asset_id", "identifier_type", "normalized_value"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "asset_change_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "event_type",
            choice(
                "asset_event_type",
                "CREATE",
                "UPDATE",
                "ARCHIVE",
                "IDENTIFIER_ADD",
                "IDENTIFIER_UPDATE",
                "IDENTIFIER_REMOVE",
            ),
            nullable=False,
        ),
        sa.Column(
            "before_json",
            sa.JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql"),
        ),
        sa.Column(
            "after_json",
            sa.JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for column in ("asset_id", "actor_id", "recorded_at"):
        op.create_index(f"ix_asset_change_events_{column}", "asset_change_events", [column])
    install_guards()


def install_guards() -> None:
    # Frozen DDL: no dependency on mutable app models. Direct SQL gets the same guards.
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        op.execute("""
            CREATE OR REPLACE FUNCTION av_asset_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Asset codes are permanently reserved; archive instead'
                        USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' THEN
                    IF NEW.id IS DISTINCT FROM OLD.id OR
                       NEW.asset_code IS DISTINCT FROM OLD.asset_code THEN
                        RAISE EXCEPTION 'Asset identity is immutable' USING ERRCODE = '23514';
                    END IF;
                END IF;
                IF NEW.asset_code !~ '^[A-Z0-9][A-Z0-9_-]{0,49}$' THEN
                    RAISE EXCEPTION 'Invalid asset code' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END $$
        """)
        op.execute(
            "CREATE TRIGGER av_asset_guard BEFORE INSERT OR UPDATE OR DELETE ON assets "
            "FOR EACH ROW EXECUTE FUNCTION av_asset_guard()"
        )
        op.execute("""
            CREATE OR REPLACE FUNCTION av_history_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'History cannot be removed or rewritten' USING ERRCODE = '23514';
            END $$
        """)
        op.execute(
            "CREATE TRIGGER av_audit_guard BEFORE UPDATE OR DELETE ON asset_change_events "
            "FOR EACH ROW EXECUTE FUNCTION av_history_guard()"
        )
        op.execute(
            "CREATE TRIGGER av_claim_delete_guard BEFORE DELETE ON asset_identifiers "
            "FOR EACH ROW EXECUTE FUNCTION av_history_guard()"
        )
        mac_invalid = "NEW.normalized_value !~ '^([0-9A-F]{2}:){5}[0-9A-F]{2}$'"
    else:
        for operation in ("INSERT", "UPDATE"):
            op.execute(f"""CREATE TRIGGER av_asset_code_{operation.lower()}
                BEFORE {operation} ON assets WHEN
                NEW.asset_code GLOB '*[^A-Z0-9_-]*' OR NEW.asset_code NOT GLOB '[A-Z0-9]*'
                BEGIN SELECT RAISE(ABORT, 'Invalid asset code'); END""")
        op.execute("""CREATE TRIGGER av_asset_identity BEFORE UPDATE ON assets
            WHEN NEW.id != OLD.id OR NEW.asset_code != OLD.asset_code
            BEGIN SELECT RAISE(ABORT, 'Asset identity is immutable'); END""")
        for table, operations in (
            ("assets", ("DELETE",)),
            ("asset_identifiers", ("DELETE",)),
            ("asset_change_events", ("UPDATE", "DELETE")),
        ):
            for operation in operations:
                op.execute(f"""CREATE TRIGGER av_{table}_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN SELECT RAISE(ABORT, 'History is retained'); END""")
        mac_invalid = (
            "length(NEW.normalized_value) != 17 OR NEW.normalized_value NOT GLOB "
            "'[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:"
            "[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]'"
        )
    invalid = (
        "(NEW.identifier_type IN ('MAC_LAN', 'MAC_WLAN', 'BSSID') AND ("
        + mac_invalid
        + " OR replace(NEW.normalized_value, ':', '') != "
        "upper(replace(replace(replace(trim(NEW.raw_value), ':', ''), '-', ''), '.', ''))"
        ")) OR (NEW.identifier_type = 'HOSTNAME' AND "
        "NEW.normalized_value != lower(trim(NEW.raw_value))) OR "
        "(NEW.identifier_type IN ('SERIAL_NUMBER', 'MANAGEMENT_ID') AND "
        "NEW.normalized_value != trim(NEW.raw_value))"
    )
    if postgres:
        op.execute(f"""CREATE OR REPLACE FUNCTION av_claim_guard()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF {invalid} THEN
                    RAISE EXCEPTION 'Invalid normalized identifier' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' THEN
                    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
                    THEN RAISE EXCEPTION 'Claim ownership is immutable' USING ERRCODE = '23514';
                    END IF;
                END IF;
                RETURN NEW;
            END $$""")
        op.execute(
            "CREATE TRIGGER av_claim_guard BEFORE INSERT OR UPDATE ON asset_identifiers "
            "FOR EACH ROW EXECUTE FUNCTION av_claim_guard()"
        )
    else:
        for operation in ("INSERT", "UPDATE"):
            op.execute(f"""CREATE TRIGGER av_claim_{operation.lower()}
                BEFORE {operation} ON asset_identifiers WHEN {invalid}
                BEGIN SELECT RAISE(ABORT, 'Invalid normalized identifier'); END""")
        op.execute("""CREATE TRIGGER av_claim_ownership BEFORE UPDATE ON asset_identifiers
            WHEN NEW.id != OLD.id OR NEW.asset_id != OLD.asset_id
            BEGIN SELECT RAISE(ABORT, 'Claim ownership is immutable'); END""")


def downgrade() -> None:
    # Destructive only to Sprint 1B tables; operational downgrade requires a backup.
    op.drop_table("asset_change_events")
    op.drop_table("asset_identifiers")
    op.drop_table("assets")
    if op.get_bind().dialect.name == "postgresql":
        for function in ("av_claim_guard", "av_history_guard", "av_asset_guard"):
            op.execute(f"DROP FUNCTION {function}()")
