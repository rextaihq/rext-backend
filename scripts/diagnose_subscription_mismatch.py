#!/usr/bin/env python3
"""
Diagnose subscription email mismatch issue.

This script checks:
1. Which users exist with the emails in question
2. Which user owns the active subscription
3. Recent webhook events
4. Recommendations for fixing the issue
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.api.database.async_database import AsyncSessionLocal
from src.api.models.user_models.users import Users
from src.api.models.subscription_models.subscriptions import UserSubscription, SubscriptionStatus
from src.api.models.subscription_models.webhooks import WebhookEvent


async def diagnose():
    """Run diagnostic checks."""
    print("=" * 80)
    print("SUBSCRIPTION EMAIL MISMATCH DIAGNOSTIC")
    print("=" * 80)
    print()

    async with AsyncSessionLocal() as db:
        # 1. Check users with relevant emails
        print("📧 STEP 1: Checking users with relevant emails")
        print("-" * 80)

        relevant_emails = [
            "mobeen4@yopmail.com",
            "mobeenabdullah@gmail.com",
            "mobeen3@yopmail.com",
            "test-checkout@example.com",
        ]

        users_stmt = select(Users).where(Users.email.in_(relevant_emails))
        users_result = await db.execute(users_stmt)
        users = users_result.scalars().all()

        if users:
            print(f"Found {len(users)} users:")
            for user in users:
                print(f"  - {user.email} (ID: {user.id})")
        else:
            print("  ❌ No users found with these emails")
        print()

        # 2. Check active subscriptions
        print("💳 STEP 2: Checking active subscriptions")
        print("-" * 80)

        active_subs_stmt = (
            select(UserSubscription)
            .options(selectinload(UserSubscription.user), selectinload(UserSubscription.plan))
            .where(
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
            .order_by(UserSubscription.created_at.desc())
            .limit(10)
        )
        active_subs_result = await db.execute(active_subs_stmt)
        active_subs = active_subs_result.scalars().all()

        if active_subs:
            print(f"Found {len(active_subs)} active subscriptions:")
            for sub in active_subs:
                user_email = sub.user.email if sub.user else "Unknown"
                plan_name = sub.plan.name if sub.plan else "Unknown"
                ls_id = sub.lemonsqueezy_subscription_id or "N/A"
                print(f"\n  Subscription ID: {sub.id}")
                print(f"    User Email: {user_email}")
                print(f"    User ID: {sub.user_id}")
                print(f"    Plan: {plan_name}")
                print(f"    Status: {sub.status.value}")
                print(
                    f"    Billing Period: {sub.billing_period.value if sub.billing_period else 'N/A'}"
                )
                print(f"    LemonSqueezy ID: {ls_id}")
                print(f"    Created: {sub.created_at}")
        else:
            print("  ❌ No active subscriptions found")
        print()

        # 3. Check subscriptions for specific users
        print("🔍 STEP 3: Checking subscriptions for specific users")
        print("-" * 80)

        if users:
            for user in users:
                user_subs_stmt = (
                    select(UserSubscription)
                    .options(selectinload(UserSubscription.plan))
                    .where(UserSubscription.user_id == user.id)
                    .order_by(UserSubscription.created_at.desc())
                )
                user_subs_result = await db.execute(user_subs_stmt)
                user_subs = user_subs_result.scalars().all()

                if user_subs:
                    print(f"\n  {user.email} has {len(user_subs)} subscription(s):")
                    for sub in user_subs:
                        plan_name = sub.plan.name if sub.plan else "Unknown"
                        print(f"    - {plan_name} ({sub.status.value}) - Created: {sub.created_at}")
                else:
                    print(f"\n  {user.email} has no subscriptions")
        print()

        # 4. Check recent webhook events
        print("📨 STEP 4: Checking recent webhook events")
        print("-" * 80)

        webhooks_stmt = select(WebhookEvent).order_by(WebhookEvent.created_at.desc()).limit(15)
        webhooks_result = await db.execute(webhooks_stmt)
        webhooks = webhooks_result.scalars().all()

        if webhooks:
            print(f"Last {len(webhooks)} webhook events:")
            for wh in webhooks:
                status_emoji = "✅" if wh.status == "processed" else "❌"
                print(f"  {status_emoji} {wh.event_name} - {wh.status} - {wh.created_at}")
                if wh.error_message:
                    print(f"      Error: {wh.error_message[:100]}")
        else:
            print("  ❌ No webhook events found")
        print()

        # 5. Recommendations
        print("💡 RECOMMENDATIONS")
        print("=" * 80)

        # Find the most recent active subscription
        if active_subs:
            latest_sub = active_subs[0]
            user_email = latest_sub.user.email if latest_sub.user else "Unknown"
            plan_name = latest_sub.plan.name if latest_sub.plan else "Unknown"

            print("\nMost recent active subscription:")
            print(f"  Plan: {plan_name}")
            print(f"  Status: {latest_sub.status.value}")
            print(f"  Owner Email: {user_email}")
            print(f"  Owner ID: {latest_sub.user_id}")
            print()

            if user_email == "mobeen4@yopmail.com":
                print("✅ GOOD NEWS: The subscription is already assigned to mobeen4@yopmail.com")
                print("   The frontend should show the subscription when logged in as this user.")
                print()
                print("   Troubleshooting steps:")
                print("   1. Ensure you're logged in as mobeen4@yopmail.com in the frontend")
                print("   2. Clear browser cache and cookies")
                print("   3. Log out and log back in")
                print("   4. Check the /api/v1/subscriptions/status endpoint response")
            elif user_email in relevant_emails:
                print(f"⚠️  MISMATCH: The subscription is assigned to {user_email}")
                print("   But you're trying to use it with mobeen4@yopmail.com")
                print()
                print("   Solutions:")
                print(f"   1. Log in as {user_email} to see the subscription")
                print("   2. OR transfer the subscription to mobeen4@yopmail.com using SQL:")
                print()
                print("      UPDATE user_subscriptions")
                user_result = await db.execute(
                    select(Users).where(Users.email == "mobeen4@yopmail.com")
                )
                mobeen4 = user_result.scalar_one_or_none()
                if mobeen4:
                    print(f"      SET user_id = '{mobeen4.id}'")
                else:
                    print("      SET user_id = '<mobeen4_user_id>'  -- User not found!")
                print(f"      WHERE id = '{latest_sub.id}';")
            else:
                print(
                    f"⚠️  UNEXPECTED: Subscription is assigned to an unexpected user: {user_email}"
                )
                print("   Please investigate manually.")
        else:
            print("\n❌ No active subscriptions found in the database.")
            print("   This suggests the subscription creation failed or was not completed.")
            print()
            print("   Next steps:")
            print("   1. Check webhook events for errors")
            print("   2. Check LemonSqueezy dashboard for the subscription")
            print("   3. Try creating a new test checkout with matching emails")

        print()
        print("=" * 80)
        print("For more details, see: CHECKOUT_EMAIL_MISMATCH_ISSUE.md")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(diagnose())
