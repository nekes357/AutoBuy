"""add tmall_items, jd_products, sync_logs.source

Revision ID: a1b2c3d4e5f6
Revises: 28d808321778
Create Date: 2026-05-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '28d808321778'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tmall_items',
        sa.Column('num_iid', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('price_cny', sa.Float(), nullable=True),
        sa.Column('price_rub', sa.Float(), nullable=True),
        sa.Column('stock', sa.Integer(), nullable=True),
        sa.Column('pic_url', sa.Text(), nullable=True),
        sa.Column('detail_url', sa.Text(), nullable=True),
        sa.Column('category_id', sa.String(length=64), nullable=True),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('num_iid'),
    )
    op.create_index('ix_tmall_items_category_id', 'tmall_items', ['category_id'], unique=False)

    op.create_table(
        'jd_products',
        sa.Column('sku_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=512), nullable=True),
        sa.Column('price_cny', sa.Float(), nullable=True),
        sa.Column('price_rub', sa.Float(), nullable=True),
        sa.Column('stock', sa.Integer(), nullable=True),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('sku_id'),
    )

    # Add source column to sync_logs (default "jd" keeps existing rows valid).
    op.add_column(
        'sync_logs',
        sa.Column('source', sa.String(length=32), nullable=False, server_default='jd'),
    )
    op.create_index('ix_sync_logs_source', 'sync_logs', ['source'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_sync_logs_source', table_name='sync_logs')
    op.drop_column('sync_logs', 'source')
    op.drop_table('jd_products')
    op.drop_index('ix_tmall_items_category_id', table_name='tmall_items')
    op.drop_table('tmall_items')
