"""Add unstructured content, location review and typed taxonomy conflict support."""
from alembic import op
import sqlalchemy as sa

revision = "0008_wave2_content_location_taxonomy"
down_revision = "0007_merge_generated_history"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("source_content_items"):
        op.create_table(
            "source_content_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False, index=True),
            sa.Column("external_key", sa.String(1000), nullable=False),
            sa.Column("url", sa.String(1200), nullable=False),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column("publication_date", sa.String(40)),
            sa.Column("content_type", sa.String(60), nullable=False, server_default="NON_INVESTMENT_CONTENT"),
            sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("extracted_description", sa.Text(), nullable=False, server_default=""),
            sa.Column("attachments_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("detected_keywords_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("parser_version", sa.String(40), nullable=False),
            sa.Column("material_change", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("source_id", "external_key", name="uq_source_content_key"),
        )
    if not inspector.has_table("location_reviews"):
        op.create_table(
            "location_reviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False, index=True),
            sa.Column("external_id", sa.String(200), nullable=False),
            sa.Column("source_record_id", sa.Integer(), sa.ForeignKey("source_opportunities.id")),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("sector", sa.String(200)),
            sa.Column("source_location", sa.Text()),
            sa.Column("description", sa.Text()),
            sa.Column("latitude", sa.Float()),
            sa.Column("longitude", sa.Float()),
            sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
            sa.Column("confidence_score", sa.Float(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("source_id", "external_id", name="uq_location_review_source_external"),
        )
    if not inspector.has_table("taxonomy_mappings"):
        op.create_table(
            "taxonomy_mappings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_key", sa.String(80), nullable=False, index=True),
            sa.Column("source_value", sa.String(200), nullable=False),
            sa.Column("normalized_value", sa.String(80), nullable=False),
            sa.Column("mapping_rule", sa.String(300), nullable=False),
            sa.Column("mapping_version", sa.String(40), nullable=False, server_default="1"),
            sa.UniqueConstraint("source_key", "source_value", name="uq_taxonomy_source_value"),
        )
    if not inspector.has_table("organization_aliases"):
        op.create_table(
            "organization_aliases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.String(80), nullable=False, index=True),
            sa.Column("canonical_name_ar", sa.String(300), nullable=False),
            sa.Column("canonical_name_en", sa.String(300), nullable=False),
            sa.Column("alias", sa.String(300), nullable=False, unique=True),
            sa.Column("source_key", sa.String(80)),
        )
    conflict_columns = {c["name"] for c in inspector.get_columns("opportunity_data_conflicts")}
    if "conflict_type" not in conflict_columns:
        with op.batch_alter_table("opportunity_data_conflicts") as batch:
            batch.add_column(sa.Column("conflict_type", sa.String(40), nullable=False, server_default="FIELD_VALUE_CONFLICT"))
        op.execute("UPDATE opportunity_data_conflicts SET conflict_type='TAXONOMY_CONFLICT' WHERE lower(field_name) IN ('sector','subsector','opportunity_type','activity')")
    job_columns = {c["name"] for c in inspector.get_columns("source_sync_jobs")}
    if "location_review_count" not in job_columns:
        with op.batch_alter_table("source_sync_jobs") as batch:
            batch.add_column(sa.Column("location_review_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("source_sync_jobs") as batch:
        batch.drop_column("location_review_count")
    with op.batch_alter_table("opportunity_data_conflicts") as batch:
        batch.drop_column("conflict_type")
    op.drop_table("organization_aliases")
    op.drop_table("taxonomy_mappings")
    op.drop_table("location_reviews")
    op.drop_table("source_content_items")
