"""Versioned embedding generations only; no automatic encoder or data backfill."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010_embedding_index"
down_revision = "0009_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "embedding_indexes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("encoder_spec", json_type, nullable=False),
        sa.Column("reference_fingerprint", sa.String(64), nullable=False),
        sa.Column("reference_count", sa.Integer(), nullable=False),
        sa.Column("calibration", json_type),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "reference_count >= 0 AND reference_count <= 2000", name="ck_embedding_indexes_count"
        ),
    )
    op.create_table(
        "image_embeddings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "index_id",
            sa.Uuid(),
            sa.ForeignKey("embedding_indexes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reference_image_id",
            sa.Uuid(),
            sa.ForeignKey("device_reference_images.id", ondelete="SET NULL"),
        ),
        sa.Column("reference_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column(
            "device_model_id",
            sa.Uuid(),
            sa.ForeignKey("device_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("vector_data", json_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "index_id", "reference_snapshot_id", name="uq_image_embeddings_reference"
        ),
    )
    op.create_index("ix_image_embeddings_index_id", "image_embeddings", ["index_id"])
    op.create_table(
        "embedding_index_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "current_index_id",
            sa.Uuid(),
            sa.ForeignKey("embedding_indexes.id", ondelete="RESTRICT"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint("id = 1 AND version > 0", name="ck_embedding_index_state_singleton"),
    )
    op.execute("INSERT INTO embedding_index_state (id, version) VALUES (1, 1)")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER av_embedding_indexes_guard BEFORE UPDATE OR DELETE ON "
            "embedding_indexes FOR EACH ROW EXECUTE FUNCTION av_history_guard()"
        )
        op.execute("""CREATE OR REPLACE FUNCTION av_embedding_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.reference_image_id IS NULL OR
                   NEW.reference_snapshot_id != NEW.reference_image_id OR NOT EXISTS (
                    SELECT 1 FROM device_reference_images WHERE id = NEW.reference_image_id
                    AND device_model_id = NEW.device_model_id AND sha256 = NEW.source_sha256
                ) OR (SELECT count(*) FROM image_embeddings WHERE index_id = NEW.index_id) >=
                     (SELECT reference_count FROM embedding_indexes WHERE id = NEW.index_id) THEN
                    RAISE EXCEPTION 'Invalid embedding source or capacity' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Embedding history retained' USING ERRCODE = '23514';
            END IF;
            IF OLD.reference_image_id IS NULL OR NEW.reference_image_id IS NOT NULL OR
               (to_jsonb(NEW) - 'reference_image_id') IS DISTINCT FROM
               (to_jsonb(OLD) - 'reference_image_id') THEN
                RAISE EXCEPTION 'Embedding is immutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER av_embedding_guard BEFORE INSERT OR UPDATE OR DELETE ON "
            "image_embeddings FOR EACH ROW EXECUTE FUNCTION av_embedding_guard()"
        )
        op.execute("""CREATE OR REPLACE FUNCTION av_embedding_head_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Index head retained' USING ERRCODE = '23514';
            END IF;
            IF NEW.id != OLD.id OR NEW.version != OLD.version + 1
               OR NEW.current_index_id IS NULL THEN
                RAISE EXCEPTION 'Invalid index head transition' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$""")
        op.execute(
            "CREATE TRIGGER av_embedding_head_guard BEFORE UPDATE OR DELETE ON "
            "embedding_index_state FOR EACH ROW EXECUTE FUNCTION av_embedding_head_guard()"
        )
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER av_embedding_indexes_{operation.lower()} BEFORE {operation} "
                "ON embedding_indexes BEGIN "
                "SELECT RAISE(ABORT, 'Index history retained'); END"
            )
        op.execute("""CREATE TRIGGER av_embedding_insert BEFORE INSERT ON image_embeddings
            WHEN NEW.reference_image_id IS NULL OR
                 NEW.reference_snapshot_id IS NOT NEW.reference_image_id OR NOT EXISTS (
                   SELECT 1 FROM device_reference_images WHERE id = NEW.reference_image_id
                   AND device_model_id = NEW.device_model_id AND sha256 = NEW.source_sha256
                 ) OR (SELECT count(*) FROM image_embeddings WHERE index_id = NEW.index_id) >=
                      (SELECT reference_count FROM embedding_indexes WHERE id = NEW.index_id)
            BEGIN SELECT RAISE(ABORT, 'Invalid embedding source or capacity'); END""")
        columns = (
            "id",
            "index_id",
            "reference_snapshot_id",
            "device_model_id",
            "source_sha256",
            "vector_data",
            "created_at",
        )
        changed = " OR ".join(f"NEW.{col} IS NOT OLD.{col}" for col in columns)
        op.execute(f"""CREATE TRIGGER av_embedding_update BEFORE UPDATE ON image_embeddings
            WHEN OLD.reference_image_id IS NULL OR NEW.reference_image_id IS NOT NULL OR {changed}
            BEGIN SELECT RAISE(ABORT, 'Embedding immutable'); END""")
        op.execute(
            "CREATE TRIGGER av_embedding_delete BEFORE DELETE ON image_embeddings "
            "BEGIN SELECT RAISE(ABORT, 'Embedding history retained'); END"
        )
        op.execute("""CREATE TRIGGER av_embedding_head_update BEFORE UPDATE ON embedding_index_state
            WHEN NEW.id != OLD.id OR NEW.version != OLD.version + 1 OR NEW.current_index_id IS NULL
            BEGIN SELECT RAISE(ABORT, 'Invalid index head transition'); END""")
        op.execute(
            "CREATE TRIGGER av_embedding_head_delete BEFORE DELETE ON embedding_index_state "
            "BEGIN SELECT RAISE(ABORT, 'Index head retained'); END"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM embedding_indexes")) or bind.scalar(
        sa.text("SELECT count(*) FROM image_embeddings")
    ):
        raise RuntimeError("Cannot downgrade populated embedding index; preserve and review first")
    op.drop_table("embedding_index_state")
    op.drop_table("image_embeddings")
    op.drop_table("embedding_indexes")
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION av_embedding_guard()")
        op.execute("DROP FUNCTION av_embedding_head_guard()")
