"""Add source-scoped multi-valued Asset / Facility / Site Type dimension.

Revision ID: 0021_asset_facility_type
Revises: 0020_investment_model
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_asset_facility_type"
down_revision = "0020_investment_model"
branch_labels = None
depends_on = None

TYPES = [
    ("asset_facility_type:mobile_vending_site", "العربات المتنقلة"),
    ("asset_facility_type:public_park", "الحدائق"),
    ("asset_facility_type:waterfront", "الشواطئ والواجهات"),
    ("asset_facility_type:other", "أخرى"),
    ("asset_facility_type:land", "الاراضي"),
    ("asset_facility_type:public_square", "الساحات الميادين"),
    ("asset_facility_type:building", "المباني"),
    ("asset_facility_type:road_sidewalk", "الطرق والارصفة"),
    ("asset_facility_type:missing", "غير محدد"),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "asset_facility_types" not in tables:
        op.create_table(
            "asset_facility_types",
            sa.Column("canonical_id", sa.String(length=120), primary_key=True),
            sa.Column("label_ar", sa.String(length=200), nullable=False, unique=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "asset_facility_type_aliases" not in tables:
        op.create_table(
            "asset_facility_type_aliases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_key", sa.String(length=80), nullable=False),
            sa.Column("source_field", sa.String(length=120), nullable=False),
            sa.Column("source_value", sa.String(length=300), nullable=False),
            sa.Column("canonical_id", sa.String(length=120), sa.ForeignKey("asset_facility_types.canonical_id"), nullable=False),
            sa.UniqueConstraint("source_key", "source_field", "source_value", name="uq_asset_type_alias_source_field_value"),
        )
        op.create_index("ix_asset_facility_type_aliases_source_key", "asset_facility_type_aliases", ["source_key"])
        op.create_index("ix_asset_facility_type_aliases_canonical_id", "asset_facility_type_aliases", ["canonical_id"])
    if "opportunity_asset_facility_types" not in tables:
        op.create_table(
            "opportunity_asset_facility_types",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("canonical_id", sa.String(length=120), sa.ForeignKey("asset_facility_types.canonical_id"), nullable=False),
            sa.Column("source_record_id", sa.Integer(), sa.ForeignKey("source_opportunities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("raw_value", sa.String(length=600), nullable=False),
            sa.UniqueConstraint("opportunity_id", "canonical_id", "source_record_id", name="uq_master_asset_type_source"),
        )
        op.create_index("ix_opportunity_asset_facility_types_opportunity_id", "opportunity_asset_facility_types", ["opportunity_id"])
        op.create_index("ix_opportunity_asset_facility_types_canonical_id", "opportunity_asset_facility_types", ["canonical_id"])
        op.create_index("ix_opportunity_asset_facility_types_source_record_id", "opportunity_asset_facility_types", ["source_record_id"])
    present = set(bind.execute(sa.text("SELECT canonical_id FROM asset_facility_types")).scalars())
    for canonical_id, label in TYPES:
        if canonical_id not in present:
            bind.execute(sa.text("INSERT INTO asset_facility_types (canonical_id,label_ar,active) VALUES (:id,:label,true)"), {"id": canonical_id, "label": label})
    aliases = [
        ("العربات المتنقلة", "asset_facility_type:mobile_vending_site"),
        ("الحدائق", "asset_facility_type:public_park"),
        ("الشواطئ والواجهات", "asset_facility_type:waterfront"),
        ("أخرى", "asset_facility_type:other"),
        ("الاراضي", "asset_facility_type:land"),
        ("الساحات الميادين", "asset_facility_type:public_square"),
        ("المباني", "asset_facility_type:building"),
        ("الطرق والارصفة", "asset_facility_type:road_sidewalk"),
    ]
    current_aliases = {(row[0], row[1], row[2]) for row in bind.execute(sa.text("SELECT source_key,source_field,source_value FROM asset_facility_type_aliases"))}
    for value, canonical_id in aliases:
        key = ("furas", "LOCATIONTYPE", value)
        if key not in current_aliases:
            bind.execute(sa.text("INSERT INTO asset_facility_type_aliases (source_key,source_field,source_value,canonical_id) VALUES (:source,:field,:value,:canonical)"), {"source": key[0], "field": key[1], "value": key[2], "canonical": canonical_id})


def downgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "opportunity_asset_facility_types" in tables:
        op.drop_table("opportunity_asset_facility_types")
    if "asset_facility_type_aliases" in tables:
        op.drop_table("asset_facility_type_aliases")
    if "asset_facility_types" in tables:
        op.drop_table("asset_facility_types")
