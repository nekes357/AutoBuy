"""add seller_nick to tmall_items

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-24 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tmall_items') as batch:
        batch.add_column(sa.Column('seller_nick', sa.String(length=128), nullable=True))
        batch.create_index('ix_tmall_items_seller_nick', ['seller_nick'])


def downgrade() -> None:
    with op.batch_alter_table('tmall_items') as batch:
        batch.drop_index('ix_tmall_items_seller_nick')
        batch.drop_column('seller_nick')
