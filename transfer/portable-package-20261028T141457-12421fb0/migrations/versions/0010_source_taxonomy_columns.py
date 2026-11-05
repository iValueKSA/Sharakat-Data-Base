"""Store source and normalized taxonomies in queryable provenance columns."""
from alembic import op
import sqlalchemy as sa

revision = "0010_source_taxonomy_columns"
down_revision = "0009_source_metrics_json"
branch_labels = None
depends_on = None

def upgrade():
    columns={c["name"] for c in sa.inspect(op.get_bind()).get_columns("source_opportunities")}
    missing=[sa.Column(name,sa.String(200 if name.startswith("source_") else 80),nullable=True) for name in ("source_sector","source_subsector","normalized_sector","normalized_subsector") if name not in columns]
    if missing:
        with op.batch_alter_table("source_opportunities") as batch:
            for column in missing:batch.add_column(column)

def downgrade():
    columns={c["name"] for c in sa.inspect(op.get_bind()).get_columns("source_opportunities")}
    with op.batch_alter_table("source_opportunities") as batch:
        for name in ("source_sector","source_subsector","normalized_sector","normalized_subsector"):
            if name in columns:batch.drop_column(name)
