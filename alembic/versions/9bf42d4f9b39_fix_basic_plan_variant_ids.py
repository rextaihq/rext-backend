"""fix_basic_plan_variant_ids

Revision ID: 9bf42d4f9b39
Revises: 986b51dfac84
Create Date: 2025-12-17 15:58:49.255765

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm, text


# revision identifiers, used by Alembic.
revision: str = '9bf42d4f9b39'
down_revision: Union[str, Sequence[str], None] = '986b51dfac84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix Basic plan variant IDs (swapped)."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Basic Plan IDs (Corrected)
    # Monthly: 1049347 ($9.99/mo)
    # Yearly: 1045158 ($99.99/yr)

    session.execute(
        text("""
            UPDATE subscription_plans
            SET
                lemonsqueezy_variant_id_monthly = '1049347',
                lemonsqueezy_variant_id_yearly = '1045158',
                provider_price_id_monthly = '1049347',
                provider_price_id_yearly = '1045158',
                updated_at = NOW()
            WHERE name = 'basic'
        """)
    )
    session.commit()
    print("✅ Fixed Basic plan variant IDs")


def downgrade() -> None:
    """Revert Basic plan variant IDs to incorrect values."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Revert to swapped IDs
    session.execute(
        text("""
            UPDATE subscription_plans
            SET
                lemonsqueezy_variant_id_monthly = '1045158',
                lemonsqueezy_variant_id_yearly = '1049347',
                provider_price_id_monthly = '1045158',
                provider_price_id_yearly = '1049347',
                updated_at = NOW()
            WHERE name = 'basic'
        """)
    )
    session.commit()
    print("✅ Reverted Basic plan variant IDs")
