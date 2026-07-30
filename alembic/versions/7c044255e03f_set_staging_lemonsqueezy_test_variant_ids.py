"""set_staging_lemonsqueezy_test_variant_ids

Revision ID: 7c044255e03f
Revises: 61aa75ef7abf
Create Date: 2026-07-29

Sets test-mode LemonSqueezy variant IDs on subscription_plans for
environments running in sandbox mode (staging). Guarded by
LEMONSQUEEZY_SANDBOX_MODE so this is a no-op wherever that flag is
false (main/production), preventing live variant IDs from ever being
overwritten by test-store IDs when this migration is replayed there.
"""
from typing import Sequence, Union
import os

from alembic import op

revision: str = '7c044255e03f'
down_revision: Union[str, Sequence[str], None] = '61aa75ef7abf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SANDBOX_MODE = os.getenv("LEMONSQUEEZY_SANDBOX_MODE", "true").lower() == "true"

_TEST_VARIANT_IDS = {
    "starter": ("1045158", "1049350"),
    "pro": ("1049346", "1049352"),
    "growth": ("1798598", "1798562"),
    "agency": ("1798564", "1798605"),
}


def upgrade() -> None:
    if not _SANDBOX_MODE:
        print("  - LEMONSQUEEZY_SANDBOX_MODE is false; skipping staging test variant IDs")
        return

    for plan_name, (monthly_id, yearly_id) in _TEST_VARIANT_IDS.items():
        op.execute(
            f"""
            UPDATE subscription_plans
            SET lemonsqueezy_variant_id_monthly = '{monthly_id}',
                lemonsqueezy_variant_id_yearly = '{yearly_id}'
            WHERE name = '{plan_name}'
            """
        )
    print("  - Set staging test-mode LemonSqueezy variant IDs")


def downgrade() -> None:
    if not _SANDBOX_MODE:
        return

    for plan_name in _TEST_VARIANT_IDS:
        op.execute(
            f"""
            UPDATE subscription_plans
            SET lemonsqueezy_variant_id_monthly = NULL,
                lemonsqueezy_variant_id_yearly = NULL
            WHERE name = '{plan_name}'
            """
        )
