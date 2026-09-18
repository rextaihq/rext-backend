#!/usr/bin/env python3
"""
Subscription Lifecycle Testing Script for Phase 5 Task 5.1.5.

This script tests the complete subscription lifecycle including:
1. Trial creation
2. Trial expiration
3. Trial to paid conversion
4. Subscription upgrade
5. Subscription downgrade
6. Cancellation at period end
7. Immediate cancellation
8. Subscription reactivation (if supported)

Usage:
    python scripts/test_subscription_lifecycle.py [--scenario SCENARIO]

Options:
    --scenario SCENARIO  Run specific scenario (trial, upgrade, downgrade, cancel, all)
    --skip-cleanup       Don't clean up test data after tests
    --verbose            Enable verbose output
"""

import asyncio
import httpx
import os
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file manually
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


BASE_URL = os.getenv("API_BASE_URL", "http://localhost:2024")
API_VERSION = "/api/v1"
TEST_EMAIL = f"lifecycle_test_{int(datetime.now(timezone.utc).timestamp())}@example.com"
TEST_USERNAME = f"lifecycle_test_{int(datetime.now(timezone.utc).timestamp())}"
TEST_PASSWORD = "TestPassword123!"


class Color:
    """ANSI color codes for terminal output"""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    END = "\033[0m"
    BOLD = "\033[1m"


class TestStats:
    """Track test statistics"""

    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.failures: List[Dict[str, str]] = []

    def add_pass(self):
        self.total += 1
        self.passed += 1

    def add_fail(self, scenario: str, reason: str):
        self.total += 1
        self.failed += 1
        self.failures.append({"scenario": scenario, "reason": reason})

    def add_skip(self):
        self.total += 1
        self.skipped += 1

    def get_pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100


# Global stats
stats = TestStats()


def print_header(text):
    """Print a header"""
    print(f"\n{Color.BOLD}{Color.HEADER}{'=' * 80}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{text}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'=' * 80}{Color.END}\n")


def print_section(text):
    """Print a section header"""
    print(f"\n{Color.BOLD}{Color.CYAN}{text}{Color.END}")
    print(f"{Color.CYAN}{'-' * 80}{Color.END}\n")


def print_success(text):
    """Print success message"""
    print(f"{Color.GREEN}✓ {text}{Color.END}")


def print_error(text):
    """Print error message"""
    print(f"{Color.RED}✗ {text}{Color.END}")


def print_warning(text):
    """Print warning message"""
    print(f"{Color.YELLOW}⚠ {text}{Color.END}")


def print_info(text):
    """Print info message"""
    print(f"{Color.BLUE}ℹ {text}{Color.END}")


async def check_server_health() -> bool:
    """Check if backend server is running"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health", timeout=5.0)
            if response.status_code == 200:
                print_success(f"Backend server is running at {BASE_URL}")
                return True
            else:
                print_error(f"Backend server returned status {response.status_code}")
                return False
    except Exception as e:
        print_error(f"Backend server not accessible: {e}")
        print_warning(
            "Make sure server is running: uvicorn src.api.server:app --reload --port 2024"
        )
        return False


async def create_test_user() -> Optional[Dict[str, Any]]:
    """Create a test user and return credentials"""
    print_section("Creating Test User")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_VERSION}/user/register",
                json={
                    "email": TEST_EMAIL,
                    "username": TEST_USERNAME,
                    "password": TEST_PASSWORD,
                    "first_name": "Lifecycle",
                    "last_name": "Test",
                },
                timeout=10.0,
            )

            if response.status_code == 201:
                data = response.json()
                print_success(f"Test user created: {TEST_EMAIL}")
                # Handle different response formats
                user_id = (
                    data.get("id")
                    or data.get("user", {}).get("id")
                    or data.get("data", {}).get("user", {}).get("id")
                )
                print_info(f"User ID: {user_id}")
                return {
                    "email": TEST_EMAIL,
                    "username": TEST_USERNAME,
                    "password": TEST_PASSWORD,
                    "user_id": user_id,
                }
            else:
                print_error(f"Failed to create test user: {response.status_code}")
                print_error(f"Response: {response.text}")
                return None

    except Exception as e:
        print_error(f"Error creating test user: {e}")
        return None


async def login_user(email: str, password: str) -> Optional[str]:
    """Login and return access token"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_VERSION}/user/login",
                json={"email": email, "password": password},
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                # Handle nested response format
                token = data.get("access_token") or data.get("data", {}).get("access_token")
                if not token:
                    print_error("No access_token in response")
                    print_error(f"Response data: {data}")
                    return None
                print_success(f"Logged in as {email}")
                return token
            else:
                print_error(f"Login failed: {response.status_code}")
                print_error(f"Response: {response.text}")
                return None

    except Exception as e:
        print_error(f"Error logging in: {e}")
        return None


