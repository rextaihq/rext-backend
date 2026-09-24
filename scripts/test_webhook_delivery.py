#!/usr/bin/env python3
"""
Test LemonSqueezy Webhook Delivery and Processing

This script systematically tests all 12 LemonSqueezy webhook event types to verify:
1. Webhook delivery and signature verification
2. Payload parsing and processing
3. Database updates for each event type
4. Handler execution and error handling

Usage:
    python scripts/test_webhook_delivery.py [options]

Options:
    --event <type>      Test specific event type (default: all)
    --url <url>         Webhook endpoint URL (default: http://localhost:2024/api/v1/subscriptions/webhooks/lemonsqueezy)
    --secret <secret>   Webhook secret (default: from .env)
    --verbose           Show detailed output

Event Types:
    Subscription Events (9):
    - subscription_created
    - subscription_updated
    - subscription_cancelled
    - subscription_resumed
    - subscription_expired
    - subscription_paused
    - subscription_payment_success
    - subscription_payment_failed
    - subscription_payment_recovered

    Order/License Events (3):
    - order_created
    - order_refunded
    - license_key_created

Examples:
    # Test all webhook types
    python scripts/test_webhook_delivery.py

    # Test specific event type
    python scripts/test_webhook_delivery.py --event subscription_created

    # Test with custom URL
    python scripts/test_webhook_delivery.py --url https://api.example.com/webhooks/lemonsqueezy
"""

import os
import sys
import json
import hmac
import hashlib
import argparse
import requests
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_WEBHOOK_URL = "http://localhost:2024/api/v1/subscriptions/webhooks/lemonsqueezy"
DEFAULT_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET", "whsecret")

# Test subscription IDs (from Task 5.1.2)
TEST_SUBSCRIPTION_ID = "731082"  # Basic Monthly subscription from test
TEST_USER_ID = "54048b28-3012-487c-8479-1ca7ab5453c6"  # mobeen@revnix.com
TEST_CUSTOMER_ID = "3277871"
TEST_PRODUCT_ID = "665157"  # Basic Plan
TEST_VARIANT_ID = "1049347"  # Basic Monthly
TEST_ORDER_ID = "6059686"


# ============================================================================
# Webhook Payload Templates
# ============================================================================


