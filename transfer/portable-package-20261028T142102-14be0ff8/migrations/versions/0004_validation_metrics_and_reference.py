"""Store normalized references and source collection completeness metrics."""
from alembic import op
import sqlalchemy as sa

revision="0004_validation_metrics"
down_revision="0003_reversible_merge"
branch_labels=None
depends_on=None

def add_columns(table, columns):
    existing={c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    missing=[column for column in columns if column.name not in existing]
    if missing:
        with op.batch_alter_table(table) as batch:
            for column in missing: batch.add_column(column)

def upgrade():
    add_columns("opportunities",[sa.Column("reference_number_normalized",sa.String(200),nullable=True)])
    add_columns("source_opportunities",[
        sa.Column("source_reference_number_normalized",sa.String(200),nullable=True),
        sa.Column("missing_successful_checks",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("last_missing_at",sa.DateTime(timezone=True),nullable=True),
    ])
    add_columns("sources",[
        sa.Column("last_source_total_reported",sa.Integer(),nullable=True),
        sa.Column("last_collection_completeness_percent",sa.Float(),nullable=True),
        sa.Column("last_pagination_complete",sa.Boolean(),nullable=True),
        sa.Column("missing_confirmation_threshold",sa.Integer(),nullable=False,server_default="3"),
    ])
    add_columns("source_sync_jobs",[
        sa.Column("unchanged_count",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("source_total_reported",sa.Integer(),nullable=True),
        sa.Column("pages_requested",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("pages_successful",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("records_received",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("records_parsed",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("unique_records",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("duplicate_candidates_count",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("merged_records_count",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("removed_records_count",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("active_count",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("expired_count",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("duplicate_items_between_pages",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("collection_completeness_percent",sa.Float(),nullable=True),
        sa.Column("pagination_complete",sa.Boolean(),nullable=True),
    ])
    for table,column,index in (("opportunities","reference_number_normalized","ix_opportunities_reference_number_normalized"),
                               ("source_opportunities","source_reference_number_normalized","ix_source_opportunities_source_reference_number_normalized")):
        indexes={i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}
        if index not in indexes: op.create_index(index,table,[column])

def downgrade():
    for table,index in (("opportunities","ix_opportunities_reference_number_normalized"),
                        ("source_opportunities","ix_source_opportunities_source_reference_number_normalized")):
        try: op.drop_index(index,table_name=table)
        except Exception: pass
    for table,columns in (("opportunities",["reference_number_normalized"]),
                          ("source_opportunities",["source_reference_number_normalized","missing_successful_checks","last_missing_at"]),
                          ("sources",["last_source_total_reported","last_collection_completeness_percent","last_pagination_complete","missing_confirmation_threshold"]),
                          ("source_sync_jobs",["unchanged_count","source_total_reported","pages_requested","pages_successful","records_received","records_parsed","unique_records","duplicate_candidates_count","merged_records_count","removed_records_count","active_count","expired_count","duplicate_items_between_pages","collection_completeness_percent","pagination_complete"])):
        existing={c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for column in columns:
                if column in existing: batch.drop_column(column)
