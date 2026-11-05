"""Store complete source adapter descriptions without truncation.

Revision ID: 0015_source_method_text
Revises: 0014_production_operations
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_source_method_text"
down_revision = "0014_production_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "sources",
        "extraction_method",
        existing_type=sa.String(length=80),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade():
    raise RuntimeError(
        "Forward-only migration: narrowing extraction_method could truncate source configuration."
    )
