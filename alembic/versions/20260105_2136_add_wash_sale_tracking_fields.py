"""Add wash sale tracking fields

Revision ID: 8520352a70e3
Revises: 20251219_tags
Create Date: 2026-01-05 21:36:26.997189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8520352a70e3'
down_revision: Union[str, None] = '20251219_tags'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add wash_sale_adjustment column - first as nullable
    op.add_column('trades', sa.Column('wash_sale_adjustment', sa.Numeric(precision=12, scale=2), nullable=True))

    # Set default value for existing rows
    op.execute("UPDATE trades SET wash_sale_adjustment = 0.00 WHERE wash_sale_adjustment IS NULL")

    # Now make it NOT NULL
    op.alter_column('trades', 'wash_sale_adjustment', nullable=False)

    # Add wash_sale_from_trade_ids column (already nullable)
    op.add_column('trades', sa.Column('wash_sale_from_trade_ids', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column('trades', 'wash_sale_from_trade_ids')
    op.drop_column('trades', 'wash_sale_adjustment')
