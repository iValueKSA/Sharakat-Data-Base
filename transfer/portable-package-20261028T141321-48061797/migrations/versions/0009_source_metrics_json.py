"""Persist source-specific collection and filtering metrics per sync job."""
from alembic import op
import sqlalchemy as sa

revision = "0009_source_metrics_json"
down_revision = "0008_wave2_content_location_taxonomy"
branch_labels = None
depends_on = None

def upgrade():
    columns={c["name"] for c in sa.inspect(op.get_bind()).get_columns("source_sync_jobs")}
    if "metrics_json" not in columns:
        with op.batch_alter_table("source_sync_jobs") as batch:
            batch.add_column(sa.Column("metrics_json",sa.JSON(),nullable=False,server_default="{}"))

def downgrade():
    columns={c["name"] for c in sa.inspect(op.get_bind()).get_columns("source_sync_jobs")}
    if "metrics_json" in columns:
        with op.batch_alter_table("source_sync_jobs") as batch: batch.drop_column("metrics_json")
