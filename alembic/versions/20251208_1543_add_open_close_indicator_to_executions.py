"""add open_close_indicator to executions

Revision ID: 5173913ff512
Revises: bb32383540bd
Create Date: 2025-12-08 15:43:52.603285

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5173913ff512'
down_revision: Union[str, None] = 'bb32383540bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add open_close_indicator column to executions table
    op.add_column('executions', sa.Column('open_close_indicator', sa.String(length=1), nullable=True))


def downgrade() -> None:
    """Downgrade database schema."""
    # Remove open_close_indicator column from executions table
    op.drop_column('executions', 'open_close_indicator')
