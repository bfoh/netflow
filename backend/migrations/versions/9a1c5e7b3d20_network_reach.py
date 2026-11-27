"""after staging: devices in the network through the BFW (v95, D-125)

A system is reached on the bench or in the network; each device keeps its bench address
(management_address) and gains the network address its file gives it, and the console
speed a person chose for its console window (D-126).

Revision ID: 9a1c5e7b3d20
Revises: 4dbe2fd28d85
Create Date: 2026-11-27 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1c5e7b3d20'
down_revision: Union[str, Sequence[str], None] = '4dbe2fd28d85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('console_speed', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('network_address', sa.String(length=64), nullable=True))
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reached_via', sa.String(length=10), nullable=False,
                                      server_default='bench'))
        batch_op.add_column(sa.Column('network_gateway_id', sa.String(length=36),
                                      nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('network_gateway_id')
        batch_op.drop_column('reached_via')
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.drop_column('network_address')
        batch_op.drop_column('console_speed')
