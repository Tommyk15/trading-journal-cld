"""change execution quantity to decimal for fractional shares

Revision ID: 9ac05c1ec7e4
Revises: 74f44ed30c95
Create Date: 2025-12-18 22:15:56.593637

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ac05c1ec7e4'
down_revision: Union[str, None] = '74f44ed30c95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema.

    Change execution quantity from INTEGER to NUMERIC(12, 4) to support
    fractional shares from IBKR price improvement executions.
    """
    # PostgreSQL can cast INTEGER to NUMERIC directly
    op.alter_column('executions', 'quantity',
               existing_type=sa.Integer(),
               type_=sa.Numeric(12, 4),
               existing_nullable=False,
               postgresql_using='quantity::numeric(12,4)')


def downgrade() -> None:
    """Downgrade database schema."""
    # Note: This may lose precision for fractional quantities
    op.alter_column('executions', 'quantity',
               existing_type=sa.Numeric(12, 4),
               type_=sa.Integer(),
               existing_nullable=False,
               postgresql_using='quantity::integer')
