"""Add a separate Sub-Activity dimension while preserving source payloads.

Revision ID: 0019_activity_sub_activity
Revises: 0018_sector_activity
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_activity_sub_activity"
down_revision = "0018_sector_activity"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    master_columns = {column["name"] for column in inspector.get_columns("opportunities")}
    if "sub_activity" not in master_columns:
        op.add_column("opportunities", sa.Column("sub_activity", sa.String(length=300), nullable=True))
    source_columns = {column["name"] for column in inspector.get_columns("source_opportunities")}
    if "source_sub_activity" not in source_columns:
        op.add_column("source_opportunities", sa.Column("source_sub_activity", sa.String(length=300), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    master_columns = {column["name"] for column in inspector.get_columns("opportunities")}
    if "sub_activity" in master_columns:
        op.drop_column("opportunities", "sub_activity")
    source_columns = {column["name"] for column in inspector.get_columns("source_opportunities")}
    if "source_sub_activity" in source_columns:
        op.drop_column("source_opportunities", "source_sub_activity")
