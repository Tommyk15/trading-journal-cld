"""add_assignment_tracking_fields

Revision ID: 76552649b90a
Revises: 20251212_position
Create Date: 2025-12-13 21:02:42.391267

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76552649b90a'
down_revision: Union[str, None] = '20251212_position'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add assignment tracking fields to trades table
    op.add_column('trades', sa.Column('is_assignment', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('trades', sa.Column('assigned_from_trade_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column('trades', 'assigned_from_trade_id')
    op.drop_column('trades', 'is_assignment')
