"""add jd_union_products

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'jd_union_products',
        sa.Column('sku_id', sa.String(length=64), nullable=False),
        sa.Column('sku_name', sa.String(length=512), nullable=True),
        sa.Column('price_cny', sa.Float(), nullable=True),
        sa.Column('price_rub', sa.Float(), nullable=True),
        sa.Column('lowest_price_cny', sa.Float(), nullable=True),
        sa.Column('brand_name', sa.String(length=255), nullable=True),
        sa.Column('shop_id', sa.String(length=64), nullable=True),
        sa.Column('shop_name', sa.String(length=255), nullable=True),
        sa.Column('category_id', sa.String(length=64), nullable=True),
        sa.Column('category_name', sa.String(length=255), nullable=True),
        sa.Column('material_url', sa.Text(), nullable=True),
        sa.Column('main_image_url', sa.Text(), nullable=True),
        sa.Column('commission', sa.Float(), nullable=True),
        sa.Column('commission_share', sa.Float(), nullable=True),
        sa.Column('in_order_count_30d', sa.Integer(), nullable=True),
        sa.Column('ware_qd', sa.Text(), nullable=True),
        sa.Column('wdesc', sa.Text(), nullable=True),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('sku_id'),
    )


def downgrade() -> None:
    op.drop_table('jd_union_products')
