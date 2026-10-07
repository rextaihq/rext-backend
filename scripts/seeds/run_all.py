"""Run all seed scripts in order. Each only inserts what is missing, so this runs on every environment."""

import asyncio

from scripts.seeds.seed_api_usage_state import seed_api_usage_state
from scripts.seeds.seed_email_templates import seed_email_templates
from scripts.seeds.seed_permissions import seed_permissions
from scripts.seeds.seed_promotions import seed_promotions
from scripts.seeds.seed_subscription_plans import seed_subscription_plans
from scripts.seeds.seed_super_admin import seed_super_admin


async def run_all_seeds():
    """Run all seed scripts."""
    print("=" * 50)
    print("Running all seed scripts...")
    print("=" * 50)

    # Note: seed_permissions now includes role seeding as well
    await seed_permissions()
    await seed_email_templates()
    await seed_subscription_plans()
    await seed_promotions()
    await seed_super_admin()
    await seed_api_usage_state()

    print("=" * 50)
    print("All seeds completed.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_all_seeds())
