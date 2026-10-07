#!/usr/bin/env python3
"""
Check webhook event details to see why license wasn't created.
"""

import asyncio
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.database.async_database import get_async_db_context
from sqlalchemy import text


async def main():
    """Check webhook details."""
    async with get_async_db_context() as db:
        # Get most recent order_created webhook
        result = await db.execute(
            text("""
                SELECT id, event_name, event_id, payload, processed, error_message, created_at
                FROM webhook_events
                WHERE event_name = 'order_created'
                ORDER BY created_at DESC
                LIMIT 2
            """)
        )
        webhooks = result.fetchall()

        if webhooks:
            for wh in webhooks:
                print(f"\n{'=' * 80}")
                print(f"Webhook: {wh[1]}")
                print(f"{'=' * 80}")
                print(f"ID: {wh[0]}")
                print(f"LemonSqueezy Event ID: {wh[2]}")
                print(f"Processed: {wh[4]}")
                print(f"Error Message: {wh[5]}")
                print(f"Created: {wh[6]}")
                print("\nPayload:")
                payload = json.loads(wh[3]) if isinstance(wh[3], str) else wh[3]
                print(json.dumps(payload, indent=2))
                print()
        else:
            print("No webhooks found")


if __name__ == "__main__":
    asyncio.run(main())
