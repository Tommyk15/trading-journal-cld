"""Add position_ledger table and roll linking fields to trades.

Revision ID: 20251212_position
Revises: 9e17b1f9d7e2
Create Date: 2025-12-12
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251212_position'
down_revision = '9e17b1f9d7e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create position_ledger table
    op.create_table(
        'position_ledger',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('underlying', sa.String(10), nullable=False, index=True),
        sa.Column('leg_key', sa.String(50), nullable=False, index=True),
        sa.Column('quantity', sa.Integer(), nullable=False, default=0),
        sa.Column('avg_cost', sa.Numeric(12, 4), default=0),
        sa.Column('total_cost', sa.Numeric(12, 2), default=0),
        sa.Column('realized_pnl', sa.Numeric(12, 2), default=0),
        sa.Column('status', sa.String(20), nullable=False, default='OPEN'),
        sa.Column('opened_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.Column('trade_id', sa.Integer(), sa.ForeignKey('trades.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Create composite index for efficient lookups
    op.create_index(
        'ix_position_ledger_underlying_leg',
        'position_ledger',
        ['underlying', 'leg_key']
    )

    # Add roll_chain_id to trades table (groups all trades in a roll sequence)
    op.add_column('trades', sa.Column('roll_chain_id', sa.Integer(), nullable=True))

    # Create index on roll_chain_id for efficient chain queries
    op.create_index('ix_trades_roll_chain_id', 'trades', ['roll_chain_id'])


def downgrade() -> None:
    # Remove roll_chain_id from trades
    op.drop_index('ix_trades_roll_chain_id', table_name='trades')
    op.drop_column('trades', 'roll_chain_id')

    # Drop position_ledger table
    op.drop_index('ix_position_ledger_underlying_leg', table_name='position_ledger')
    op.drop_table('position_ledger')
