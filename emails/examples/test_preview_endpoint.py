"""
Test Email Preview Endpoint

Example script showing how to use the email preview API endpoints.
"""
import requests
import json
from pathlib import Path


# Configuration
API_BASE_URL = "http://localhost:8000/api/v1/email/preview"
# Note: You'll need a valid auth token - get it from your frontend or login endpoint
AUTH_TOKEN = "your_auth_token_here"


def test_auth_email_previews():
    """Test auth email preview endpoints."""
    print("Testing Auth Email Previews")
    print("=" * 60)

    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }

    # Test 1: Email Verification
    print("\n1. Testing email verification preview...")
    response = requests.post(
        f"{API_BASE_URL}/auth",
        headers=headers,
        json={
            "template_type": "verification",
            "user_name": "John Doe",
            "token": "test_token_123"
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Subject: {data['subject']}")
        print(f"   ✓ Size: {data['metadata']['size_bytes']} bytes")

        # Save HTML
        output_path = Path(__file__).parent / "api_verification_preview.html"
        with open(output_path, "w") as f:
            f.write(data['html'])
        print(f"   ✓ Saved to: {output_path}")
    else:
        print(f"   ✗ Error: {response.status_code} - {response.text}")

    # Test 2: Password Reset
    print("\n2. Testing password reset preview...")
    response = requests.post(
        f"{API_BASE_URL}/auth",
        headers=headers,
        json={
            "template_type": "password_reset",
            "user_name": "Jane Smith",
            "user_email": "jane@example.com",
            "token": "reset_token_456"
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Subject: {data['subject']}")
        print(f"   ✓ Size: {data['metadata']['size_bytes']} bytes")
    else:
        print(f"   ✗ Error: {response.status_code}")

    # Test 3: Welcome Email
    print("\n3. Testing welcome email preview...")
    response = requests.post(
        f"{API_BASE_URL}/auth",
        headers=headers,
        json={
            "template_type": "welcome",
            "user_name": "Alex"
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Subject: {data['subject']}")
        print(f"   ✓ Size: {data['metadata']['size_bytes']} bytes")
    else:
        print(f"   ✗ Error: {response.status_code}")


def test_workspace_email_previews():
    """Test workspace email preview endpoints."""
    print("\n\nTesting Workspace Email Previews")
    print("=" * 60)

    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }

    # Test 1: Workspace Invitation
    print("\n1. Testing workspace invitation preview...")
    response = requests.post(
        f"{API_BASE_URL}/workspace",
        headers=headers,
        json={
            "template_type": "invitation",
            "workspace_name": "Acme Corporation",
            "user_name": "John Doe",
            "role_name": "Editor",
            "expiry_days": 7,
            "workspace_description": "Our main workspace for content creation"
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Subject: {data['subject']}")
        print(f"   ✓ Size: {data['metadata']['size_bytes']} bytes")

        # Save HTML
        output_path = Path(__file__).parent / "api_workspace_invitation_preview.html"
        with open(output_path, "w") as f:
            f.write(data['html'])
        print(f"   ✓ Saved to: {output_path}")
    else:
        print(f"   ✗ Error: {response.status_code} - {response.text}")

    # Test 2: Invitation Accepted
    print("\n2. Testing invitation accepted preview...")
    response = requests.post(
        f"{API_BASE_URL}/workspace",
        headers=headers,
        json={
            "template_type": "invitation_accepted",
            "workspace_name": "Acme Corporation",
            "user_name": "New Member",
            "secondary_user_name": "Jane Smith",
            "user_email": "jane@example.com",
            "role_name": "Editor"
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Subject: {data['subject']}")
        print(f"   ✓ Size: {data['metadata']['size_bytes']} bytes")
    else:
        print(f"   ✗ Error: {response.status_code}")

    # Test 3: Role Changed
    print("\n3. Testing role changed preview...")
    response = requests.post(
        f"{API_BASE_URL}/workspace",
        headers=headers,
        json={
            "template_type": "role_changed",
            "workspace_name": "Acme Corporation",
            "user_name": "Member Name",
            "old_role_name": "Viewer",
            "role_name": "Editor",
            "secondary_user_name": "Admin User"
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Subject: {data['subject']}")
        print(f"   ✓ Size: {data['metadata']['size_bytes']} bytes")
    else:
        print(f"   ✗ Error: {response.status_code}")

    # Test 4: Member Removed
    print("\n4. Testing member removed preview...")
    response = requests.post(
        f"{API_BASE_URL}/workspace",
        headers=headers,
        json={
            "template_type": "member_removed",
            "workspace_name": "Acme Corporation",
            "user_name": "Member Name",
            "secondary_user_name": "Admin User",
            "reason": "Project concluded"
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Subject: {data['subject']}")
        print(f"   ✓ Size: {data['metadata']['size_bytes']} bytes")
    else:
        print(f"   ✗ Error: {response.status_code}")


def test_html_endpoints():
    """Test HTML preview endpoints (returns raw HTML)."""
    print("\n\nTesting HTML Preview Endpoints")
    print("=" * 60)

    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }

    print("\n1. Testing auth HTML endpoint...")
    response = requests.post(
        f"{API_BASE_URL}/auth/html",
        headers=headers,
        json={
            "template_type": "verification",
            "user_name": "Test User"
        }
    )
    if response.status_code == 200:
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Content-Type: {response.headers.get('content-type')}")
        print(f"   ✓ Returns raw HTML (size: {len(response.text)} bytes)")
    else:
        print(f"   ✗ Error: {response.status_code}")

    print("\n2. Testing workspace HTML endpoint...")
    response = requests.post(
        f"{API_BASE_URL}/workspace/html",
        headers=headers,
        json={
            "template_type": "invitation",
            "workspace_name": "Test Workspace",
            "user_name": "Inviter"
        }
    )
    if response.status_code == 200:
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Content-Type: {response.headers.get('content-type')}")
        print(f"   ✓ Returns raw HTML (size: {len(response.text)} bytes)")
    else:
        print(f"   ✗ Error: {response.status_code}")


def main():
    """Run all preview endpoint tests."""
    print("\n" + "=" * 60)
    print("Email Preview Endpoint Tests")
    print("=" * 60)

    print(f"\nAPI Base URL: {API_BASE_URL}")
    print(f"Auth Token: {'[SET]' if AUTH_TOKEN != 'your_auth_token_here' else '[NOT SET]'}")

    if AUTH_TOKEN == "your_auth_token_here":
        print("\n⚠️  WARNING: Auth token not set!")
        print("   Please set AUTH_TOKEN variable with a valid token")
        print("   You can get a token by logging in through the API")
        return

    try:
        # Run tests
        test_auth_email_previews()
        test_workspace_email_previews()
        test_html_endpoints()

        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        print("\n💡 Check the generated HTML files:")
        print("   - api_verification_preview.html")
        print("   - api_workspace_invitation_preview.html")

    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to API")
        print("   Make sure the backend server is running:")
        print("   cd wrext-backend && python src/api/server.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
