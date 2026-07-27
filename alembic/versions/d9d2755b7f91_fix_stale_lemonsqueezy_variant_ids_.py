"""fix_stale_lemonsqueezy_variant_ids_all_plans

Revision ID: d9d2755b7f91
Revises: 20260622trial
Create Date: 2026-07-17 12:55:15.620847

Starter, Pro, Growth, and Agency plans had lemonsqueezy_product_id and
lemonsqueezy_variant_id_monthly/yearly pointing at products/variants that no
longer exist in LemonSqueezy (store 230544), causing "POST /checkouts" to
fail with a 404 on the variant relationship. Correct, live IDs were verified
directly against the LemonSqueezy API after the store's products were
recreated/restructured (Basic Plan renamed to Starter Plan, Growth plan and
Agency plan added).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd9d2755b7f91'
down_revision: Union[str, Sequence[str], None] = '20260622trial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        UPDATE subscription_plans
        SET lemonsqueezy_product_id = '941169',
            lemonsqueezy_variant_id_monthly = '1479230',
            lemonsqueezy_variant_id_yearly = '1919133'
        WHERE name = 'starter'
    """)
    op.execute("""
        UPDATE subscription_plans
        SET lemonsqueezy_product_id = '941200',
            lemonsqueezy_variant_id_monthly = '1479273',
            lemonsqueezy_variant_id_yearly = '1919173'
        WHERE name = 'pro'
    """)
    op.execute("""
        UPDATE subscription_plans
        SET lemonsqueezy_product_id = '1227486',
            lemonsqueezy_variant_id_monthly = '1919211',
            lemonsqueezy_variant_id_yearly = '1919194'
        WHERE name = 'growth'
    """)
    op.execute("""
        UPDATE subscription_plans
        SET lemonsqueezy_product_id = '1227456',
            lemonsqueezy_variant_id_monthly = '1919185',
            lemonsqueezy_variant_id_yearly = '1919146'
        WHERE name = 'agency'
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        UPDATE subscription_plans
        SET lemonsqueezy_product_id = '665157',
            lemonsqueezy_variant_id_monthly = '1045158',
            lemonsqueezy_variant_id_yearly = '1049350'
        WHERE name = 'starter'
    """)
    op.execute("""
        UPDATE subscription_plans
        SET lemonsqueezy_product_id = '66779',
            lemonsqueezy_variant_id_monthly = '1049346',
            lemonsqueezy_variant_id_yearly = '1049352'
        WHERE name = 'pro'
    """)
    op.execute("""
        UPDATE subscription_plans
        SET lemonsqueezy_product_id = '149407',
            lemonsqueezy_variant_id_monthly = '1798598',
            lemonsqueezy_variant_id_yearly = '1798562'
        WHERE name = 'growth'
    """)
    op.execute("""
        UPDATE subscription_plans
        SET lemonsqueezy_product_id = '1149409',
            lemonsqueezy_variant_id_monthly = '1798564',
            lemonsqueezy_variant_id_yearly = '1798605'
        WHERE name = 'agency'
    """)
