"""Separate technical health, public coverage, and source limitations."""
from alembic import op
import sqlalchemy as sa

revision = "0013_public_coverage_model"
down_revision = "0012_wave3_source_models"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sources", sa.Column("technical_health", sa.String(30), nullable=False, server_default="UNKNOWN"))
    op.add_column("sources", sa.Column("coverage_status", sa.String(40), nullable=False, server_default="UNKNOWN_COVERAGE"))
    op.add_column("sources", sa.Column("coverage_notes", sa.Text(), nullable=False, server_default=""))
    op.create_table("source_limitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("limitation_type", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.String(1200), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("affects_completeness", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.UniqueConstraint("source_id", "limitation_type", "evidence_url", name="uq_source_limitation_evidence"))
    op.create_index("ix_source_limitations_source_id", "source_limitations", ["source_id"])
    op.create_table("modon_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("official_name_ar", sa.String(300), nullable=True),
        sa.Column("official_name_en", sa.String(300), nullable=False),
        sa.Column("location_type", sa.String(60), nullable=False),
        sa.Column("source_identifier", sa.String(200), nullable=False),
        sa.Column("region", sa.String(200), nullable=True),
        sa.Column("governorate", sa.String(200), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_url", sa.String(1200), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_identifier", name="uq_modon_location_source_identifier"))
    op.create_table("ncp_project_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_source_opportunity_id", sa.Integer(), sa.ForeignKey("source_opportunities.id"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("event_date", sa.String(40), nullable=True),
        sa.Column("source_url", sa.String(1200), nullable=False),
        sa.Column("stage_before", sa.String(40), nullable=True),
        sa.Column("stage_after", sa.String(40), nullable=False),
        sa.Column("raw_title", sa.Text(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_source_opportunity_id", "source_url", "event_type", name="uq_ncp_project_event_source"))
    op.create_index("ix_ncp_project_events_project_source_opportunity_id", "ncp_project_events", ["project_source_opportunity_id"])


def downgrade():
    op.drop_index("ix_ncp_project_events_project_source_opportunity_id", table_name="ncp_project_events")
    op.drop_table("ncp_project_events")
    op.drop_table("modon_locations")
    op.drop_index("ix_source_limitations_source_id", table_name="source_limitations")
    op.drop_table("source_limitations")
    op.drop_column("sources", "coverage_notes")
    op.drop_column("sources", "coverage_status")
    op.drop_column("sources", "technical_health")
