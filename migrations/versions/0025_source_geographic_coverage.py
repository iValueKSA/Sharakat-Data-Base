"""Add versioned source-to-region geographic coverage assessments."""
from alembic import op
import sqlalchemy as sa

revision = "0025_source_geographic_coverage"
down_revision = "0024_national_geography"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_geographic_coverage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("geographic_reference_unit_id", sa.Integer(),
                  sa.ForeignKey("geographic_reference_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coverage_status", sa.String(length=20), nullable=False),
        sa.Column("assessment_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_id", "geographic_reference_unit_id",
                            name="uq_source_geographic_coverage_unit"),
        sa.CheckConstraint("coverage_status IN ('COVERED','NOT_COVERED','PARTIAL')",
                           name="ck_source_geographic_coverage_status"),
    )
    op.create_index("ix_source_geographic_coverage_source_id", "source_geographic_coverage", ["source_id"])
    op.create_index("ix_source_geographic_coverage_geographic_reference_unit_id",
                    "source_geographic_coverage", ["geographic_reference_unit_id"])


def downgrade():
    op.drop_index("ix_source_geographic_coverage_geographic_reference_unit_id",
                  table_name="source_geographic_coverage")
    op.drop_index("ix_source_geographic_coverage_source_id", table_name="source_geographic_coverage")
    op.drop_table("source_geographic_coverage")
