#!/usr/bin/env python3
"""
Script to update subscription_plans table with LemonSqueezy product IDs.

This script updates the database with the product and variant IDs from LemonSqueezy
test store for Phase 5 testing.

Usage:
    python scripts/update_lemonsqueezy_product_ids.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.api.db.database import SessionLocal
from src.config.lemonsqueezy_plan_config import (
    get_configured_plan_mapping,
    get_plan_env_var_names,
)


async def update_product_ids():
    """Update subscription_plans table with LemonSqueezy product IDs."""

    print("=" * 80)
    print("Update Subscription Plans with LemonSqueezy Product IDs")
    print("=" * 80)
    print()

    db = SessionLocal()

    try:
        # First, show current state
        print("Current subscription_plans state:")
        print("-" * 80)

        result = db.execute(text("""
            SELECT
                name,
                display_name,
                lemonsqueezy_product_id,
                lemonsqueezy_variant_id_monthly,
                lemonsqueezy_variant_id_yearly
            FROM subscription_plans
            ORDER BY name
        """))

        rows = result.fetchall()

        if not rows:
            print("⚠ No subscription plans found in database")
            print("   Run migrations first: alembic upgrade head")
            return

        print(f"{'Plan':<15} {'Display Name':<20} {'Product ID':<12} {'Monthly Var':<12} {'Yearly Var':<12}")
        print("-" * 80)
        for row in rows:
            print(f"{row[0]:<15} {row[1]:<20} {row[2] or 'NULL':<12} {row[3] or 'NULL':<12} {row[4] or 'NULL':<12}")

        print()
        print("-" * 80)
        print()

        plan_names = [row[0] for row in rows if row[0] not in {"free", "trial"}]
        product_mapping = get_configured_plan_mapping(plan_names, os.environ)

        if not product_mapping:
            print("⚠ No LemonSqueezy plan IDs were found in environment variables.")
            print("   Add env vars using this pattern for each paid plan:")
            for plan_name in plan_names:
                env_names = get_plan_env_var_names(plan_name)
                print(f"   - {plan_name}: {env_names['product_id']}, {env_names['variant_id_monthly']}, {env_names['variant_id_yearly']}")
            print("   Optional store override per plan:")
            print("   - LEMONSQUEEZY_<PLAN>_STORE_ID (falls back to LEMONSQUEEZY_STORE_ID)")
            return

        # Ask for confirmation
        print(f"About to update {len(product_mapping)} plans with LemonSqueezy product IDs from environment:")
        for plan_name, ids in product_mapping.items():
            print(
                f"  - {plan_name}: product={ids.product_id}, "
                f"monthly={ids.variant_id_monthly}, "
                f"yearly={ids.variant_id_yearly}, "
                f"store={ids.store_id or 'NULL'}"
            )
        print()

        response = input("Continue with update? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("❌ Update cancelled")
            return

        print()
        print("Updating plans...")
        print()

        # Update each plan
        for plan_name, ids in product_mapping.items():
            try:
                # Check if plan exists
                check_result = db.execute(
                    text("SELECT COUNT(*) FROM subscription_plans WHERE name = :plan_name"),
                    {"plan_name": plan_name}
                )
                count = check_result.scalar()

                if count == 0:
                    print(f"⚠ Plan '{plan_name}' not found in database, skipping")
                    continue

                # Update the plan
                db.execute(
                    text("""
                        UPDATE subscription_plans
                        SET
                            lemonsqueezy_product_id = :product_id,
                            lemonsqueezy_variant_id_monthly = :monthly_variant_id,
                            lemonsqueezy_variant_id_yearly = :yearly_variant_id,
                            lemonsqueezy_store_id = :store_id,
                            provider_price_id_monthly = :monthly_variant_id,
                            provider_price_id_yearly = :yearly_variant_id
                        WHERE name = :plan_name
                    """),
                    {
                        "plan_name": plan_name,
                        "product_id": ids.product_id,
                        "monthly_variant_id": ids.variant_id_monthly,
                        "yearly_variant_id": ids.variant_id_yearly,
                        "store_id": ids.store_id,
                    }
                )

                print(f"✓ Updated plan '{plan_name}'")

            except Exception as e:
                print(f"✗ Failed to update plan '{plan_name}': {e}")
                db.rollback()
                raise

        # Commit all changes
        db.commit()
        print()
        print("✅ All plans updated successfully")
        print()

        # Show updated state
        print("Updated subscription_plans state:")
        print("-" * 80)

        result = db.execute(text("""
            SELECT
                name,
                display_name,
                lemonsqueezy_product_id,
                lemonsqueezy_variant_id_monthly,
                lemonsqueezy_variant_id_yearly
            FROM subscription_plans
            ORDER BY name
        """))

        rows = result.fetchall()

        print(f"{'Plan':<15} {'Display Name':<20} {'Product ID':<12} {'Monthly Var':<12} {'Yearly Var':<12}")
        print("-" * 80)
        for row in rows:
            print(f"{row[0]:<15} {row[1]:<20} {row[2] or 'NULL':<12} {row[3] or 'NULL':<12} {row[4] or 'NULL':<12}")

        print()
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Verify the env-based IDs match the LemonSqueezy dashboard")
        print("2. Test creating a checkout session with these variant IDs")
        print("3. Proceed to Task 5.1.2: Test complete checkout flow")
        print()

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(update_product_ids())
