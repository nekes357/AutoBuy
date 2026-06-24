"""add stock columns + catalog check tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-24 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stock fields on the curated catalog.
    with op.batch_alter_table('jd_union_products') as batch:
        batch.add_column(sa.Column('in_stock', sa.Boolean(), nullable=True))
        batch.add_column(sa.Column('stock_state', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('stock_num', sa.Integer(), nullable=True))

    op.create_table(
        'jd_union_catalog_checks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('with_sku', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('not_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('no_sku', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'jd_union_catalog_check_rows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('check_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.String(length=64), nullable=True),
        sa.Column('name', sa.String(length=512), nullable=True),
        sa.Column('sku_id', sa.String(length=64), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('found', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('jd_name', sa.String(length=512), nullable=True),
        sa.Column('price_cny', sa.Float(), nullable=True),
        sa.Column('price_rub', sa.Float(), nullable=True),
        sa.Column('commission', sa.Float(), nullable=True),
        sa.Column('commission_share', sa.Float(), nullable=True),
        sa.Column('in_stock', sa.Boolean(), nullable=True),
        sa.Column('stock_num', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_jd_union_catalog_check_rows_check_id',
                    'jd_union_catalog_check_rows', ['check_id'])
    op.create_index('ix_jd_union_catalog_check_rows_sku_id',
                    'jd_union_catalog_check_rows', ['sku_id'])


def downgrade() -> None:
    op.drop_index('ix_jd_union_catalog_check_rows_sku_id',
                  table_name='jd_union_catalog_check_rows')
    op.drop_index('ix_jd_union_catalog_check_rows_check_id',
                  table_name='jd_union_catalog_check_rows')
    op.drop_table('jd_union_catalog_check_rows')
    op.drop_table('jd_union_catalog_checks')
    with op.batch_alter_table('jd_union_products') as batch:
        batch.drop_column('stock_num')
        batch.drop_column('stock_state')
        batch.drop_column('in_stock')
