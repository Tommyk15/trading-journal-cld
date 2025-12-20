"""add_tags_and_trade_tags_tables

Revision ID: 20251219_tags
Revises: 9ac05c1ec7e4
Create Date: 2025-12-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251219_tags'
down_revision: Union[str, None] = '9ac05c1ec7e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tags and trade_tags tables."""
    # Create tags table
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('color', sa.String(7), nullable=False, server_default='#6B7280'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_tags_name', 'tags', ['name'])

    # Create trade_tags association table
    op.create_table(
        'trade_tags',
        sa.Column('trade_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['trade_id'], ['trades.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('trade_id', 'tag_id'),
    )


def downgrade() -> None:
    """Drop tags and trade_tags tables."""
    op.drop_table('trade_tags')
    op.drop_index('ix_tags_name', 'tags')
    op.drop_table('tags')
