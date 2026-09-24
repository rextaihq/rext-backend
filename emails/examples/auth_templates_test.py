"""
Test Auth Email Templates

Tests and generates examples of all authentication email templates.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from emails.templates.auth import (
    create_password_reset_email,
    create_verification_email,
    create_welcome_email,
)


def test_verification_email():
    """Test email verification template."""
    print("1. Testing email verification template...")

    html = create_verification_email(
        user_name="John Doe",
        verification_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example.token",
        frontend_url="https://app.rext.com",
    )

    # Verify key elements
    assert "Welcome to Rext AI, John Doe!" in html
    assert "Verify Email Address" in html
    assert "verify-email?token=" in html
    assert "<!DOCTYPE html>" in html

    # Save to file
    output_path = Path(__file__).parent / "verification_email_output.html"
    with open(output_path, "w") as f:
        f.write(html)

    print("   ✓ Verification email generated")
    print(f"   ✓ Saved to: {output_path}")

    return True


def test_password_reset_email():
    """Test password reset template."""
    print("\n2. Testing password reset template...")

    html = create_password_reset_email(
        user_name="Jane Smith",
        reset_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.reset.token",
        user_email="jane@example.com",
        frontend_url="https://app.rext.com",
    )

    # Verify key elements
    assert "Reset Your Password" in html
    assert "Jane Smith" in html
    assert "jane@example.com" in html
    assert "reset-password?token=" in html
    assert "<!DOCTYPE html>" in html

    # Save to file
    output_path = Path(__file__).parent / "password_reset_email_output.html"
    with open(output_path, "w") as f:
        f.write(html)

    print("   ✓ Password reset email generated")
    print(f"   ✓ Saved to: {output_path}")

    return True


def test_welcome_email():
    """Test welcome email template."""
    print("\n3. Testing welcome email template...")

    html = create_welcome_email(user_name="Alex Johnson", frontend_url="https://app.rext.com")

    # Verify key elements
    assert "Welcome aboard, Alex Johnson!" in html
    assert "Go to Dashboard" in html
    assert "Create Your First Workspace" in html
    assert "<!DOCTYPE html>" in html

    # Save to file
    output_path = Path(__file__).parent / "welcome_email_output.html"
    with open(output_path, "w") as f:
        f.write(html)

    print("   ✓ Welcome email generated")
    print(f"   ✓ Saved to: {output_path}")

    return True


def main():
    """Run all auth template tests."""
    print("=" * 60)
    print("Auth Email Templates Test Suite")
    print("=" * 60 + "\n")

    try:
        # Test all templates
        test_verification_email()
        test_password_reset_email()
        test_welcome_email()

        print("\n" + "=" * 60)
        print("✅ All auth email templates generated successfully!")
        print("=" * 60)
        print("\n💡 Open the generated HTML files in a browser to preview:")
        print("   - verification_email_output.html")
        print("   - password_reset_email_output.html")
        print("   - welcome_email_output.html")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
