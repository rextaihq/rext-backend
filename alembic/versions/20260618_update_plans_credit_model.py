"""update_plans_to_credit_model

Revision ID: 20260618plans
Revises: 20260618coupons
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op


revision: str = '20260618plans'
down_revision: Union[str, Sequence[str], None] = '20260618coupons'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Remove old free/trial plans ────────────────────────────────────────
    op.execute("DELETE FROM subscription_plans WHERE name IN ('free', 'trial')")

    # ── Starter (was: basic) ───────────────────────────────────────────────
    op.execute("""
        UPDATE subscription_plans SET
            name                          = 'starter',
            display_name                  = 'Starter',
            description                   = 'For freelancers and solo site owners.',
            price_monthly                 = 39.00,
            price_yearly                  = 390.00,
            credits_per_month             = 400,
            is_trial_plan                 = false,
            max_workspaces                = 1,
            max_members_per_workspace     = 5,
            max_knowledge_items           = 500,
            max_api_calls_per_month       = 5000,
            lemonsqueezy_product_id       = '665157',
            lemonsqueezy_variant_id_monthly = '1045158',
            lemonsqueezy_variant_id_yearly  = '1049350'
        WHERE name = 'basic'
    """)

    # ── Pro ────────────────────────────────────────────────────────────────
    op.execute("""
        UPDATE subscription_plans SET
            display_name                  = 'Pro',
            description                   = 'For serious SEO teams that need API access.',
            price_monthly                 = 189.00,
            price_yearly                  = 1890.00,
            credits_per_month             = 2400,
            is_trial_plan                 = false,
            max_workspaces                = 5,
            max_members_per_workspace     = 15,
            max_knowledge_items           = 5000,
            max_api_calls_per_month       = 50000,
            lemonsqueezy_product_id       = '66779',
            lemonsqueezy_variant_id_monthly = '1049346',
            lemonsqueezy_variant_id_yearly  = '1049352'
        WHERE name = 'pro'
    """)

    # ── Enterprise ─────────────────────────────────────────────────────────
    op.execute("""
        UPDATE subscription_plans SET
            display_name                  = 'Enterprise',
            description                   = 'Custom credits, SSO, SLA, dedicated support.',
            price_monthly                 = 999.00,
            price_yearly                  = 9990.00,
            credits_per_month             = NULL,
            is_trial_plan                 = false,
            max_workspaces                = -1,
            max_members_per_workspace     = -1,
            max_knowledge_items           = -1,
            max_api_calls_per_month       = -1,
            is_public                     = false
        WHERE name = 'enterprise'
    """)

    # ── Growth (new) ───────────────────────────────────────────────────────
    op.execute("""
        INSERT INTO subscription_plans (
            id, name, display_name, description,
            price_monthly, price_yearly,
            credits_per_month, is_trial_plan,
            max_workspaces, max_members_per_workspace,
            max_knowledge_items, max_api_calls_per_month,
            is_active, is_public,
            lemonsqueezy_product_id,
            lemonsqueezy_variant_id_monthly,
            lemonsqueezy_variant_id_yearly,
            lemonsqueezy_store_id,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid(),
            'growth', 'Growth', 'For small teams — most popular plan.',
            89.00, 890.00,
            1000, false,
            3, 10,
            2000, 20000,
            true, true,
            '149407', '1798598', '1798562',
            '230544',
            now(), now()
        )
        ON CONFLICT (name) DO NOTHING
    """)

    # ── Agency (new) ───────────────────────────────────────────────────────
    op.execute("""
        INSERT INTO subscription_plans (
            id, name, display_name, description,
            price_monthly, price_yearly,
            credits_per_month, is_trial_plan,
            max_workspaces, max_members_per_workspace,
            max_knowledge_items, max_api_calls_per_month,
            is_active, is_public,
            lemonsqueezy_product_id,
            lemonsqueezy_variant_id_monthly,
            lemonsqueezy_variant_id_yearly,
            lemonsqueezy_store_id,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid(),
            'agency', 'Agency', 'For agencies and white-label resellers.',
            399.00, 3990.00,
            5500, false,
            -1, -1,
            -1, -1,
            true, true,
            '1149409', '1798564', '1798605',
            '230544',
            now(), now()
        )
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM subscription_plans WHERE name IN ('growth', 'agency', 'starter')")
    op.execute("""
        UPDATE subscription_plans SET
            price_monthly = 29.99, price_yearly = 290.99,
            credits_per_month = NULL,
            lemonsqueezy_variant_id_yearly = '1049351'
        WHERE name = 'pro'
    """)
