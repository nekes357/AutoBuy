"""add catalog_watchlist

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'catalog_watchlist',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('category_name', sa.String(length=255), nullable=False),
        sa.Column('category_id', sa.String(length=64), nullable=True),
        sa.Column('query', sa.String(length=255), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('item_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_catalog_watchlist_source', 'catalog_watchlist', ['source'])
    op.create_index('ix_catalog_watchlist_enabled', 'catalog_watchlist', ['enabled'])


def downgrade() -> None:
    op.drop_index('ix_catalog_watchlist_enabled', table_name='catalog_watchlist')
    op.drop_index('ix_catalog_watchlist_source', table_name='catalog_watchlist')
    op.drop_table('catalog_watchlist')
