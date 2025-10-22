#!/usr/bin/env python3
"""
Script to manually create a license from the existing webhook data.
This is needed because the bug prevented license creation on the first purchase.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.database.async_database import get_async_db_context
from sqlalchemy import select, text
from src.api.models.subscription_models.licenses import License, LicenseStatus
from src.api.models.user_models.users import Users


async def main():
    """Create license from webhook data."""
    async with get_async_db_context() as db:
        # Get the license_key_created webhook
        result = await db.execute(
            text("""
                SELECT id, event_name, event_id, payload
                FROM webhook_events
                WHERE event_name = 'license_key_created'
                ORDER BY created_at DESC
                LIMIT 1
            """)
        )
        webhook = result.fetchone()

        if not webhook:
            print("No license_key_created webhook found")
            return

        payload = webhook[3]
        data = payload.get("data", {})
        attributes = data.get("attributes", {})

        # Get custom_data from the order_created webhook (same order_id)
        order_id_str = str(attributes.get("order_id"))
        result_order = await db.execute(
            text("""
                SELECT payload
                FROM webhook_events
                WHERE event_name = 'order_created'
                AND payload->'data'->>'id' = :order_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"order_id": order_id_str}
        )
        order_webhook = result_order.fetchone()

        custom_data = {}
        if order_webhook:
            order_payload = order_webhook[0]
            custom_data = order_payload.get("meta", {}).get("custom_data", {})
        print(f"Custom data: {custom_data}")

        # Extract license data
        license_key = attributes.get("key")
        lemonsqueezy_license_id = data.get("id")
        lemonsqueezy_order_id = str(attributes.get("order_id"))
        product_id = str(attributes.get("product_id"))
        customer_id = str(attributes.get("customer_id"))
        user_email = attributes.get("user_email")
        user_name = attributes.get("user_name")
        status = attributes.get("status", "inactive")
        activation_limit = attributes.get("activation_limit") or 5  # Default to 5
        expires_at = attributes.get("expires_at")

        print(f"License Key: {license_key}")
        print(f"LemonSqueezy License ID: {lemonsqueezy_license_id}")
        print(f"Order ID: {lemonsqueezy_order_id}")
        print(f"Product ID: {product_id}")
        print(f"User Email: {user_email}")
        print(f"Status: {status}")
        print(f"Activation Limit: {activation_limit}")
        print()

        # Find user by custom_data user_id first, then by email
        user = None
        user_id_from_custom = custom_data.get("user_id")

        if user_id_from_custom:
            from uuid import UUID
            try:
                user_uuid = UUID(user_id_from_custom)
                stmt = select(Users).where(Users.id == user_uuid)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                if user:
                    print(f"Found user by custom_data user_id: {user.id} ({user.email})")
            except ValueError:
                pass

        if not user:
            # Try by email
            stmt = select(Users).where(Users.email == user_email)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                print(f"Found user by email: {user.id} ({user.email})")

        if not user:
            print(f"User not found with email {user_email} or custom_data user_id {user_id_from_custom}")
            return

        print(f"Found user: {user.id} ({user.email})")

        # Check if license already exists
        stmt = select(License).where(License.lemonsqueezy_order_id == lemonsqueezy_order_id)
        result = await db.execute(stmt)
        existing_license = result.scalar_one_or_none()

        if existing_license:
            print(f"License already exists: {existing_license.id}")
            return

        # Create license
        # Map status string to LicenseStatus enum
        status_map = {
            "active": LicenseStatus.ACTIVE,
            "inactive": LicenseStatus.INACTIVE,
            "expired": LicenseStatus.EXPIRED,
            "disabled": LicenseStatus.DISABLED,
        }
        license_status = status_map.get(status.lower(), LicenseStatus.INACTIVE)

        print(f"License status: {license_status} (type: {type(license_status)})")
        print(f"License status value: {license_status.value}")

        # Use raw SQL to insert to avoid enum conversion issues
        from sqlalchemy import text as sql_text
        from uuid import uuid4
        license_id = str(uuid4())

        await db.execute(
            sql_text("""
                INSERT INTO licenses (
                    id, user_id, license_key, lemonsqueezy_license_id,
                    lemonsqueezy_order_id, lemonsqueezy_product_id, product_name,
                    status, activation_email, activation_limit, activation_count,
                    activated_at, expires_at, created_at, updated_at, license_metadata
                ) VALUES (
                    :id, :user_id, :license_key, :lemonsqueezy_license_id,
                    :lemonsqueezy_order_id, :lemonsqueezy_product_id, :product_name,
                    :status::licensestatus, :activation_email, :activation_limit, :activation_count,
                    :activated_at, :expires_at, :created_at, :updated_at, :license_metadata::jsonb
                )
            """),
            {
                "id": license_id,
                "user_id": str(user.id),
                "license_key": license_key,
                "lemonsqueezy_license_id": lemonsqueezy_license_id,
                "lemonsqueezy_order_id": lemonsqueezy_order_id,
                "lemonsqueezy_product_id": product_id,
                "product_name": "License 1",
                "status": status.lower(),  # Use lowercase string
                "activation_email": user.email,
                "activation_limit": activation_limit,
                "activation_count": 0,
                "activated_at": None,
                "expires_at": None,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "license_metadata": "{}"
            }
        )

        await db.commit()

        print(f"\n✅ License created successfully!")
        print(f"License ID: {license_id}")
        print(f"License Key: {license_key}")
        print(f"Status: {status}")
        print(f"Activation Limit: {activation_limit}")


if __name__ == '__main__':
    asyncio.run(main())