def get_webhook_payload(event_type: str, **kwargs) -> Dict[str, Any]:
    """
    Generate webhook payload for specific event type.

    Args:
        event_type: LemonSqueezy event type
        **kwargs: Additional data to customize payload

    Returns:
        Dict containing webhook payload
    """
    timestamp = datetime.now(timezone.utc).isoformat() + "Z"

    # Common subscription attributes
    subscription_attrs = {
        "store_id": 126929,
        "customer_id": int(kwargs.get("customer_id", TEST_CUSTOMER_ID)),
        "order_id": int(kwargs.get("order_id", TEST_ORDER_ID)),
        "order_item_id": 6385234,
        "product_id": int(kwargs.get("product_id", TEST_PRODUCT_ID)),
        "variant_id": int(kwargs.get("variant_id", TEST_VARIANT_ID)),
        "product_name": kwargs.get("product_name", "Rext Basic Plan"),
        "variant_name": kwargs.get("variant_name", "Monthly"),
        "user_name": kwargs.get("user_name", "Mobeen"),
        "user_email": kwargs.get("user_email", "mobeen@revnix.com"),
        "status": kwargs.get("status", "active"),
        "status_formatted": kwargs.get("status_formatted", "Active"),
        "card_brand": "visa",
        "card_last_four": "4242",
        "pause": None,
        "cancelled": False,
        "trial_ends_at": None,
        "billing_anchor": 21,
        "urls": {
            "update_payment_method": "https://app.lemonsqueezy.com/my-orders/...",
            "customer_portal": "https://app.lemonsqueezy.com/my-orders/...",
        },
        "renews_at": kwargs.get("renews_at", "2025-11-21T00:00:00.000000Z"),
        "ends_at": kwargs.get("ends_at", None),
        "created_at": "2025-10-21T10:30:00.000000Z",
        "updated_at": timestamp,
        "test_mode": True,
    }

    # Event-specific payloads
    payloads = {
        # ===== SUBSCRIPTION EVENTS =====
        "subscription_created": {
            "meta": {
                "event_name": "subscription_created",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscriptions",
                "id": kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID),
                "attributes": {
                    **subscription_attrs,
                    "status": "active",
                    "status_formatted": "Active",
                },
                "relationships": {
                    "store": {"links": {"related": "..."}},
                    "customer": {"links": {"related": "..."}},
                    "order": {"links": {"related": "..."}},
                    "product": {"links": {"related": "..."}},
                    "variant": {"links": {"related": "..."}},
                },
            },
        },
        "subscription_updated": {
            "meta": {
                "event_name": "subscription_updated",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscriptions",
                "id": kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID),
                "attributes": {
                    **subscription_attrs,
                    "status": kwargs.get("status", "active"),
                    "variant_id": kwargs.get("new_variant_id", TEST_VARIANT_ID),
                },
            },
        },
        "subscription_cancelled": {
            "meta": {
                "event_name": "subscription_cancelled",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscriptions",
                "id": kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID),
                "attributes": {
                    **subscription_attrs,
                    "status": "cancelled",
                    "status_formatted": "Cancelled",
                    "cancelled": True,
                    "ends_at": "2025-11-21T00:00:00.000000Z",
                },
            },
        },
        "subscription_resumed": {
            "meta": {
                "event_name": "subscription_resumed",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscriptions",
                "id": kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID),
                "attributes": {
                    **subscription_attrs,
                    "status": "active",
                    "status_formatted": "Active",
                    "pause": None,
                    "cancelled": False,
                    "ends_at": None,
                },
            },
        },
        "subscription_expired": {
            "meta": {
                "event_name": "subscription_expired",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscriptions",
                "id": kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID),
                "attributes": {
                    **subscription_attrs,
                    "status": "expired",
                    "status_formatted": "Expired",
                    "ends_at": timestamp,
                },
            },
        },
        "subscription_paused": {
            "meta": {
                "event_name": "subscription_paused",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscriptions",
                "id": kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID),
                "attributes": {
                    **subscription_attrs,
                    "status": "paused",
                    "status_formatted": "Paused",
                    "pause": {"mode": "void", "resumes_at": "2025-12-21T00:00:00.000000Z"},
                },
            },
        },
        "subscription_payment_success": {
            "meta": {
                "event_name": "subscription_payment_success",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscription-invoices",
                "id": "test-invoice-123",
                "attributes": {
                    "store_id": 126929,
                    "subscription_id": int(kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID)),
                    "billing_reason": "renewal",
                    "card_brand": "visa",
                    "card_last_four": "4242",
                    "currency": "USD",
                    "currency_rate": "1.00000000",
                    "status": "paid",
                    "status_formatted": "Paid",
                    "refunded": False,
                    "refunded_at": None,
                    "subtotal": 900,
                    "discount_total": 0,
                    "tax": 0,
                    "total": 900,
                    "subtotal_usd": 900,
                    "discount_total_usd": 0,
                    "tax_usd": 0,
                    "total_usd": 900,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "test_mode": True,
                },
            },
        },
        "subscription_payment_failed": {
            "meta": {
                "event_name": "subscription_payment_failed",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscription-invoices",
                "id": "test-invoice-failed-123",
                "attributes": {
                    "store_id": 126929,
                    "subscription_id": int(kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID)),
                    "billing_reason": "renewal",
                    "card_brand": "visa",
                    "card_last_four": "4242",
                    "currency": "USD",
                    "status": "failed",
                    "status_formatted": "Failed",
                    "refunded": False,
                    "subtotal": 900,
                    "tax": 0,
                    "total": 900,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "test_mode": True,
                },
            },
        },
        "subscription_payment_recovered": {
            "meta": {
                "event_name": "subscription_payment_recovered",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "subscription-invoices",
                "id": "test-invoice-recovered-123",
                "attributes": {
                    "store_id": 126929,
                    "subscription_id": int(kwargs.get("subscription_id", TEST_SUBSCRIPTION_ID)),
                    "billing_reason": "renewal",
                    "card_brand": "visa",
                    "card_last_four": "4242",
                    "currency": "USD",
                    "status": "paid",
                    "status_formatted": "Paid",
                    "refunded": False,
                    "subtotal": 900,
                    "tax": 0,
                    "total": 900,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "test_mode": True,
                },
            },
        },
        # ===== ORDER/LICENSE EVENTS =====
        "order_created": {
            "meta": {
                "event_name": "order_created",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "orders",
                "id": str(kwargs.get("order_id", 9999999)),
                "attributes": {
                    "store_id": 126929,
                    "customer_id": int(kwargs.get("customer_id", TEST_CUSTOMER_ID)),
                    "identifier": "test-order-9999999",
                    "order_number": 12345,
                    "user_name": "Mobeen",
                    "user_email": "mobeen@revnix.com",
                    "currency": "USD",
                    "currency_rate": "1.00000000",
                    "subtotal": 29900,  # $299 for lifetime license
                    "discount_total": 0,
                    "tax": 0,
                    "total": 29900,
                    "subtotal_usd": 29900,
                    "discount_total_usd": 0,
                    "tax_usd": 0,
                    "total_usd": 29900,
                    "tax_name": "",
                    "tax_rate": "0.00",
                    "status": "paid",
                    "status_formatted": "Paid",
                    "refunded": False,
                    "refunded_at": None,
                    "subtotal_formatted": "$299.00",
                    "discount_total_formatted": "$0.00",
                    "tax_formatted": "$0.00",
                    "total_formatted": "$299.00",
                    "first_order_item": {
                        "id": 123456,
                        "order_id": int(kwargs.get("order_id", 9999999)),
                        "product_id": int(kwargs.get("product_id", TEST_PRODUCT_ID)),
                        "variant_id": int(kwargs.get("variant_id", TEST_VARIANT_ID)),
                        "product_name": "Rext Pro - Lifetime",
                        "variant_name": "Lifetime License",
                        "price": 29900,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                        "test_mode": True,
                    },
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "test_mode": True,
                },
            },
        },
        "order_refunded": {
            "meta": {
                "event_name": "order_refunded",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "orders",
                "id": str(kwargs.get("order_id", 9999999)),
                "attributes": {
                    "store_id": 126929,
                    "customer_id": int(kwargs.get("customer_id", TEST_CUSTOMER_ID)),
                    "identifier": "test-order-9999999",
                    "user_email": "mobeen@revnix.com",
                    "status": "refunded",
                    "status_formatted": "Refunded",
                    "refunded": True,
                    "refunded_at": timestamp,
                    "total": 29900,
                    "created_at": "2025-10-21T10:30:00.000000Z",
                    "updated_at": timestamp,
                    "test_mode": True,
                },
            },
        },
        "license_key_created": {
            "meta": {
                "event_name": "license_key_created",
                "webhook_id": "test-webhook",
                "custom_data": {"user_id": kwargs.get("user_id", TEST_USER_ID)},
            },
            "data": {
                "type": "license-keys",
                "id": "test-license-123",
                "attributes": {
                    "store_id": 126929,
                    "customer_id": int(kwargs.get("customer_id", TEST_CUSTOMER_ID)),
                    "order_id": int(kwargs.get("order_id", 9999999)),
                    "order_item_id": 123456,
                    "product_id": int(kwargs.get("product_id", TEST_PRODUCT_ID)),
                    "user_name": "Mobeen",
                    "user_email": "mobeen@revnix.com",
                    "key": "TEST-ABCD-1234-EFGH-5678",
                    "key_short": "TEST-ABCD-12XX-XXXX-XX78",
                    "activation_limit": 5,
                    "instances_count": 0,
                    "disabled": False,
                    "status": "active",
                    "status_formatted": "Active",
                    "expires_at": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "test_mode": True,
                },
            },
        },
    }

    payload = payloads.get(event_type)
    if not payload:
        raise ValueError(f"Unknown event type: {event_type}")

    # Override event_id if provided
    if "event_id" in kwargs:
        payload["meta"]["event_name"] = event_type

    return payload


