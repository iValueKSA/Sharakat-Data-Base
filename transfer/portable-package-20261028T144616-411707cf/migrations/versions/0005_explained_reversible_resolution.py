"""Explain duplicate candidates and make master merges fully auditable/reversible."""
from alembic import op
import sqlalchemy as sa

revision="0005_explained_resolution"
down_revision="0004_validation_metrics"
branch_labels=None
depends_on=None


def add_columns(table, columns):
    existing={c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    missing=[c for c in columns if c.name not in existing]
    if missing:
        with op.batch_alter_table(table) as batch:
            for column in missing: batch.add_column(column)


def upgrade():
    add_columns("duplicate_candidates",[sa.Column("explanation_json",sa.JSON(),nullable=True)])
    add_columns("opportunity_merge_audit",[
        sa.Column("merged_at",sa.DateTime(timezone=True),nullable=True),
        sa.Column("merge_reason",sa.Text(),nullable=True),
        sa.Column("merge_evidence",sa.JSON(),nullable=True),
        sa.Column("performed_by",sa.String(200),nullable=True),
        sa.Column("target_before_json",sa.JSON(),nullable=True),
        sa.Column("target_after_json",sa.JSON(),nullable=True),
    ])


def downgrade():
    for table, columns in (("duplicate_candidates",["explanation_json"]),
                           ("opportunity_merge_audit",["merged_at","merge_reason","merge_evidence","performed_by","target_before_json","target_after_json"])):
        existing={c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for column in columns:
                if column in existing: batch.drop_column(column)
