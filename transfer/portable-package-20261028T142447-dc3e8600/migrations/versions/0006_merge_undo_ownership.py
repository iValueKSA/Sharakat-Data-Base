"""Track all reassigned child rows for complete merge undo."""
from alembic import op
import sqlalchemy as sa

revision = "0006_merge_undo_ownership"
down_revision = "0005_explained_resolution"
branch_labels = None
depends_on = None


def upgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("opportunity_merge_audit")}
    missing = [
        sa.Column("source_history_ids", sa.JSON(), nullable=True),
        sa.Column("source_provenance_ids", sa.JSON(), nullable=True),
        sa.Column("source_conflict_ids", sa.JSON(), nullable=True),
        sa.Column("source_document_ids", sa.JSON(), nullable=True),
    ]
    with op.batch_alter_table("opportunity_merge_audit") as batch:
        for column in missing:
            if column.name not in existing:
                batch.add_column(column)


def downgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("opportunity_merge_audit")}
    with op.batch_alter_table("opportunity_merge_audit") as batch:
        for name in ("source_history_ids", "source_provenance_ids", "source_conflict_ids", "source_document_ids"):
            if name in existing:
                batch.drop_column(name)