def generate_signature(payload: bytes, secret: str) -> str:
    """
    Generate HMAC SHA-256 signature for webhook payload.

    Args:
        payload: Raw webhook payload bytes
        secret: Webhook signing secret

    Returns:
        Hex-encoded signature string
    """
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def send_webhook(
    url: str,
    event_type: str,
    secret: str,
    payload_overrides: Optional[Dict[str, Any]] = None,
    invalid_signature: bool = False,
    missing_signature: bool = False,
) -> Dict[str, Any]:
    """
    Send webhook to endpoint and return response.

    Args:
        url: Webhook endpoint URL
        event_type: LemonSqueezy event type
        secret: Webhook signing secret
        payload_overrides: Optional overrides for payload
        invalid_signature: Send invalid signature (for testing)
        missing_signature: Don't send signature header (for testing)

    Returns:
        Dict with response details
    """
    # Generate payload
    payload_data = get_webhook_payload(event_type, **(payload_overrides or {}))
    payload_bytes = json.dumps(payload_data).encode("utf-8")

    # Generate signature
    if invalid_signature:
        signature = "invalid_signature_12345678"
    elif missing_signature:
        signature = None
    else:
        signature = generate_signature(payload_bytes, secret)

    # Send request
    headers = {"Content-Type": "application/json"}

    if signature is not None:
        headers["X-Signature"] = signature

    try:
        response = requests.post(url, data=payload_bytes, headers=headers, timeout=10)

        return {
            "success": response.status_code == 200,
            "status_code": response.status_code,
            "response": response.json()
            if response.headers.get("content-type") == "application/json"
            else response.text,
            "event_type": event_type,
            "payload": payload_data,
        }

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e), "event_type": event_type}


