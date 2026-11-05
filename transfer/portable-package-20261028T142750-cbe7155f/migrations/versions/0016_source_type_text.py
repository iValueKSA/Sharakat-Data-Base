"""Preserve complete source type identifiers from the SQLite database.

Revision ID: 0016_source_type_text
Revises: 0015_source_method_text
"""
from alembic import op
import sqlalchemy as sa


revision = "0016_source_type_text"
down_revision = "0015_source_method_text"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "sources",
        "source_type",
        existing_type=sa.String(length=40),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade():
    raise RuntimeError(
        "Forward-only migration: narrowing source_type could truncate source configuration."
    )
