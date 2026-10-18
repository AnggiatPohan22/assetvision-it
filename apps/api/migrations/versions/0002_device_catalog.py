"""Sprint 1A-01 catalog schema; no physical assets or automatic seed data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_device_catalog"
down_revision = "0001_sprint0"
branch_labels = None
depends_on = None


def record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def name_checks(column: str, prefix: str) -> list[sa.CheckConstraint]:
    # Frozen migration definitions; do not import mutable application metadata.
    return [
        sa.CheckConstraint(f"length({column}) > 0", name=f"ck_{prefix}_name_nonempty"),
        sa.CheckConstraint(
            f"{column} = trim({column}) AND {column} NOT LIKE '%  %'"
            f" AND {column} NOT LIKE '%\t%' AND {column} NOT LIKE '%\n%'"
            f" AND {column} NOT LIKE '%\r%'",
            name=f"ck_{prefix}_name_canonical",
        ),
        sa.CheckConstraint("version > 0", name=f"ck_{prefix}_version"),
    ]


def upgrade() -> None:
    op.create_table(
        "device_categories",
        *record_columns(),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        *name_checks("name", "device_categories"),
        sa.CheckConstraint(
            "length(code) > 0 AND code = lower(trim(code)) AND code NOT LIKE '% %'",
            name="ck_device_categories_code",
        ),
    )
    op.create_table(
        "manufacturers",
        *record_columns(),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column(
            "normalized_name", sa.String(150),
            sa.Computed("lower(trim(name))", persisted=True), nullable=False, unique=True,
        ),
        sa.Column("website", sa.String(2048)),
        *name_checks("name", "manufacturers"),
    )
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "device_models",
        *record_columns(),
        sa.Column("manufacturer_id", sa.Uuid(), sa.ForeignKey("manufacturers.id"), nullable=False),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("device_categories.id"), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column(
            "normalized_model_name", sa.String(200),
            sa.Computed("lower(trim(model_name))", persisted=True), nullable=False,
        ),
        sa.Column("aliases", json_type, nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "environment",
            sa.Enum(
                "indoor", "outdoor", "both", name="device_environment",
                native_enum=False, create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("specs", json_type, nullable=False),
        sa.UniqueConstraint(
            "manufacturer_id", "normalized_model_name", name="uq_device_models_manufacturer_name"
        ),
        *name_checks("model_name", "device_models"),
    )
    for column in ("manufacturer_id", "category_id", "normalized_model_name"):
        op.create_index(f"ix_device_models_{column}", "device_models", [column])
    op.create_table(
        "device_reference_images",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("device_model_id", sa.Uuid(), sa.ForeignKey("device_models.id"), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("angle", sa.String(100)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_device_reference_images_byte_size"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_device_reference_images_sha256"),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_device_reference_images_mime_type",
        ),
        sa.CheckConstraint(
            "length(storage_key) > 0 AND storage_key NOT LIKE '/%'"
            " AND storage_key NOT LIKE '%..%' AND storage_key NOT LIKE '%:%'"
            " AND replace(storage_key, '\\', '') = storage_key",
            name="ck_device_reference_images_storage_key",
        ),
    )
    op.create_index(
        "ix_device_reference_images_device_model_id", "device_reference_images", ["device_model_id"]
    )
    op.create_index(
        "uq_device_reference_images_primary", "device_reference_images", ["device_model_id"],
        unique=True, postgresql_where=sa.text("is_primary"), sqlite_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_table("device_reference_images")
    op.drop_table("device_models")
    op.drop_table("manufacturers")
    op.drop_table("device_categories")