# ============================================================================
# Test Functions
# ============================================================================


def test_all_events(url: str, secret: str, verbose: bool = False) -> List[Dict[str, Any]]:
    """
    Test all 12 webhook event types.

    Args:
        url: Webhook endpoint URL
        secret: Webhook signing secret
        verbose: Show detailed output

    Returns:
        List of test results
    """
    event_types = [
        # Subscription events
        "subscription_created",
        "subscription_updated",
        "subscription_cancelled",
        "subscription_resumed",
        "subscription_expired",
        "subscription_paused",
        "subscription_payment_success",
        "subscription_payment_failed",
        "subscription_payment_recovered",
        # Order/License events
        "order_created",
        "order_refunded",
        "license_key_created",
    ]

    results = []

    print(f"\n{'=' * 70}")
    print(f"Testing All Webhook Events ({len(event_types)} total)")
    print(f"{'=' * 70}\n")

    for i, event_type in enumerate(event_types, 1):
        print(f"[{i}/{len(event_types)}] Testing: {event_type}...", end=" ")

        result = send_webhook(url, event_type, secret)
        results.append(result)

        if result["success"]:
            print("✅ PASS")
        else:
            print(f"❌ FAIL (Status: {result.get('status_code', 'N/A')})")

        if verbose and not result["success"]:
            print(f"    Error: {result.get('response', result.get('error'))}")

    return results


def test_signature_verification(url: str, secret: str, verbose: bool = False) -> Dict[str, Any]:
    """
    Test signature verification with valid, invalid, and missing signatures.

    Args:
        url: Webhook endpoint URL
        secret: Webhook signing secret
        verbose: Show detailed output

    Returns:
        Dict with test results
    """
    print(f"\n{'=' * 70}")
    print("Testing Signature Verification")
    print(f"{'=' * 70}\n")

    results = {"valid_signature": None, "invalid_signature": None, "missing_signature": None}

    # Test 1: Valid signature (should succeed)
    print("[1/3] Testing valid signature...", end=" ")
    result = send_webhook(url, "subscription_created", secret)
    results["valid_signature"] = result

    if result["success"] and result["status_code"] == 200:
        print("✅ PASS (Accepted)")
    else:
        print(f"❌ FAIL (Expected 200, got {result.get('status_code')})")

    # Test 2: Invalid signature (should reject with 400 or 401)
    print("[2/3] Testing invalid signature...", end=" ")
    result = send_webhook(url, "subscription_created", secret, invalid_signature=True)
    results["invalid_signature"] = result

    if not result["success"] and result["status_code"] in [400, 401]:
        print(f"✅ PASS (Rejected with {result['status_code']})")
    else:
        print(f"❌ FAIL (Expected 400/401, got {result.get('status_code')})")

    # Test 3: Missing signature (should reject with 400)
    print("[3/3] Testing missing signature...", end=" ")
    result = send_webhook(url, "subscription_created", secret, missing_signature=True)
    results["missing_signature"] = result

    if not result["success"] and result["status_code"] == 400:
        print("✅ PASS (Rejected with 400)")
    else:
        print(f"❌ FAIL (Expected 400, got {result.get('status_code')})")

    return results


def test_idempotency(url: str, secret: str, verbose: bool = False) -> Dict[str, Any]:
    """
    Test idempotency by sending the same event twice.

    Args:
        url: Webhook endpoint URL
        secret: Webhook signing secret
        verbose: Show detailed output

    Returns:
        Dict with test results
    """
    print(f"\n{'=' * 70}")
    print("Testing Idempotency (Duplicate Events)")
    print(f"{'=' * 70}\n")

    event_id = f"idempotency_test_{int(datetime.now(timezone.utc).timestamp())}"

    # Send first webhook
    print("[1/2] Sending webhook first time...", end=" ")
    result1 = send_webhook(
        url, "subscription_payment_success", secret, payload_overrides={"event_id": event_id}
    )

    if result1["success"]:
        print("✅ PASS (Processed)")
    else:
        print(f"❌ FAIL (Status: {result1.get('status_code')})")

    # Send duplicate webhook
    print("[2/2] Sending duplicate webhook...", end=" ")
    result2 = send_webhook(
        url, "subscription_payment_success", secret, payload_overrides={"event_id": event_id}
    )

    if result2["success"]:
        print("✅ PASS (Accepted - should be deduplicated)")
        if verbose:
            print(f"    Response: {result2.get('response')}")
    else:
        print(f"❌ FAIL (Status: {result2.get('status_code')})")

    return {
        "first_send": result1,
        "duplicate_send": result2,
        "idempotency_working": result1["success"] and result2["success"],
    }


