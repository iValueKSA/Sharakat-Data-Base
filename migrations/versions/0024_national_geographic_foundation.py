"""Add nullable national geography and versioned reference-import structures."""
from alembic import op
import sqlalchemy as sa

revision = "0024_national_geography"
down_revision = "0023_quant_commercial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "geographic_reference_datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("effective_date", sa.String(length=40), nullable=True),
        sa.Column("operator", sa.String(length=300), nullable=False),
        sa.Column("source_url", sa.String(length=1200), nullable=False),
        sa.Column("license_name", sa.String(length=300), nullable=True),
        sa.Column("license_url", sa.String(length=1200), nullable=True),
        sa.Column("license_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("coverage_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("provenance_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("import_status", sa.String(length=30), nullable=False, server_default="IMPORTED"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("dataset_key", "version", name="uq_geography_dataset_version"),
    )
    op.create_index("ix_geographic_reference_datasets_dataset_key", "geographic_reference_datasets", ["dataset_key"])
    op.create_index("ix_geographic_reference_datasets_is_current", "geographic_reference_datasets", ["is_current"])
    op.create_table(
        "geographic_reference_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("geographic_reference_datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("geographic_reference_units.id"), nullable=True),
        sa.Column("parent_external_id", sa.String(length=200), nullable=True),
        sa.Column("name_ar", sa.String(length=300), nullable=False),
        sa.Column("name_en", sa.String(length=300), nullable=True),
        sa.Column("aliases_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("geometry_json", sa.JSON(), nullable=True),
        sa.Column("source_record_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.UniqueConstraint("dataset_id", "level", "external_id", name="uq_geography_unit_dataset_level_id"),
    )
    op.create_index("ix_geographic_reference_units_dataset_id", "geographic_reference_units", ["dataset_id"])
    op.create_index("ix_geographic_reference_units_level", "geographic_reference_units", ["level"])
    op.create_index("ix_geographic_reference_units_parent_id", "geographic_reference_units", ["parent_id"])
    op.add_column("opportunities", sa.Column("geographic_scope", sa.String(length=40), nullable=True))
    op.add_column("opportunities", sa.Column("geography_reference_unit_id", sa.Integer(), nullable=True))
    op.add_column("opportunities", sa.Column("geography_evidence_json", sa.JSON(), nullable=True))
    op.add_column("opportunities", sa.Column("coordinate_provenance_json", sa.JSON(), nullable=True))
    op.create_check_constraint("ck_opportunity_geographic_scope", "opportunities",
        "geographic_scope IS NULL OR geographic_scope IN ('SPECIFIC_LOCATION','MULTIPLE_VERIFIED_LOCATIONS','REGION_WIDE','NATIONWIDE','UNSPECIFIED')")
    op.create_foreign_key("fk_opportunities_geography_reference_unit", "opportunities", "geographic_reference_units", ["geography_reference_unit_id"], ["id"])
    op.create_index("ix_opportunities_geography_reference_unit_id", "opportunities", ["geography_reference_unit_id"])
    op.add_column("opportunity_locations", sa.Column("geography_reference_unit_id", sa.Integer(), nullable=True))
    op.add_column("opportunity_locations", sa.Column("source_evidence_json", sa.JSON(), nullable=True))
    op.create_foreign_key("fk_opportunity_locations_geography_reference_unit", "opportunity_locations", "geographic_reference_units", ["geography_reference_unit_id"], ["id"])
    op.create_index("ix_opportunity_locations_geography_reference_unit_id", "opportunity_locations", ["geography_reference_unit_id"])


def downgrade():
    op.drop_index("ix_opportunity_locations_geography_reference_unit_id", table_name="opportunity_locations")
    op.drop_constraint("fk_opportunity_locations_geography_reference_unit", "opportunity_locations", type_="foreignkey")
    op.drop_column("opportunity_locations", "source_evidence_json")
    op.drop_column("opportunity_locations", "geography_reference_unit_id")
    op.drop_index("ix_opportunities_geography_reference_unit_id", table_name="opportunities")
    op.drop_constraint("fk_opportunities_geography_reference_unit", "opportunities", type_="foreignkey")
    op.drop_constraint("ck_opportunity_geographic_scope", "opportunities", type_="check")
    op.drop_column("opportunities", "coordinate_provenance_json")
    op.drop_column("opportunities", "geography_evidence_json")
    op.drop_column("opportunities", "geography_reference_unit_id")
    op.drop_column("opportunities", "geographic_scope")
    op.drop_index("ix_geographic_reference_units_parent_id", table_name="geographic_reference_units")
    op.drop_index("ix_geographic_reference_units_level", table_name="geographic_reference_units")
    op.drop_index("ix_geographic_reference_units_dataset_id", table_name="geographic_reference_units")
    op.drop_table("geographic_reference_units")
    op.drop_index("ix_geographic_reference_datasets_is_current", table_name="geographic_reference_datasets")
    op.drop_index("ix_geographic_reference_datasets_dataset_key", table_name="geographic_reference_datasets")
    op.drop_table("geographic_reference_datasets")
