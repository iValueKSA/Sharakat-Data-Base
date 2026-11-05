"""Make absent investment values carry no implied currency."""
from alembic import op
import sqlalchemy as sa

revision = "0023_quant_commercial"
down_revision = "0022_status_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("opportunities", "currency", existing_type=sa.String(length=10), nullable=True)
    # Historical SAR values came from the model default, including every row
    # without an investment amount. They are not source evidence and must not
    # imply a currency for an absent amount.
    op.execute(sa.text("UPDATE opportunities SET currency = NULL WHERE investment_value IS NULL"))


def downgrade():
    op.execute(sa.text("UPDATE opportunities SET currency = 'SAR' WHERE currency IS NULL"))
    op.alter_column("opportunities", "currency", existing_type=sa.String(length=10), nullable=False)
