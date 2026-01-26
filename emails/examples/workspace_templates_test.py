"""
Test Workspace Email Templates

Tests and generates examples of all workspace email templates.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from emails.templates.workspace import (
    create_workspace_invitation_email,
    create_invitation_accepted_email,
    create_role_changed_email,
    create_member_removed_email
)


def test_workspace_invitation():
    """Test workspace invitation template."""
    print("1. Testing workspace invitation template...")

    html = create_workspace_invitation_email(
        workspace_name="Acme Corporation",
        inviter_name="John Doe",
        invitation_token="abc123xyz789",
        role_name="Editor",
        expiry_days=7,
        workspace_description="A collaborative workspace for the Acme team to create and share content.",
        frontend_url="https://app.rext.com"
    )

    # Verify key elements
    assert "You've been invited to join Acme Corporation" in html
    assert "John Doe" in html
    assert "Editor" in html
    assert "invitations/accept?token=" in html
    assert "<!DOCTYPE html>" in html

    # Save to file
    output_path = Path(__file__).parent / "workspace_invitation_output.html"
    with open(output_path, "w") as f:
        f.write(html)

    print(f"   ✓ Workspace invitation generated")
    print(f"   ✓ Saved to: {output_path}")

    return True


def test_invitation_accepted():
    """Test invitation accepted template."""
    print("\n2. Testing invitation accepted template...")

    html = create_invitation_accepted_email(
        workspace_name="Acme Corporation",
        new_member_name="Jane Smith",
        new_member_email="jane@example.com",
        role_name="Editor",
        workspace_id="workspace-uuid-123",
        frontend_url="https://app.rext.com"
    )

    # Verify key elements
    assert "New member joined Acme Corporation" in html
    assert "Jane Smith" in html
    assert "jane@example.com" in html
    assert "Editor" in html
    assert "<!DOCTYPE html>" in html

    # Save to file
    output_path = Path(__file__).parent / "invitation_accepted_output.html"
    with open(output_path, "w") as f:
        f.write(html)

    print(f"   ✓ Invitation accepted notification generated")
    print(f"   ✓ Saved to: {output_path}")

    return True


def test_role_changed():
    """Test role changed template."""
    print("\n3. Testing role changed template...")

    html = create_role_changed_email(
        workspace_name="Acme Corporation",
        member_name="Alex",
        old_role_name="Viewer",
        new_role_name="Editor",
        changed_by_name="John Doe",
        workspace_id="workspace-uuid-123",
        frontend_url="https://app.rext.com"
    )

    # Verify key elements
    assert "Your role in Acme Corporation" in html
    assert "Alex" in html
    assert "Viewer" in html
    assert "Editor" in html
    assert "John Doe" in html
    assert "<!DOCTYPE html>" in html

    # Save to file
    output_path = Path(__file__).parent / "role_changed_output.html"
    with open(output_path, "w") as f:
        f.write(html)

    print(f"   ✓ Role changed notification generated")
    print(f"   ✓ Saved to: {output_path}")

    return True


def test_member_removed():
    """Test member removed template."""
    print("\n4. Testing member removed template...")

    html = create_member_removed_email(
        workspace_name="Acme Corporation",
        member_name="Bob",
        removed_by_name="John Doe",
        reason="Project concluded and access is no longer needed.",
        frontend_url="https://app.rext.com"
    )

    # Verify key elements
    assert "You've been removed from Acme Corporation" in html
    assert "Bob" in html
    assert "John Doe" in html
    assert "Project concluded" in html
    assert "<!DOCTYPE html>" in html

    # Save to file
    output_path = Path(__file__).parent / "member_removed_output.html"
    with open(output_path, "w") as f:
        f.write(html)

    print(f"   ✓ Member removed notification generated")
    print(f"   ✓ Saved to: {output_path}")

    return True


def main():
    """Run all workspace template tests."""
    print("=" * 60)
    print("Workspace Email Templates Test Suite")
    print("=" * 60 + "\n")

    try:
        # Test all templates
        test_workspace_invitation()
        test_invitation_accepted()
        test_role_changed()
        test_member_removed()

        print("\n" + "=" * 60)
        print("✅ All workspace email templates generated successfully!")
        print("=" * 60)
        print("\n💡 Open the generated HTML files in a browser to preview:")
        print("   - workspace_invitation_output.html")
        print("   - invitation_accepted_output.html")
        print("   - role_changed_output.html")
        print("   - member_removed_output.html")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
