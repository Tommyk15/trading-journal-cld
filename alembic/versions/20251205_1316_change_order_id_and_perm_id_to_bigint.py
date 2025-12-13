"""change order_id and perm_id to bigint

Revision ID: bb32383540bd
Revises: 
Create Date: 2025-12-05 13:16:04.337291

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb32383540bd'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Change order_id and perm_id from INTEGER to BIGINT
    op.alter_column('executions', 'order_id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    op.alter_column('executions', 'perm_id',
                    existing_type=sa.INTEGER(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade database schema."""
    # Revert BIGINT back to INTEGER
    op.alter_column('executions', 'perm_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False)
    op.alter_column('executions', 'order_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.INTEGER(),
                    existing_nullable=False)
