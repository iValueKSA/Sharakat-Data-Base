"""Keep unqualified raw source records and field conflicts."""
from alembic import op
import sqlalchemy as sa

revision="0002_raw_and_conflicts"
down_revision="0001_initial"
branch_labels=None
depends_on=None

def upgrade():
    inspector=sa.inspect(op.get_bind())
    column=next(c for c in inspector.get_columns("source_opportunities") if c["name"]=="master_opportunity_id")
    if not column["nullable"]:
        with op.batch_alter_table("source_opportunities") as batch:
            batch.alter_column("master_opportunity_id",existing_type=sa.Integer(),nullable=True)
    if not inspector.has_table("opportunity_data_conflicts"):
        op.create_table(
        "opportunity_data_conflicts",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("opportunity_id",sa.Integer(),sa.ForeignKey("opportunities.id"),nullable=False,index=True),
        sa.Column("field_name",sa.String(100),nullable=False),
        sa.Column("selected_value",sa.Text(),nullable=False),
        sa.Column("conflicting_value",sa.Text(),nullable=False),
        sa.Column("source_id",sa.Integer(),sa.ForeignKey("sources.id"),nullable=False),
        sa.Column("source_record_id",sa.Integer(),sa.ForeignKey("source_opportunities.id"),nullable=False),
        sa.Column("detected_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("status",sa.String(30),nullable=False,server_default="OPEN"),
        )

def downgrade():
    op.drop_table("opportunity_data_conflicts")
    with op.batch_alter_table("source_opportunities") as batch:
        batch.alter_column("master_opportunity_id",existing_type=sa.Integer(),nullable=False)
