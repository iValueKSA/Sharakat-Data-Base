"""Persist versioned derived standardization without changing source evidence.

Revision ID: 0017_data_standardization
Revises: 0016_source_type_text
"""
from alembic import op
import sqlalchemy as sa


revision = "0017_data_standardization"
down_revision = "0016_source_type_text"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("source_opportunities")}
    if "standardized_data_json" not in columns:
        op.add_column("source_opportunities", sa.Column(
            "standardized_data_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if "standardization_version" not in columns:
        op.add_column("source_opportunities", sa.Column(
            "standardization_version", sa.String(length=40), nullable=False, server_default="0"))


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("source_opportunities")}
    if "standardization_version" in columns:
        op.drop_column("source_opportunities", "standardization_version")
    if "standardized_data_json" in columns:
        op.drop_column("source_opportunities", "standardized_data_json")
