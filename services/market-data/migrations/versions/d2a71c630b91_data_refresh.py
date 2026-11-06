"""Durable refresh control plane, leases, immutable source/quality/snapshot pins."""

from alembic import op
import sqlalchemy as sa

revision = "d2a71c630b91"
down_revision = "a7b92401fd52"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "refresh_schedule",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "actor_id", sa.String(36), sa.ForeignKey("market_actor.id"), nullable=False
        ),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_successful_cutoff", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_schedule_actor_id", "refresh_schedule", ["actor_id"])
    op.create_index(
        "ix_refresh_schedule_next_run_at", "refresh_schedule", ["next_run_at"]
    )
    op.create_table(
        "refresh_job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "schedule_id",
            sa.String(36),
            sa.ForeignKey("refresh_schedule.id"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", sa.String(36), sa.ForeignKey("market_actor.id"), nullable=False
        ),
        sa.Column("tick_key", sa.String(128), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("schedule_version", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("cutoff_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.JSON()),
        sa.Column("source_manifest", sa.JSON()),
        sa.Column("artifacts", sa.JSON(), nullable=False),
        sa.Column("ingestion_job_ids", sa.JSON(), nullable=False),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("market_snapshot.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("schedule_id", "tick_key"),
    )
    for name in ["schedule_id", "actor_id", "status"]:
        op.create_index("ix_refresh_job_" + name, "refresh_job", [name])
    op.create_table(
        "refresh_receipt",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "actor_id", sa.String(36), sa.ForeignKey("market_actor.id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.UniqueConstraint("actor_id", "idempotency_key"),
    )


def downgrade():
    op.drop_table("refresh_receipt")
    op.drop_table("refresh_job")
    op.drop_table("refresh_schedule")
