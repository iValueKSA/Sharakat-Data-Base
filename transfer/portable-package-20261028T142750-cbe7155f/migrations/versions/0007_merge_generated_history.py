"""Track merge-generated history rows so undo can restore the exact prior state."""
from alembic import op
import sqlalchemy as sa

revision = "0007_merge_generated_history"
down_revision = "0006_merge_undo_ownership"
branch_labels = None
depends_on = None


def upgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("opportunity_merge_audit")}
    if "merge_history_ids" not in existing:
        with op.batch_alter_table("opportunity_merge_audit") as batch:
            batch.add_column(sa.Column("merge_history_ids", sa.JSON(), nullable=True))


def downgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("opportunity_merge_audit")}
    if "merge_history_ids" in existing:
        with op.batch_alter_table("opportunity_merge_audit") as batch:
            batch.drop_column("merge_history_ids")
