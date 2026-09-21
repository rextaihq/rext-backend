#!/usr/bin/env python3
"""
LemonSqueezy API Key Validation Script

Validates LemonSqueezy API key by making a test API call to verify authentication.

Usage:
    # Validate key from environment
    python scripts/validate_lemonsqueezy_key.py

    # Validate specific key
    LEMONSQUEEZY_API_KEY=your_key python scripts/validate_lemonsqueezy_key.py

Exit Codes:
    0 - Key is valid
    1 - Key is invalid or error occurred
"""

import os
import sys
import httpx
from datetime import datetime
from typing import Tuple


def validate_api_key(api_key: str) -> Tuple[bool, str]:
    """
    Validate LemonSqueezy API key by calling the /users/me endpoint.

    Args:
        api_key: LemonSqueezy API key to validate

    Returns:
        Tuple of (is_valid, message)
    """
    print("🔍 Validating LemonSqueezy API key...")
    print(f"   Key prefix: {api_key[:12]}...")
    print(f"   Key length: {len(api_key)} characters")

    try:
        response = httpx.get(
            "https://api.lemonsqueezy.com/v1/users/me",
            headers={"Accept": "application/vnd.api+json", "Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )

        if response.status_code == 200:
            data = response.json()
            user_data = data.get("data", {}).get("attributes", {})
            user_name = user_data.get("name", "Unknown")
            user_email = user_data.get("email", "Unknown")

            print("\n✅ API key is VALID")
            print(f"   Authenticated as: {user_name} ({user_email})")
            print(f"   Timestamp: {datetime.now().isoformat()}")
            return True, "Valid"

        elif response.status_code == 401:
            error_msg = "401 Unauthorized - Key is invalid, revoked, or expired"
            print("\n❌ API key is INVALID")
            print(f"   Error: {error_msg}")
            return False, error_msg

        elif response.status_code == 429:
            error_msg = "429 Too Many Requests - Rate limit exceeded"
            print("\n⚠️  Rate limit exceeded")
            print(f"   Error: {error_msg}")
            print("   Try again in a few minutes")
            return False, error_msg

        else:
            error_msg = f"Unexpected status code: {response.status_code}"
            print("\n⚠️  Unexpected response")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False, error_msg

    except httpx.ConnectTimeout:
        error_msg = "Connection timeout - Check network connectivity"
        print("\n❌ Connection timeout")
        print(f"   Error: {error_msg}")
        return False, error_msg

    except httpx.HTTPError as e:
        error_msg = f"HTTP error: {str(e)}"
        print(f"\n❌ HTTP Error: {e}")
        return False, error_msg

    except Exception as e:
        error_msg = f"Validation error: {str(e)}"
        print(f"\n❌ Unexpected error: {e}")
        return False, error_msg


def check_key_format(api_key: str) -> bool:
    """
    Check if API key format looks valid (basic sanity checks).

    Args:
        api_key: API key to check

    Returns:
        True if format looks valid
    """
    issues = []

    # Check minimum length
    if len(api_key) < 20:
        issues.append(f"Key is too short ({len(api_key)} chars, expected 40+)")

    # Check for common mistakes
    if api_key.startswith(" ") or api_key.endswith(" "):
        issues.append("Key contains leading/trailing whitespace")

    if "\n" in api_key or "\r" in api_key:
        issues.append("Key contains newline characters")

    if api_key == "your_api_key_here" or api_key == "REPLACE_ME":
        issues.append("Key is a placeholder value")

    if issues:
        print("\n⚠️  Warning: Key format issues detected:")
        for issue in issues:
            print(f"   - {issue}")
        return False

    return True


def main():
    """Main validation function"""
    print("=" * 60)
    print("LemonSqueezy API Key Validator")
    print("=" * 60)

    # Get API key from environment
    api_key = os.getenv("LEMONSQUEEZY_API_KEY")

    if not api_key:
        print("\n❌ Error: LEMONSQUEEZY_API_KEY environment variable not set")
        print("\nUsage:")
        print("  export LEMONSQUEEZY_API_KEY=your_key_here")
        print("  python scripts/validate_lemonsqueezy_key.py")
        print("\nOr:")
        print("  LEMONSQUEEZY_API_KEY=your_key python scripts/validate_lemonsqueezy_key.py")
        sys.exit(1)

    # Check format first
    format_ok = check_key_format(api_key)

    if not format_ok:
        print("\n⚠️  Proceeding with validation despite format warnings...")

    # Validate key with API call
    is_valid, message = validate_api_key(api_key)

    print("\n" + "=" * 60)
    if is_valid:
        print("✅ VALIDATION SUCCESSFUL")
        print("   Key is ready for use in production")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ VALIDATION FAILED")
        print(f"   Reason: {message}")
        print("   Do NOT deploy this key to production")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
