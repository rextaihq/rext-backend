"""Run all seed scripts in order."""

import asyncio

from scripts.seeds.seed_email_templates import seed_email_templates
from scripts.seeds.seed_permissions import seed_permissions


async def run_all_seeds():
    """Run all seed scripts."""
    print("=" * 50)
    print("Running all seed scripts...")
    print("=" * 50)

    await seed_email_templates()
    await seed_permissions()

    print("=" * 50)
    print("All seeds completed.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_all_seeds())
