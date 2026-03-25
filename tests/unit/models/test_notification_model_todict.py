import pytest
from uuid import uuid4
from datetime import datetime, timezone
from src.api.models.notification.notification_model import Notification

def test_notification_to_dict_exposed_fields():
    """Verify that user-facing fields are exposed in to_dict()"""
    notification = Notification()
    notification.user_id = uuid4()
    notification.title = "Test"
    notification.message = "Test Message"
    notification.type = "system"
    notification.category = "test"
    notification.status = "success"
    notification.priority = "high"
    notification.action_url = "/test"
    notification.action_label = "View"
    notification.payload = {"k": "v"}
    notification.read_at = datetime.now(timezone.utc)
    notification.expires_at = datetime.now(timezone.utc)
    
    data = notification.to_dict()
    
    # Check exposed fields
    assert data["priority"] == "high"
    assert data["action_url"] == "/test"
    assert data["action_label"] == "View"
    assert data["payload"] == {"k": "v"}
    assert "read_at" in data
    assert "expires_at" in data
    
    # Check internal fields (should be excluded)
    assert "is_archived" not in data
    assert "sent_via_sse" not in data
    assert "is_deleted" not in data
