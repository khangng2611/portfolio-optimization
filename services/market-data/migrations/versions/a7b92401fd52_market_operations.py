"""Immutable dataset pins, registration receipts, and durable ingestion quality."""

from alembic import op
import sqlalchemy as sa

revision = "a7b92401fd52"
down_revision = "582bc1fd90ea"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "registered_dataset",
        sa.Column("dataset_id", sa.String(64), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column(
            "registered_by",
            sa.String(36),
            sa.ForeignKey("market_actor.id"),
            nullable=False,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "dataset_registration_receipt",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "actor_id", sa.String(36), sa.ForeignKey("market_actor.id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.UniqueConstraint("actor_id", "idempotency_key"),
    )
    op.create_table(
        "ingestion_quality_report",
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("ingestion_job.id"), primary_key=True
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("price_revision") as batch:
        batch.add_column(sa.Column("ingestion_job_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_price_revision_ingestion_job",
            "ingestion_job",
            ["ingestion_job_id"],
            ["id"],
        )
        batch.create_index("ix_price_revision_ingestion_job_id", ["ingestion_job_id"])


def downgrade():
    with op.batch_alter_table("price_revision") as batch:
        batch.drop_index("ix_price_revision_ingestion_job_id")
        batch.drop_constraint("fk_price_revision_ingestion_job", type_="foreignkey")
        batch.drop_column("ingestion_job_id")
    op.drop_table("ingestion_quality_report")
    op.drop_table("dataset_registration_receipt")
    op.drop_table("registered_dataset")
