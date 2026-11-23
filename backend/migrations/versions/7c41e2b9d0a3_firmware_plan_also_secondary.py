"""firmware plan also writes the secondary image

Revision ID: 7c41e2b9d0a3
Revises: 2d2a9e50b52a
Create Date: 2026-11-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c41e2b9d0a3'
down_revision: Union[str, Sequence[str], None] = '2d2a9e50b52a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('deployments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('also_secondary', sa.Boolean(), server_default=sa.false(),
                                      nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('deployments', schema=None) as batch_op:
        batch_op.drop_column('also_secondary')
