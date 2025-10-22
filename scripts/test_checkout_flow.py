#!/usr/bin/env python3
"""
Automated checkout flow testing script for Phase 5 Task 5.1.2.

This script tests the complete checkout flow for all plan variants,
verifying checkout URL generation and providing manual testing instructions.

Usage:
    python scripts/test_checkout_flow.py
"""

import asyncio
import httpx
import os
from pathlib import Path
from datetime import datetime

# Load .env file manually
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:2024')
API_VERSION = '/api/v1'


class Color:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


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


async def check_server_health():
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
        print_warning(f"Make sure server is running: uvicorn src.api.server:app --reload --port 2024")
        return False


async def create_test_user(email: str, username: str, password: str):
    """Create a test user"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_VERSION}/user/register",
                json={
                    "email": email,
                    "username": username,
                    "password": password,
                    "confirm_password": password,
                    "first_name": "Test",
                    "last_name": "Checkout"
                },
                timeout=10.0
            )

            if response.status_code == 200 or response.status_code == 201:
                print_success(f"Test user created: {email}")
                return True
            elif response.status_code in [400, 409]:  # Bad request or conflict (duplicate)
                data = response.json()
                if "already exists" in str(data).lower() or "duplicate" in str(data).lower():
                    print_warning(f"User already exists: {email} (will use for testing)")
                    return True
                else:
                    print_error(f"Failed to create user: {data}")
                    return False
            else:
                print_error(f"Failed to create user: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        print_error(f"Error creating user: {e}")
        return False


async def login_user(email: str, password: str):
    """Login and get access token"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_VERSION}/user/login",
                json={
                    "email": email,
                    "password": password
                },
                timeout=10.0
            )

            if response.status_code == 200:
                response_data = response.json()
                # Handle nested response structure
                if 'data' in response_data:
                    data = response_data['data']
                    token = data.get('access_token')
                else:
                    token = response_data.get('access_token')

                if token:
                    print_success(f"Login successful for {email}")
                    return token
                else:
                    print_error("No access token in response")
                    print_info(f"Response: {response_data}")
                    return None
            else:
                print_error(f"Login failed: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        print_error(f"Error during login: {e}")
        return None


async def get_plan_uuid(token: str, plan_name: str):
    """Get plan UUID by name"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{API_VERSION}/plans",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )

            if response.status_code == 200:
                response_data = response.json()
                # Handle nested response
                if 'data' in response_data:
                    plans = response_data['data']
                else:
                    plans = response_data

                for plan in plans:
                    if plan.get('name') == plan_name:
                        return plan.get('id')

                print_error(f"Plan '{plan_name}' not found")
                return None
            else:
                print_error(f"Failed to fetch plans: {response.status_code}")
                return None
    except Exception as e:
        print_error(f"Error fetching plans: {e}")
        return None


async def test_checkout_variant(token: str, plan_uuid: str, plan_name: str, billing_period: str):
    """Test checkout for a specific plan variant"""
    try:

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_VERSION}/subscriptions/checkout",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "plan_id": plan_uuid,
                    "billing_period": billing_period,
                    "success_url": "http://localhost:3000/checkout/success",
                    "cancel_url": "http://localhost:3000/checkout/cancel"
                },
                timeout=10.0
            )

            if response.status_code == 200 or response.status_code == 201:
                response_data = response.json()
                # Handle nested response
                if 'data' in response_data:
                    data = response_data['data']
                else:
                    data = response_data

                checkout_url = data.get('checkout_url')
                session_id = data.get('session_id')

                if checkout_url:
                    print_success(f"Checkout URL generated for {plan_name} {billing_period}")
                    print_info(f"Session ID: {session_id}")
                    print_info(f"Checkout URL: {checkout_url}")
                    return {
                        'success': True,
                        'checkout_url': checkout_url,
                        'session_id': session_id
                    }
                else:
                    print_error("No checkout URL in response")
                    return {'success': False, 'error': 'No checkout URL'}
            else:
                print_error(f"Checkout failed: {response.status_code} - {response.text}")
                return {'success': False, 'error': response.text}
    except Exception as e:
        print_error(f"Error creating checkout: {e}")
        return {'success': False, 'error': str(e)}


async def main():
    """Main test execution"""
    print_header("LemonSqueezy Checkout Flow Testing - Phase 5 Task 5.1.2")

    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Test configuration
    TEST_EMAIL = "test-checkout@example.com"
    TEST_USERNAME = "testcheckout"
    TEST_PASSWORD = "TestPassword123!"

    # Plan UUIDs from database
    PLAN_UUIDS = {
        "basic": "fbd92e86-68f3-4e1d-9940-6b8ad57af32d",
        "pro": "d2524075-e7bc-49e1-976b-13edba978deb",
    }

    PLAN_VARIANTS = [
        {"plan_name": "basic", "billing_period": "monthly", "price": "$9.99/month"},
        {"plan_name": "basic", "billing_period": "yearly", "price": "$99.99/year"},
        {"plan_name": "pro", "billing_period": "monthly", "price": "$29.99/month"},
        {"plan_name": "pro", "billing_period": "yearly", "price": "$290.99/year"},
    ]

    # Step 1: Check server health
    print_section("Step 1: Check Backend Server")
    server_ok = await check_server_health()

    if not server_ok:
        print_error("Backend server check failed. Exiting.")
        return

    # Step 2: Create/verify test user
    print_section("Step 2: Create/Login Test User")
    user_created = await create_test_user(TEST_EMAIL, TEST_USERNAME, TEST_PASSWORD)

    if not user_created:
        print_error("Failed to create test user. Exiting.")
        return

    # Step 3: Login
    token = await login_user(TEST_EMAIL, TEST_PASSWORD)

    if not token:
        print_error("Failed to login. Exiting.")
        return

    print_info(f"Access token: {token[:30]}...")

    # Step 4: Test each checkout variant
    print_section("Step 3: Test Checkout for Each Plan Variant")

    results = []

    for variant in PLAN_VARIANTS:
        plan_name = variant['plan_name']
        billing_period = variant['billing_period']
        price = variant['price']
        plan_uuid = PLAN_UUIDS[plan_name]

        print(f"\n{Color.BOLD}Testing: {plan_name.title()} - {billing_period.title()} ({price}){Color.END}")
        print("-" * 60)

        result = await test_checkout_variant(token, plan_uuid, plan_name, billing_period)
        result['plan_name'] = plan_name
        result['billing_period'] = billing_period
        result['price'] = price
        results.append(result)

        if result['success']:
            print_success("Checkout URL generation successful")
        else:
            print_error(f"Checkout URL generation failed: {result.get('error', 'Unknown error')}")

        print()

    # Summary
    print_section("Test Summary")

    success_count = sum(1 for r in results if r['success'])
    total_count = len(results)

    print(f"Total variants tested: {total_count}")
    print(f"Successful: {Color.GREEN}{success_count}{Color.END}")
    print(f"Failed: {Color.RED}{total_count - success_count}{Color.END}")
    print()

    if success_count == total_count:
        print_success("All checkout URL generation tests passed! ✓")
    else:
        print_warning("Some tests failed. Check errors above.")

    # Manual testing instructions
    print_section("Next Steps: Manual Testing")

    print("For each successful checkout URL, complete the following manual steps:\n")
    print("1. Open the checkout URL in your browser")
    print("2. Verify correct plan and price displayed")
    print("3. Use LemonSqueezy test card:")
    print("   - Card Number: 4242 4242 4242 4242")
    print("   - Expiry: Any future date (e.g., 12/25)")
    print("   - CVC: Any 3 digits (e.g., 123)")
    print("4. Complete the checkout")
    print("5. Verify webhook received in backend logs")
    print("6. Check subscription in database:")
    print(f"   SELECT * FROM user_subscriptions")
    print(f"   WHERE user_id = (SELECT id FROM users WHERE email = '{TEST_EMAIL}')")
    print("7. Test subscription dashboard access")
    print("8. Test customer portal link")
    print()

    # Print checkout URLs for easy access
    print_section("Checkout URLs for Manual Testing")

    for idx, result in enumerate(results, 1):
        if result['success']:
            print(f"\n{idx}. {Color.BOLD}{result['plan_name'].title()} - {result['billing_period'].title()} ({result['price']}){Color.END}")
            print(f"   Session ID: {result.get('session_id', 'N/A')}")
            print(f"   {Color.CYAN}{result['checkout_url']}{Color.END}")

    print()
    print_header("Test Complete")

    print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print_info("Document your test results in:")
    print_info("  wrext-backend/docs/testing/phase5-task-5.1.2-checkout-flow-testing.md")
    print()


if __name__ == '__main__':
    asyncio.run(main())
