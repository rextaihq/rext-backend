import sys
import os
# Ensure the current directory is in sys.path
sys.path.append(os.getcwd())

from fastapi.testclient import TestClient
from src.api.server import app
from src.api.security.token_utils import create_access_token
import uuid

def verify_permission_enforcement():
    print("STARTING VERIFICATION", flush=True)
    
    # We can use TestClient as a context manager to handle lifespan events if needed,
    # or just use it directly if we don't need DB connections for this specific test.
    # The endpoint /impersonate/status doesn't hit the DB directly in the initial permission check.
    
    client = TestClient(app)
    
    # 1. Test Restricted Access (No Permission)
    print("\n--- Testing Access WITHOUT 'user.read' Permission ---", flush=True)
    user_id = str(uuid.uuid4())
    token_no_perm = create_access_token({
        "id": user_id,
        "email": "noperm@example.com",
        "roles": ["user"],
        "permissions": ["some.other.permission"] # missing user.read
    })
    
    response = client.get(
        "/api/user/impersonate/status",
        headers={"Authorization": f"Bearer {token_no_perm}"}
    )
    
    print(f"Status Code: {response.status_code}", flush=True)
    if response.status_code == 403:
        print("SUCCESS: Access denied (403 Forbidden) as expected.", flush=True)
    else:
        print(f"FAILURE: Expected 403, got {response.status_code}. Response: {response.text}", flush=True)

    # 2. Test Allowed Access (With Permission)
    print("\n--- Testing Access WITH 'user.read' Permission ---", flush=True)
    token_with_perm = create_access_token({
        "id": user_id,
        "email": "withperm@example.com",
        "roles": ["user"],
        "permissions": ["user.read"]
    })
    
    response = client.get(
        "/api/user/impersonate/status",
        headers={"Authorization": f"Bearer {token_with_perm}"}
    )
    
    print(f"Status Code: {response.status_code}", flush=True)
    
    # Note: It might return 200 or 401/404 if it tries to hit DB later logic, 
    # but if it passes the permission check, it won't be 403.
    # The current implementation checks permission first.
    if response.status_code != 403:
         print(f"SUCCESS: Access granted (Status {response.status_code}). Permission check passed.", flush=True)
    else:
         print(f"FAILURE: Access denied (403) even with permission.", flush=True)

    print("\nVERIFICATION COMPLETE", flush=True)

if __name__ == "__main__":
    try:
        verify_permission_enforcement()
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