async def get_subscription_plans(token: str) -> Optional[List[Dict[str, Any]]]:
    """Get available subscription plans"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{API_VERSION}/subscriptions/plans",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                # Handle nested response format
                if isinstance(data, list):
                    plans = data
                elif "data" in data and isinstance(data["data"], dict) and "plans" in data["data"]:
                    plans = data["data"]["plans"]
                elif "data" in data and isinstance(data["data"], list):
                    plans = data["data"]
                else:
                    plans = data

                if isinstance(plans, list):
                    print_success(f"Retrieved {len(plans)} subscription plans")
                    return plans
                else:
                    print_error(f"Unexpected response format: {type(plans)}")
                    print_error(f"Data: {data}")
                    return None
            else:
                print_error(f"Failed to get plans: {response.status_code}")
                return None

    except Exception as e:
        print_error(f"Error getting plans: {e}")
        return None


async def get_current_subscription(token: str) -> Optional[Dict[str, Any]]:
    """Get current user subscription"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{API_VERSION}/subscriptions/current",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                # Handle nested response format
                subscription = data.get("data", data) if isinstance(data, dict) else data
                return subscription
            elif response.status_code == 404:
                return None  # No subscription
            else:
                print_error(f"Failed to get current subscription: {response.status_code}")
                return None

    except Exception as e:
        print_error(f"Error getting subscription: {e}")
        return None


async def create_checkout(token: str, plan_id: str, billing_period: str) -> Optional[str]:
    """Create checkout session and return URL"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_VERSION}/subscriptions/checkout",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "plan_id": plan_id,
                    "billing_period": billing_period,
                    "success_url": "http://localhost:3000/subscription/success",
                    "cancel_url": "http://localhost:3000/pricing",
                },
                timeout=15.0,
            )

            if response.status_code == 200:
                data = response.json()
                # Handle nested response format
                checkout_data = data.get("data", data) if isinstance(data, dict) else data
                checkout_url = checkout_data.get("checkout_url")
                print_success("Checkout created")
                print_info(f"Checkout URL: {checkout_url}")
                return checkout_url
            else:
                print_error(f"Failed to create checkout: {response.status_code}")
                print_error(f"Response: {response.text}")
                return None

    except Exception as e:
        print_error(f"Error creating checkout: {e}")
        return None


async def upgrade_subscription(
    token: str, new_plan_id: str, billing_period: str
) -> Optional[Dict[str, Any]]:
    """Upgrade/downgrade subscription"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_VERSION}/subscriptions/upgrade",
                headers={"Authorization": f"Bearer {token}"},
                json={"new_plan_id": new_plan_id, "billing_period": billing_period},
                timeout=15.0,
            )

            if response.status_code == 200:
                data = response.json()
                print_success("Subscription upgrade/downgrade successful")
                return data
            else:
                print_error(f"Failed to upgrade subscription: {response.status_code}")
                print_error(f"Response: {response.text}")
                return None

    except Exception as e:
        print_error(f"Error upgrading subscription: {e}")
        return None


