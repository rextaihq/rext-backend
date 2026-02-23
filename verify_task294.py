
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.api.schema.notification_schema import UpdateNotificationPreferencesRequest
from src.api.config import get_settings

def test_schema_loading():
    print("Testing UpdateNotificationPreferencesRequest...")
    # This should work without categories field
    data = {
        "email_notifications": True,
        "in_app_notifications": False,
        "gen_started": True
    }
    req = UpdateNotificationPreferencesRequest(**data)
    print(f"Request instantiated: {req.model_dump(exclude_unset=True)}")
    
    # Check that categories field is gone
    if hasattr(req, "categories"):
        print("ERROR: categories field still present!")
        sys.exit(1)
    else:
        print("SUCCESS: categories field is absent.")

def test_config_loading():
    print("\nTesting Config loading...")
    settings = get_settings()
    print(f"ALLOWED_MIME_TYPES: {settings.ALLOWED_MIME_TYPES}")
    print("Config loaded successfully.")

if __name__ == "__main__":
    try:
        test_schema_loading()
        test_config_loading()
        print("\nAll Task 294 schema/config checks PASSED.")
    except Exception as e:
        print(f"\nVerification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
