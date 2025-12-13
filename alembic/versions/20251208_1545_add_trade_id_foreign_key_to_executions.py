"""add trade_id foreign key to executions

Revision ID: 9e17b1f9d7e2
Revises: 5173913ff512
Create Date: 2025-12-08 15:45:46.462156

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e17b1f9d7e2'
down_revision: Union[str, None] = '5173913ff512'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add trade_id column with foreign key to trades table
    op.add_column('executions', sa.Column('trade_id', sa.Integer(), nullable=True))
    op.create_index('ix_executions_trade_id', 'executions', ['trade_id'])
    op.create_foreign_key(
        'fk_executions_trade_id_trades',
        'executions', 'trades',
        ['trade_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Remove foreign key and column
    op.drop_constraint('fk_executions_trade_id_trades', 'executions', type_='foreignkey')
    op.drop_index('ix_executions_trade_id', 'executions')
    op.drop_column('executions', 'trade_id')
