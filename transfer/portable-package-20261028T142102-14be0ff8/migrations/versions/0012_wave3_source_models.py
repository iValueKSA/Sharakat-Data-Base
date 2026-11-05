"""Persist multi-location source evidence and qualification review separately."""
from alembic import op
import sqlalchemy as sa

revision = "0012_wave3_source_models"
down_revision = "0011_invest_saudi_source_identity"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "opportunity_locations" not in tables:
        op.create_table(
            "opportunity_locations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_opportunity_id", sa.Integer(), sa.ForeignKey("source_opportunities.id"), nullable=False),
            sa.Column("location_name", sa.String(200), nullable=False),
            sa.Column("location_scope", sa.String(40), nullable=False, server_default="SINGLE_LOCATION"),
            sa.Column("is_al_ahsa", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source_location_text", sa.Text(), nullable=True),
            sa.UniqueConstraint("source_opportunity_id", "location_name", name="uq_opportunity_location_source_name"),
        )
        op.create_index("ix_opportunity_locations_source_opportunity_id", "opportunity_locations", ["source_opportunity_id"])
    if "qualification_reviews" not in tables:
        op.create_table(
            "qualification_reviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
            sa.Column("source_record_id", sa.Integer(), sa.ForeignKey("source_opportunities.id"), nullable=True),
            sa.Column("external_id", sa.String(200), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("source_url", sa.String(1200), nullable=False),
            sa.Column("proposed_type", sa.String(80), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("source_id", "external_id", name="uq_qualification_review_source_external"),
        )
        op.create_index("ix_qualification_reviews_source_id", "qualification_reviews", ["source_id"])


def downgrade():
    op.drop_index("ix_qualification_reviews_source_id", table_name="qualification_reviews")
    op.drop_table("qualification_reviews")
    op.drop_index("ix_opportunity_locations_source_opportunity_id", table_name="opportunity_locations")
    op.drop_table("opportunity_locations")
