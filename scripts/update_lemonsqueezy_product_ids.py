#!/usr/bin/env python3
"""
Script to update subscription_plans table with LemonSqueezy product IDs.

This script updates the database with the product and variant IDs from LemonSqueezy
test store for Phase 5 testing.

Usage:
    python scripts/update_lemonsqueezy_product_ids.py
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.api.db.database import SessionLocal


PRODUCT_MAPPING = {
    'basic': {
        'lemonsqueezy_product_id': '665157',
        'lemonsqueezy_monthly_variant_id': '1049347',
        'lemonsqueezy_yearly_variant_id': '1045158',
    },
    'professional': {
        'lemonsqueezy_product_id': '667795',
        'lemonsqueezy_monthly_variant_id': '1049346',
        'lemonsqueezy_yearly_variant_id': '1049351',
    },
    # Enterprise plan will be added once created in LemonSqueezy
    # 'enterprise': {
    #     'lemonsqueezy_product_id': 'XXXXX',
    #     'lemonsqueezy_monthly_variant_id': 'XXXXX',
    #     'lemonsqueezy_yearly_variant_id': 'XXXXX',
    # },
}


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
                plan_id,
                name,
                lemonsqueezy_product_id,
                lemonsqueezy_monthly_variant_id,
                lemonsqueezy_yearly_variant_id
            FROM subscription_plans
            WHERE plan_id IN ('free', 'basic', 'professional', 'enterprise')
            ORDER BY plan_id
        """))

        rows = result.fetchall()

        if not rows:
            print("⚠ No subscription plans found in database")
            print("   Run migrations first: alembic upgrade head")
            return

        print(f"{'Plan ID':<15} {'Name':<20} {'Product ID':<12} {'Monthly Var':<12} {'Yearly Var':<12}")
        print("-" * 80)
        for row in rows:
            print(f"{row[0]:<15} {row[1]:<20} {row[2] or 'NULL':<12} {row[3] or 'NULL':<12} {row[4] or 'NULL':<12}")

        print()
        print("-" * 80)
        print()

        # Ask for confirmation
        print(f"About to update {len(PRODUCT_MAPPING)} plans with LemonSqueezy product IDs:")
        for plan_id, ids in PRODUCT_MAPPING.items():
            print(f"  - {plan_id}: product={ids['lemonsqueezy_product_id']}, "
                  f"monthly={ids['lemonsqueezy_monthly_variant_id']}, "
                  f"yearly={ids['lemonsqueezy_yearly_variant_id']}")
        print()

        response = input("Continue with update? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("❌ Update cancelled")
            return

        print()
        print("Updating plans...")
        print()

        # Update each plan
        for plan_id, ids in PRODUCT_MAPPING.items():
            try:
                # Check if plan exists
                check_result = db.execute(
                    text("SELECT COUNT(*) FROM subscription_plans WHERE plan_id = :plan_id"),
                    {"plan_id": plan_id}
                )
                count = check_result.scalar()

                if count == 0:
                    print(f"⚠ Plan '{plan_id}' not found in database, skipping")
                    continue

                # Update the plan
                db.execute(
                    text("""
                        UPDATE subscription_plans
                        SET
                            lemonsqueezy_product_id = :product_id,
                            lemonsqueezy_monthly_variant_id = :monthly_variant_id,
                            lemonsqueezy_yearly_variant_id = :yearly_variant_id
                        WHERE plan_id = :plan_id
                    """),
                    {
                        "plan_id": plan_id,
                        "product_id": ids['lemonsqueezy_product_id'],
                        "monthly_variant_id": ids['lemonsqueezy_monthly_variant_id'],
                        "yearly_variant_id": ids['lemonsqueezy_yearly_variant_id'],
                    }
                )

                print(f"✓ Updated plan '{plan_id}'")

            except Exception as e:
                print(f"✗ Failed to update plan '{plan_id}': {e}")
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
                plan_id,
                name,
                lemonsqueezy_product_id,
                lemonsqueezy_monthly_variant_id,
                lemonsqueezy_yearly_variant_id
            FROM subscription_plans
            WHERE plan_id IN ('free', 'basic', 'professional', 'enterprise')
            ORDER BY plan_id
        """))

        rows = result.fetchall()

        print(f"{'Plan ID':<15} {'Name':<20} {'Product ID':<12} {'Monthly Var':<12} {'Yearly Var':<12}")
        print("-" * 80)
        for row in rows:
            print(f"{row[0]:<15} {row[1]:<20} {row[2] or 'NULL':<12} {row[3] or 'NULL':<12} {row[4] or 'NULL':<12}")

        print()
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Verify the product IDs match those in LemonSqueezy dashboard")
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
