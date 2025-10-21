#!/usr/bin/env python3
"""
Quick script to check licenses in database.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.database.async_database import get_async_db_context
from sqlalchemy import select, text
from src.api.models.subscription_models.licenses import License


async def main():
    """Check licenses in database."""
    async with get_async_db_context() as db:
        # Get all licenses
        result = await db.execute(
            select(License).order_by(License.created_at.desc()).limit(10)
        )
        licenses = result.scalars().all()

        if licenses:
            print(f"\nFound {len(licenses)} license(s):\n")
            for lic in licenses:
                print(f"License ID: {lic.id}")
                print(f"  Key: {lic.license_key}")
                print(f"  Product: {lic.product_name}")
                print(f"  Status: {lic.status.value}")
                print(f"  User ID: {lic.user_id}")
                print(f"  Activation Limit: {lic.activation_limit}")
                print(f"  Activation Count: {lic.activation_count}")
                print(f"  Created: {lic.created_at}")
                print()
        else:
            print("\nNo licenses found in database\n")

            # Check webhook events for order_created
            result = await db.execute(
                text("""
                    SELECT event_name, processed, created_at, error_message
                    FROM webhook_events
                    WHERE event_name IN ('order_created', 'license_key_created')
                    ORDER BY created_at DESC
                    LIMIT 5
                """)
            )
            webhooks = result.fetchall()

            if webhooks:
                print("Recent order/license webhooks:")
                for wh in webhooks:
                    print(f"  {wh[0]}: Processed={wh[1]}, Created={wh[2]}")
                    if wh[3]:
                        print(f"    Error: {wh[3]}")
                print()
            else:
                print("No order/license webhooks found")
                print()

            # Check all recent webhook events
            result = await db.execute(
                text("""
                    SELECT event_name, processed, created_at
                    FROM webhook_events
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
            )
            all_webhooks = result.fetchall()

            if all_webhooks:
                print("Recent webhook events (all types):")
                for wh in all_webhooks:
                    print(f"  {wh[0]}: Processed={wh[1]}, Created={wh[2]}")
            else:
                print("No webhook events found at all")


if __name__ == '__main__':
    asyncio.run(main())
