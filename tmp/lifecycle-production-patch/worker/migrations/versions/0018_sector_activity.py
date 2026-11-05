"""Add a distinct Master Activity dimension.

Revision ID: 0018_sector_activity
Revises: 0017_data_standardization
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_sector_activity"
down_revision = "0017_data_standardization"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("opportunities")}
    if "activity" not in columns:
        op.add_column("opportunities", sa.Column("activity", sa.String(length=300), nullable=True))
    source_columns = {column["name"] for column in inspector.get_columns("source_opportunities")}
    if "source_activity" not in source_columns:
        op.add_column("source_opportunities", sa.Column("source_activity", sa.String(length=300), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("opportunities")}
    if "activity" in columns:
        op.drop_column("opportunities", "activity")
    source_columns = {column["name"] for column in inspector.get_columns("source_opportunities")}
    if "source_activity" in source_columns:
        op.drop_column("source_opportunities", "source_activity")