# ============================================================================
# Main Function
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Test LemonSqueezy webhook delivery and processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test all webhook types
    python scripts/test_webhook_delivery.py

    # Test specific event type
    python scripts/test_webhook_delivery.py --event subscription_created

    # Test with verbose output
    python scripts/test_webhook_delivery.py --verbose

    # Test signature verification only
    python scripts/test_webhook_delivery.py --test-signature

    # Test idempotency only
    python scripts/test_webhook_delivery.py --test-idempotency
        """,
    )

    parser.add_argument("--event", type=str, help="Test specific event type (default: all)")

    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_WEBHOOK_URL,
        help=f"Webhook endpoint URL (default: {DEFAULT_WEBHOOK_URL})",
    )

    parser.add_argument(
        "--secret",
        type=str,
        default=DEFAULT_SECRET,
        help="Webhook signing secret (default: from .env)",
    )

    parser.add_argument("--verbose", action="store_true", help="Show detailed output")

    parser.add_argument(
        "--test-signature", action="store_true", help="Test signature verification only"
    )

    parser.add_argument("--test-idempotency", action="store_true", help="Test idempotency only")

    args = parser.parse_args()

    print(f"\n{'=' * 70}")
    print("LemonSqueezy Webhook Testing Tool")
    print(f"{'=' * 70}")
    print(f"Webhook URL: {args.url}")
    print(f"Secret: {'*' * len(args.secret)}")
    print(f"{'=' * 70}")

    all_results = {}

    # Test specific event
    if args.event:
        print(f"\nTesting single event: {args.event}")
        result = send_webhook(args.url, args.event, args.secret)
        all_results["single_event"] = result

        if result["success"]:
            print(f"✅ SUCCESS: {args.event} processed")
        else:
            print(f"❌ FAILED: {args.event}")
            print(f"Status: {result.get('status_code')}")
            print(f"Response: {result.get('response', result.get('error'))}")

    # Test signature verification
    elif args.test_signature:
        all_results["signature_tests"] = test_signature_verification(
            args.url, args.secret, args.verbose
        )

    # Test idempotency
    elif args.test_idempotency:
        all_results["idempotency_test"] = test_idempotency(args.url, args.secret, args.verbose)

    # Test all events
    else:
        all_results["all_events"] = test_all_events(args.url, args.secret, args.verbose)

        all_results["signature_tests"] = test_signature_verification(
            args.url, args.secret, args.verbose
        )

        all_results["idempotency_test"] = test_idempotency(args.url, args.secret, args.verbose)

    # Print summary
    print(f"\n{'=' * 70}")
    print("Test Summary")
    print(f"{'=' * 70}\n")

    if "all_events" in all_results:
        total = len(all_results["all_events"])
        passed = sum(1 for r in all_results["all_events"] if r["success"])
        print(f"All Events Test: {passed}/{total} passed")

    if "signature_tests" in all_results:
        sig_tests = all_results["signature_tests"]
        valid_ok = sig_tests["valid_signature"]["success"]
        invalid_rejected = not sig_tests["invalid_signature"]["success"] and sig_tests[
            "invalid_signature"
        ]["status_code"] in [400, 401]
        missing_rejected = (
            not sig_tests["missing_signature"]["success"]
            and sig_tests["missing_signature"]["status_code"] == 400
        )

        sig_passed = sum([valid_ok, invalid_rejected, missing_rejected])
        print(f"Signature Tests: {sig_passed}/3 passed")
        print(f"  - Valid signature accepted: {'✅' if valid_ok else '❌'}")
        print(f"  - Invalid signature rejected: {'✅' if invalid_rejected else '❌'}")
        print(f"  - Missing signature rejected: {'✅' if missing_rejected else '❌'}")

    if "idempotency_test" in all_results:
        idem_working = all_results["idempotency_test"]["idempotency_working"]
        print(f"Idempotency Test: {'✅ PASS' if idem_working else '❌ FAIL'}")

    print(f"\n{'=' * 70}\n")

    # Save detailed results to file
    results_file = Path(__file__).parent.parent / "docs" / "testing" / "webhook_test_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)

    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"Detailed results saved to: {results_file}\n")

    return 0 if all(r.get("success", False) for r in all_results.get("all_events", [])) else 1


if __name__ == "__main__":
    sys.exit(main())