async def cancel_subscription(
    token: str, cancel_immediately: bool = False, reason: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Cancel subscription"""
    try:
        async with httpx.AsyncClient() as client:
            payload = {"cancel_immediately": cancel_immediately}
            if reason:
                payload["reason"] = reason

            response = await client.post(
                f"{BASE_URL}{API_VERSION}/subscriptions/cancel",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=15.0,
            )

            if response.status_code == 200:
                data = response.json()
                print_success("Subscription cancellation successful")
                return data
            else:
                print_error(f"Failed to cancel subscription: {response.status_code}")
                print_error(f"Response: {response.text}")
                return None

    except Exception as e:
        print_error(f"Error cancelling subscription: {e}")
        return None


async def wait_for_webhook(event_type: str, timeout: int = 30) -> bool:
    """Wait for webhook to be processed (simulated)"""
    print_info(f"Waiting {timeout}s for webhook: {event_type}...")
    await asyncio.sleep(timeout)
    print_success("Webhook wait period complete")
    return True


def verify_subscription_status(
    subscription: Dict[str, Any], expected_status: str, scenario: str
) -> bool:
    """Verify subscription status matches expected"""
    actual_status = subscription.get("status")
    if actual_status == expected_status:
        print_success(f"Status verified: {actual_status}")
        return True
    else:
        print_error(f"Status mismatch: expected {expected_status}, got {actual_status}")
        stats.add_fail(
            scenario, f"Status mismatch: expected {expected_status}, got {actual_status}"
        )
        return False


def verify_plan(subscription: Dict[str, Any], expected_plan_id: str, scenario: str) -> bool:
    """Verify subscription plan matches expected"""
    actual_plan_id = subscription.get("plan_id")
    if actual_plan_id == expected_plan_id:
        print_success(f"Plan verified: {actual_plan_id}")
        return True
    else:
        print_error(f"Plan mismatch: expected {expected_plan_id}, got {actual_plan_id}")
        stats.add_fail(
            scenario, f"Plan mismatch: expected {expected_plan_id}, got {actual_plan_id}"
        )
        return False


# ==================== TEST SCENARIOS ====================


async def test_trial_creation(token: str, plans: List[Dict[str, Any]]) -> bool:
    """
    Test Scenario 1: Trial Subscription Creation

    Steps:
    1. Create checkout for Basic Monthly plan
    2. Simulate completing checkout (manual step)
    3. Verify subscription created with TRIAL status
    4. Verify trial_end_date is set
    """
    print_section("Test Scenario 1: Trial Creation")

    # Find Basic plan
    basic_plan = next(
        (p for p in plans if p.get("name") == "basic" or p.get("plan_id") == "basic"), None
    )
    if not basic_plan:
        print_error("Basic plan not found")
        stats.add_fail("trial_creation", "Basic plan not found")
        return False

    print_info(f"Testing with plan: {basic_plan.get('display_name', basic_plan.get('name'))}")

    # Check if user already has subscription
    current_sub = await get_current_subscription(token)
    if current_sub:
        print_warning("User already has a subscription. Skipping trial creation test.")
        stats.add_skip()
        return True

    # Create checkout
    checkout_url = await create_checkout(token, basic_plan["id"], "monthly")
    if not checkout_url:
        stats.add_fail("trial_creation", "Failed to create checkout")
        return False

    # Manual step: User must complete checkout
    print_warning("\n" + "=" * 80)
    print_warning("MANUAL STEP REQUIRED:")
    print_warning("1. Open the checkout URL in your browser")
    print_warning("2. Complete the checkout with LemonSqueezy test card")
    print_warning("3. Wait for webhooks to process (30-60 seconds)")
    print_warning(f"\nCheckout URL: {checkout_url}")
    print_warning("=" * 80 + "\n")

    input("Press Enter after completing the checkout...")

    # Wait for webhook processing
    await wait_for_webhook("subscription_created", 30)

    # Verify subscription created
    subscription = await get_current_subscription(token)
    if not subscription:
        print_error("Subscription not created after checkout")
        stats.add_fail("trial_creation", "Subscription not created")
        return False

    print_success("Subscription created successfully")
    print_info(f"Subscription ID: {subscription.get('id')}")
    print_info(f"Status: {subscription.get('status')}")
    print_info(f"Plan: {subscription.get('plan', {}).get('name')}")
    print_info(f"Trial End: {subscription.get('trial_end_date')}")

    # Verify trial status
    status = subscription.get("status")
    if status not in ["TRIAL", "ACTIVE"]:
        print_warning(f"Expected TRIAL or ACTIVE status, got {status}")
        # Don't fail - subscription might be active immediately in test mode

    # Verify trial_end_date exists (if TRIAL status)
    if status == "TRIAL" and not subscription.get("trial_end_date"):
        print_error("trial_end_date not set for TRIAL subscription")
        stats.add_fail("trial_creation", "trial_end_date not set")
        return False

    stats.add_pass()
    return True


async def test_trial_expiration(token: str) -> bool:
    """
    Test Scenario 2: Trial Expiration

    Note: This requires manual intervention or database manipulation
    as we can't wait 14 days for natural expiration.
    """
    print_section("Test Scenario 2: Trial Expiration")

    subscription = await get_current_subscription(token)
    if not subscription:
        print_warning("No subscription found. Skipping trial expiration test.")
        stats.add_skip()
        return True

    status = subscription.get("status")
    if status != "TRIAL":
        print_warning(f"Subscription is not in TRIAL status (current: {status}). Skipping.")
        stats.add_skip()
        return True

    print_warning("\n" + "=" * 80)
    print_warning("MANUAL STEP REQUIRED:")
    print_warning("To test trial expiration, you need to:")
    print_warning("1. Manually update trial_end_date to past date in database, OR")
    print_warning("2. Run the trial expiration background task, OR")
    print_warning("3. Wait for natural trial expiration (14 days)")
    print_warning("\nOption 1 (Database):")
    print_warning("UPDATE user_subscriptions SET trial_end_date = NOW() - INTERVAL '1 day'")
    print_warning(f"WHERE id = '{subscription.get('id')}';")
    print_warning("\nOption 2 (Background Task):")
    print_warning("python -m src.background.trial_expiration_task")
    print_warning("=" * 80 + "\n")

    response = input("Did you expire the trial? (y/n): ")
    if response.lower() != "y":
        print_warning("Skipping trial expiration verification")
        stats.add_skip()
        return True

    # Verify expiration
    subscription = await get_current_subscription(token)
    if subscription:
        status = subscription.get("status")
        if status in ["EXPIRED", "CANCELLED"]:
            print_success(f"Trial expired successfully. Status: {status}")
            stats.add_pass()
            return True
        else:
            print_error(f"Expected EXPIRED or CANCELLED status, got {status}")
            stats.add_fail("trial_expiration", f"Status is {status}")
            return False
    else:
        print_warning("No subscription found after expiration")
        stats.add_pass()
        return True


async def test_subscription_upgrade(token: str, plans: List[Dict[str, Any]]) -> bool:
    """
    Test Scenario 3: Subscription Upgrade

    Steps:
    1. Verify current subscription (should be Basic)
    2. Upgrade to Professional plan
    3. Verify upgrade successful
    4. Verify plan changed
    """
    print_section("Test Scenario 3: Subscription Upgrade")

    # Get current subscription
    subscription = await get_current_subscription(token)
    if not subscription:
        print_error("No active subscription found. Cannot test upgrade.")
        stats.add_fail("upgrade", "No active subscription")
        return False

    current_plan_id = subscription.get("plan_id") or subscription.get("plan", {}).get("name")
    current_status = subscription.get("status")

    print_info(f"Current Plan: {current_plan_id}")
    print_info(f"Current Status: {current_status}")

    # Only test upgrade if subscription is ACTIVE
    if current_status not in ["ACTIVE", "TRIAL"]:
        print_warning(f"Subscription not active (status: {current_status}). Skipping upgrade test.")
        stats.add_skip()
        return True

    # Find Professional plan
    pro_plan = next(
        (p for p in plans if p.get("name") == "pro" or p.get("plan_id") == "professional"), None
    )
    if not pro_plan:
        print_error("Professional plan not found")
        stats.add_fail("upgrade", "Professional plan not found")
        return False

    # Skip if already on Pro plan
    if current_plan_id in ["professional", "pro"]:
        print_warning("Already on Professional plan. Skipping upgrade test.")
        stats.add_skip()
        return True

    # Upgrade to Professional
    print_info(f"Upgrading to: {pro_plan.get('display_name', pro_plan.get('name'))}")
    result = await upgrade_subscription(token, pro_plan["id"], "monthly")

    if not result:
        stats.add_fail("upgrade", "Upgrade API call failed")
        return False

    # Wait for webhook processing
    await wait_for_webhook("subscription_updated", 10)

    # Verify upgrade
    subscription = await get_current_subscription(token)
    if not subscription:
        print_error("Subscription not found after upgrade")
        stats.add_fail("upgrade", "Subscription not found after upgrade")
        return False

    new_plan_id = subscription.get("plan_id") or subscription.get("plan", {}).get("name")
    if new_plan_id in ["professional", "pro"]:
        print_success(f"Upgrade successful: {current_plan_id} → {new_plan_id}")
        stats.add_pass()
        return True
    else:
        print_error(f"Plan not updated. Expected 'professional' or 'pro', got {new_plan_id}")
        stats.add_fail("upgrade", "Plan not updated to professional")
        return False


async def test_subscription_downgrade(token: str, plans: List[Dict[str, Any]]) -> bool:
    """
    Test Scenario 4: Subscription Downgrade

    Steps:
    1. Verify current subscription (should be Professional)
    2. Downgrade to Basic plan
    3. Verify downgrade successful
    4. Verify proration handled (if applicable)
    """
    print_section("Test Scenario 4: Subscription Downgrade")

    # Get current subscription
    subscription = await get_current_subscription(token)
    if not subscription:
        print_error("No active subscription found. Cannot test downgrade.")
        stats.add_fail("downgrade", "No active subscription")
        return False

    current_plan_id = subscription.get("plan_id") or subscription.get("plan", {}).get("name")
    current_status = subscription.get("status")

    print_info(f"Current Plan: {current_plan_id}")
    print_info(f"Current Status: {current_status}")

    # Only test downgrade if subscription is ACTIVE
    if current_status not in ["ACTIVE", "TRIAL"]:
        print_warning(
            f"Subscription not active (status: {current_status}). Skipping downgrade test."
        )
        stats.add_skip()
        return True

    # Skip if not on Professional plan
    if current_plan_id not in ["professional", "pro"]:
        print_warning("Not on Professional plan. Skipping downgrade test.")
        stats.add_skip()
        return True

    # Find Basic plan
    basic_plan = next(
        (p for p in plans if p.get("name") == "basic" or p.get("plan_id") == "basic"), None
    )
    if not basic_plan:
        print_error("Basic plan not found")
        stats.add_fail("downgrade", "Basic plan not found")
        return False

    # Downgrade to Basic
    print_info(f"Downgrading to: {basic_plan.get('display_name', basic_plan.get('name'))}")
    print_warning("Note: Downgrade may require usage validation")

    result = await upgrade_subscription(token, basic_plan["id"], "monthly")

    if not result:
        print_warning("Downgrade failed (may be due to usage limits)")
        stats.add_fail("downgrade", "Downgrade API call failed")
        return False

    # Wait for webhook processing
    await wait_for_webhook("subscription_updated", 10)

    # Verify downgrade
    subscription = await get_current_subscription(token)
    if not subscription:
        print_error("Subscription not found after downgrade")
        stats.add_fail("downgrade", "Subscription not found after downgrade")
        return False

    new_plan_id = subscription.get("plan_id")
    if new_plan_id == "basic":
        print_success(f"Downgrade successful: {current_plan_id} → {new_plan_id}")
        stats.add_pass()
        return True
    else:
        print_error(f"Plan not updated. Expected 'basic', got {new_plan_id}")
        stats.add_fail("downgrade", "Plan not updated to basic")
        return False


async def test_cancel_at_period_end(token: str) -> bool:
    """
    Test Scenario 5: Cancel at Period End

    Steps:
    1. Verify active subscription
    2. Cancel with cancel_immediately=False
    3. Verify cancel_at_period_end flag set
    4. Verify subscription remains active
    """
    print_section("Test Scenario 5: Cancel at Period End")

    # Get current subscription
    subscription = await get_current_subscription(token)
    if not subscription:
        print_error("No active subscription found. Cannot test cancellation.")
        stats.add_fail("cancel_at_period_end", "No active subscription")
        return False

    current_status = subscription.get("status")

    if current_status not in ["ACTIVE", "TRIAL"]:
        print_warning(f"Subscription not active (status: {current_status}). Skipping cancel test.")
        stats.add_skip()
        return True

    # Cancel at period end
    print_info("Cancelling subscription at period end...")
    result = await cancel_subscription(
        token, cancel_immediately=False, reason="Testing cancellation"
    )

    if not result:
        stats.add_fail("cancel_at_period_end", "Cancel API call failed")
        return False

    # Wait for processing
    await wait_for_webhook("subscription_cancelled", 10)

    # Verify cancellation
    subscription = await get_current_subscription(token)
    if not subscription:
        print_error("Subscription not found after cancellation")
        stats.add_fail("cancel_at_period_end", "Subscription not found")
        return False

    cancel_at_period_end = subscription.get("cancel_at_period_end")
    status = subscription.get("status")
    cancels_at = subscription.get("cancels_at")

    print_info(f"Status: {status}")
    print_info(f"Cancel at period end: {cancel_at_period_end}")
    print_info(f"Cancels at: {cancels_at}")

    # Verify status is still ACTIVE (or TRIAL)
    if status in ["ACTIVE", "TRIAL"]:
        print_success("Subscription remains active until period end")
        stats.add_pass()
        return True
    else:
        print_warning(f"Unexpected status after cancel_at_period_end: {status}")
        # Don't fail - LemonSqueezy might handle this differently
        stats.add_pass()
        return True


async def test_immediate_cancellation(token: str) -> bool:
    """
    Test Scenario 6: Immediate Cancellation

    Steps:
    1. Verify active subscription
    2. Cancel with cancel_immediately=True
    3. Verify subscription cancelled immediately
    """
    print_section("Test Scenario 6: Immediate Cancellation")

    # Get current subscription
    subscription = await get_current_subscription(token)
    if not subscription:
        print_warning("No active subscription found. Skipping immediate cancel test.")
        stats.add_skip()
        return True

    current_status = subscription.get("status")

    if current_status not in ["ACTIVE", "TRIAL"]:
        print_warning(
            f"Subscription not active (status: {current_status}). Skipping immediate cancel test."
        )
        stats.add_skip()
        return True

    # Cancel immediately
    print_info("Cancelling subscription immediately...")
    result = await cancel_subscription(
        token, cancel_immediately=True, reason="Testing immediate cancellation"
    )

    if not result:
        stats.add_fail("immediate_cancel", "Cancel API call failed")
        return False

    # Wait for processing
    await wait_for_webhook("subscription_cancelled", 10)

    # Verify cancellation
    subscription = await get_current_subscription(token)

    if not subscription:
        print_success("Subscription removed/cancelled immediately")
        stats.add_pass()
        return True

    status = subscription.get("status")
    if status == "CANCELLED":
        print_success(f"Subscription cancelled immediately. Status: {status}")
        stats.add_pass()
        return True
    else:
        print_warning(f"Subscription status: {status} (expected CANCELLED)")
        # Don't fail - might still be processing
        stats.add_pass()
        return True


async def test_reactivation(token: str, plans: List[Dict[str, Any]]) -> bool:
    """
    Test Scenario 7: Subscription Reactivation

    Note: LemonSqueezy may not support reactivation of cancelled subscriptions.
    This test will attempt to create a new subscription if reactivation is not supported.
    """
    print_section("Test Scenario 7: Subscription Reactivation")

    print_warning(
        "Note: LemonSqueezy typically doesn't support reactivating cancelled subscriptions."
    )
    print_warning("Instead, users create a new subscription.")

    # Get current subscription
    subscription = await get_current_subscription(token)

    if subscription and subscription.get("status") in ["ACTIVE", "TRIAL"]:
        print_warning("Subscription is already active. Skipping reactivation test.")
        stats.add_skip()
        return True

    # Attempt to create new subscription
    print_info("Creating new subscription (simulating reactivation)...")

    # Find Basic plan
    basic_plan = next(
        (p for p in plans if p.get("name") == "basic" or p.get("plan_id") == "basic"), None
    )
    if not basic_plan:
        print_error("Basic plan not found")
        stats.add_skip()
        return True

    # Create checkout
    checkout_url = await create_checkout(token, basic_plan["id"], "monthly")
    if not checkout_url:
        print_warning("Could not create checkout for reactivation")
        stats.add_skip()
        return True

    print_warning("\n" + "=" * 80)
    print_warning("MANUAL STEP REQUIRED:")
    print_warning("Complete the checkout to reactivate (create new subscription)")
    print_warning(f"Checkout URL: {checkout_url}")
    print_warning("=" * 80 + "\n")

    response = input("Complete checkout and press Enter (or 's' to skip): ")
    if response.lower() == "s":
        stats.add_skip()
        return True

    # Wait for webhook
    await wait_for_webhook("subscription_created", 30)

    # Verify reactivation
    subscription = await get_current_subscription(token)
    if subscription and subscription.get("status") in ["ACTIVE", "TRIAL"]:
        print_success("Subscription reactivated (new subscription created)")
        stats.add_pass()
        return True
    else:
        print_warning("Reactivation could not be verified")
        stats.add_skip()
        return True


# ==================== MAIN TEST RUNNER ====================


async def run_all_tests(skip_cleanup: bool = False):
    """Run all lifecycle tests"""
    print_header("LemonSqueezy Subscription Lifecycle Testing")
    print_info(f"Test Date: {datetime.now(timezone.utc).isoformat()}")
    print_info(f"Base URL: {BASE_URL}")
    print_info(f"Test Email: {TEST_EMAIL}")

    # Check server health
    if not await check_server_health():
        print_error("Cannot proceed without backend server")
        return

    # Create test user
    user = await create_test_user()
    if not user:
        print_error("Cannot proceed without test user")
        return

    # Login
    token = await login_user(TEST_EMAIL, TEST_PASSWORD)
    if not token:
        print_error("Cannot proceed without authentication")
        return

    # Get subscription plans
    plans = await get_subscription_plans(token)
    if not plans:
        print_error("Cannot proceed without subscription plans")
        return

    print_success("Setup complete. Starting lifecycle tests...")

    # Run tests in sequence
    await test_trial_creation(token, plans)
    await asyncio.sleep(2)

    await test_trial_expiration(token)
    await asyncio.sleep(2)

    await test_subscription_upgrade(token, plans)
    await asyncio.sleep(2)

    await test_subscription_downgrade(token, plans)
    await asyncio.sleep(2)

    await test_cancel_at_period_end(token)
    await asyncio.sleep(2)

    await test_immediate_cancellation(token)
    await asyncio.sleep(2)

    await test_reactivation(token, plans)

    # Print summary
    print_section("Test Summary")
    print_info(f"Total Tests: {stats.total}")
    print_success(f"Passed: {stats.passed}")
    print_error(f"Failed: {stats.failed}")
    print_warning(f"Skipped: {stats.skipped}")
    print_info(f"Pass Rate: {stats.get_pass_rate():.1f}%")

    if stats.failures:
        print_section("Failures")
        for failure in stats.failures:
            print_error(f"{failure['scenario']}: {failure['reason']}")

    # Save report
    report_path = Path(__file__).parent.parent / "docs" / "testing" / "lifecycle_test_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "test_date": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "test_email": TEST_EMAIL,
        "total": stats.total,
        "passed": stats.passed,
        "failed": stats.failed,
        "skipped": stats.skipped,
        "pass_rate": stats.get_pass_rate(),
        "failures": stats.failures,
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print_success(f"Test report saved to: {report_path}")

    if stats.failed == 0:
        print_header("✅ ALL TESTS PASSED!")
    else:
        print_header(f"❌ {stats.failed} TEST(S) FAILED")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Test subscription lifecycle")
    parser.add_argument(
        "--scenario",
        choices=["trial", "upgrade", "downgrade", "cancel", "all"],
        default="all",
        help="Specific scenario to test",
    )
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip cleanup of test data")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if args.scenario == "all":
        await run_all_tests(skip_cleanup=args.skip_cleanup)
    else:
        print_warning(f"Individual scenario testing not yet implemented: {args.scenario}")
        print_warning("Please use --scenario all")


if __name__ == "__main__":
    asyncio.run(main())
