"""
Syncs subscription_plans LemonSqueezy product/variant/store IDs from
environment variables into the database.

This runs once on every application startup (see src/api/server.py lifespan).
It replaces the old approach of baking IDs into one-time Alembic data
migrations, which caused stage's test-mode IDs to get hardcoded into
migrations that then ran identically against production. With this sync,
changing an env var and redeploying is sufficient in any environment -
no new migration is ever needed for a plan ID change.

Plans not fully configured in the current environment are skipped (logged),
never treated as a fatal startup error - a plan simply isn't purchasable
via checkout until its env vars are set.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.plans import SubscriptionPlan
from src.config.lemonsqueezy_plan_config import get_plan_config_from_env
from src.utils.logger import logger

# Plans that are sold through LemonSqueezy. Free/trial plans have no
# provider-side product, so they're intentionally excluded.
PAID_PLAN_NAMES = ("starter", "growth", "pro", "agency")


async def sync_lemonsqueezy_plan_ids(session: AsyncSession) -> dict[str, bool]:
    """
    Upsert each paid plan's LemonSqueezy IDs from env vars into its DB row.

    Returns a mapping of plan_name -> whether it was synced (True) or
    skipped due to incomplete env config (False). Plans that don't exist
    in the DB yet are silently omitted from the result.
    """
    result: dict[str, bool] = {}

    for plan_name in PAID_PLAN_NAMES:
        plan_row = (
            await session.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.name == plan_name)
            )
        ).scalar_one_or_none()

        if plan_row is None:
            logger.warning(f"LemonSqueezy plan sync: plan '{plan_name}' not found in DB, skipping")
            continue

        config = get_plan_config_from_env(plan_name)

        if not config.is_configured:
            logger.warning(
                f"LemonSqueezy plan sync: '{plan_name}' has no complete env configuration "
                f"(product/variant IDs) - checkout for this plan will fail until "
                f"LEMONSQUEEZY_{plan_name.upper()}_* env vars are set"
            )
            result[plan_name] = False
            continue

        plan_row.lemonsqueezy_product_id = config.product_id
        plan_row.lemonsqueezy_variant_id_monthly = config.variant_id_monthly
        plan_row.lemonsqueezy_variant_id_yearly = config.variant_id_yearly
        if config.store_id:
            plan_row.lemonsqueezy_store_id = config.store_id
        plan_row.provider_price_id_monthly = config.variant_id_monthly
        plan_row.provider_price_id_yearly = config.variant_id_yearly

        result[plan_name] = True

    synced = [name for name, ok in result.items() if ok]
    skipped = [name for name, ok in result.items() if not ok]
    logger.info(
        f"LemonSqueezy plan sync complete: synced={synced or 'none'} skipped={skipped or 'none'}"
    )

    return result
