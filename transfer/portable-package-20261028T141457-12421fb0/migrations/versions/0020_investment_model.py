"""Add the separate canonical Investment Model Master dimension.

Revision ID: 0020_investment_model
Revises: 0019_activity_sub_activity
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_investment_model"
down_revision = "0019_activity_sub_activity"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("opportunities")}
    if "investment_model" not in columns:
        op.add_column("opportunities", sa.Column("investment_model", sa.String(length=200), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("opportunities")}
    if "investment_model" in columns:
        op.drop_column("opportunities", "investment_model")
