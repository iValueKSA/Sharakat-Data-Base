"""Support reversible duplicate merges."""
from alembic import op
import sqlalchemy as sa

revision="0003_reversible_merge"
down_revision="0002_raw_and_conflicts"
branch_labels=None
depends_on=None

def upgrade():
    inspector=sa.inspect(op.get_bind())
    columns={c["name"] for c in inspector.get_columns("opportunities")}
    if "merged_into_id" not in columns:
        with op.batch_alter_table("opportunities") as batch:
            batch.add_column(sa.Column("merged_into_id",sa.Integer(),sa.ForeignKey("opportunities.id"),nullable=True))
    indexes={i["name"] for i in inspector.get_indexes("opportunities")}
    if "ix_opportunities_merged_into_id" not in indexes:
        op.create_index("ix_opportunities_merged_into_id","opportunities",["merged_into_id"])
    if not inspector.has_table("opportunity_merge_audit"):
        op.create_table(
        "opportunity_merge_audit",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("merged_opportunity_id",sa.Integer(),sa.ForeignKey("opportunities.id"),nullable=False,index=True),
        sa.Column("target_opportunity_id",sa.Integer(),sa.ForeignKey("opportunities.id"),nullable=False,index=True),
        sa.Column("source_record_ids",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("undone_at",sa.DateTime(timezone=True),nullable=True),
        )

def downgrade():
    op.drop_table("opportunity_merge_audit")
    op.drop_index("ix_opportunities_merged_into_id",table_name="opportunities")
    with op.batch_alter_table("opportunities") as batch:
        batch.drop_column("merged_into_id")
