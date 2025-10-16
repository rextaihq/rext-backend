#!/usr/bin/env python3
"""
JWT Secret Key Generator

Generates cryptographically secure secret keys for JWT token signing.
Use this script to generate values for SECRET_KEY and REFRESH_SECRET_KEY
in your .env file.

Usage:
    python scripts/generate_jwt_secret.py

Security Notes:
    - Keys are generated using secrets.token_urlsafe() (cryptographically secure)
    - Default length is 64 bytes (provides 256+ bits of entropy)
    - Store keys securely in .env file (never commit to git)
    - Use different keys for SECRET_KEY and REFRESH_SECRET_KEY
    - Rotate keys periodically (see docs/security/key-rotation.md)
"""

import secrets
import sys


def generate_secret(length: int = 64) -> str:
    """
    Generate a cryptographically strong secret key.

    Args:
        length: Number of bytes to generate (default: 64)

    Returns:
        A URL-safe base64-encoded random string

    Examples:
        >>> key = generate_secret()
        >>> len(key) >= 64  # At least 64 characters
        True
    """
    return secrets.token_urlsafe(length)


def main():
    """Generate and display JWT secret keys."""
    print("=" * 80)
    print("JWT Secret Key Generator")
    print("=" * 80)
    print()
    print("Generated SECRET_KEY (copy to .env):")
    print("-" * 80)
    secret_key = generate_secret()
    print(f"SECRET_KEY={secret_key}")
    print()

    print("Generated REFRESH_SECRET_KEY (copy to .env):")
    print("-" * 80)
    refresh_key = generate_secret()
    print(f"REFRESH_SECRET_KEY={refresh_key}")
    print()

    print("=" * 80)
    print("IMPORTANT SECURITY REMINDERS:")
    print("=" * 80)
    print("✓ Copy both keys to your .env file")
    print("✓ NEVER commit .env to version control")
    print("✓ Use DIFFERENT keys for production and development")
    print("✓ Rotate keys periodically (see docs/security/key-rotation.md)")
    print("✓ If keys are compromised, regenerate immediately and update all deployments")
    print()
    print("Next steps:")
    print("1. Copy the keys above to your .env file")
    print("2. Restart your application to load the new keys")
    print("3. Verify application starts without validation errors")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nKey generation cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError generating keys: {e}", file=sys.stderr)
        sys.exit(1)
