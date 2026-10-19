"""Add retained recognition evidence, never modify existing master records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_recognition_surveys"
down_revision = "0010_embedding_index"
branch_labels = None
depends_on = None
TABLES = ("recognition_jobs", "survey_observations", "recognition_reviews")


def fk(name: str, target: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(target), nullable=nullable)


def stamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    payload = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "recognition_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        fk("created_by", "users.id"),
        stamp("created_at"),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("storage_key", sa.String(100), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(30), nullable=False),
        sa.Column("result_json", payload, nullable=False),
        sa.CheckConstraint("kind IN ('MODEL','OCR')", name="ck_recognition_jobs_kind"),
    )
    op.create_index("ix_recognition_jobs_created_by", "recognition_jobs", ["created_by"])
    op.create_table(
        "survey_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        fk("created_by", "users.id"),
        stamp("created_at"),
        stamp("observed_at"),
        fk("observed_location_id", "locations.id", True),
        fk("device_job_id", "recognition_jobs.id"),
        fk("label_job_id", "recognition_jobs.id", True),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("evidence_json", payload, nullable=False),
    )
    op.create_index("ix_survey_observations_created_by", "survey_observations", ["created_by"])
    op.create_table(
        "recognition_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "observation_id",
            sa.Uuid(),
            sa.ForeignKey("survey_observations.id"),
            nullable=False,
            unique=True,
        ),
        fk("reviewer_id", "users.id"),
        stamp("reviewed_at"),
        sa.Column("decision", sa.String(20), nullable=False),
        fk("selected_asset_id", "assets.id", True),
        fk("selected_model_id", "device_models.id", True),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("evidence_json", payload, nullable=False),
        sa.CheckConstraint(
            "decision IN ('MATCH','UNKNOWN','CONFLICT','MORE_PHOTOS')",
            name="ck_recognition_reviews_decision",
        ),
        sa.CheckConstraint(
            "(decision = 'MATCH' AND selected_asset_id IS NOT NULL AND "
            "selected_model_id IS NOT NULL) OR (decision != 'MATCH' AND "
            "selected_asset_id IS NULL AND selected_model_id IS NULL)",
            name="ck_recognition_reviews_selection",
        ),
    )
    for name in TABLES:
        if op.get_bind().dialect.name == "postgresql":
            op.execute(
                f"CREATE TRIGGER av_{name}_history BEFORE UPDATE OR DELETE ON {name} "
                "FOR EACH ROW EXECUTE FUNCTION av_history_guard()"
            )
        else:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER av_{name}_{action.lower()} BEFORE {action} ON {name} "
                    "BEGIN SELECT RAISE(ABORT, 'Recognition evidence retained'); END"
                )


def downgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        if bind.scalar(sa.text(f"SELECT count(*) FROM {name}")):
            raise RuntimeError("Cannot downgrade populated recognition evidence; preserve first")
    for name in reversed(TABLES):
        op.drop_table(name)
