import sys
import os
from unittest.mock import MagicMock
from uuid import uuid4
from datetime import datetime, timezone

# Mock expensive modules
for mod in ['langchain_core', 'langchain_core.prompts', 'transformers', 'torch', 'langsmith']:
    sys.modules[mod] = MagicMock()

sys.path.append(os.getcwd())

def verify_to_dict():
    print("Starting verification of Notification.to_dict()...")
    
    from src.api.models.notification.notification_model import Notification
    
    user_uuid = uuid4()
    # Create a notification object manually (bypass DB)
    notification = Notification()
    notification.user_id = user_uuid
    notification.title = "Test Notification"
    notification.message = "This is a test message"
    notification.type = "system"
    notification.category = "test_category"
    notification.status = "success"
    notification.priority = "high"
    notification.action_url = "/test-url"
    notification.action_label = "Test Action"
    notification.payload = {"key": "value"}
    notification.read_at = datetime.now(timezone.utc)
    notification.expires_at = datetime.now(timezone.utc)
    
    # Check fields that should be EXPOSED
    data = notification.to_dict()
    
    exposed_fields = [
        'priority', 'action_url', 'action_label', 'payload', 'read_at', 'expires_at'
    ]
    
    failed = False
    for field in exposed_fields:
        if field in data:
            print(f"✅ Field '{field}' is correctly EXPOSED.")
        else:
            print(f"❌ Field '{field}' is MISSING from the response.")
            failed = True
            
    # Check fields that should still be EXCLUDED
    excluded_fields = [
        'is_archived', 'archived_at', 'is_deleted', 'deleted_at',
        'sent_via_email', 'sent_via_sse', 'email_sent_at', 'sse_sent_at'
    ]
    
    # Set these fields so they would be returned if not excluded
    notification.is_archived = False
    notification.sent_via_sse = True
    
    data_with_internal = notification.to_dict()
    
    for field in excluded_fields:
        if field in data_with_internal:
            print(f"❌ Field '{field}' should be EXCLUDED but is EXPOSED.")
            failed = True
        else:
            print(f"✅ Field '{field}' is correctly EXCLUDED.")
            
    if not failed:
        print("\nSUCCESS: Notification.to_dict() behaves as expected.")
    else:
        print("\nFAILURE: Notification.to_dict() does not behave as expected.")
        sys.exit(1)

if __name__ == "__main__":
    verify_to_dict()
