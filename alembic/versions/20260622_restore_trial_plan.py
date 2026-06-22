"""restore_trial_plan

Revision ID: 20260622trial
Revises: 20260618plans
Create Date: 2026-06-22

Restores the trial plan removed in 20260618plans.
Trial has no LemonSqueezy IDs — it is $0, auto-assigned on signup, not purchasable.
credits_per_month = 50 (one-time allocation, ~3 articles). No monthly renewal — is_trial_plan=true skips reset.
"""
from typing import Sequence, Union
from alembic import op


revision: str = '20260622trial'
down_revision: Union[str, Sequence[str], None] = '20260618plans'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO subscription_plans (
            id, name, display_name, description,
            price_monthly, price_yearly,
            credits_per_month, is_trial_plan,
            max_workspaces, max_members_per_workspace,
            max_topics, max_knowledge_items, max_api_calls_per_month,
            is_active, is_public,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid(),
            'trial', 'Trial', '14-day free trial. Test the full pipeline before committing.',
            0.00, 0.00,
            50, true,
            1, 3,
            10, 20, 100,
            true, false,
            now(), now()
        )
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM subscription_plans WHERE name = 'trial'")
