"""Register reviewed offline artifacts independently of queued training jobs."""

from alembic import op

revision = "b5147af92c02"
down_revision = "b5147af92c01"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ml_model") as table:
        table.alter_column("training_job_id", nullable=True)


def downgrade():
    with op.batch_alter_table("ml_model") as table:
        table.alter_column("training_job_id", nullable=False)
