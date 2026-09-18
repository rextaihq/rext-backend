from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.api.schema.admin_email_schema import AdminEmailLogResponse, ResendEmailRequest


def test_admin_email_log_response_serialization() -> None:
    """Should correctly serialize from dictionary or attributes."""
    data = {
        "id": uuid4(),
        "to_email": "test@example.com",
        "from_email": "admin@example.com",
        "subject": "Test Subject",
        "status": "sent",
        "provider": "resend",
        "retry_count": 0,
        "error_message": None,
        "created_at": datetime.now(timezone.utc),
        "sent_at": datetime.now(timezone.utc),
        "failed_at": None,
    }

    # Test dictionary validation
    response = AdminEmailLogResponse(**data)
    assert response.to_email == "test@example.com"
    assert response.status == "sent"


def test_resend_email_request_validation() -> None:
    """Should validate list length and item type."""
    # Valid request
    valid_ids = [uuid4() for _ in range(5)]
    request = ResendEmailRequest(email_log_ids=valid_ids)
    assert len(request.email_log_ids) == 5

    # Empty list (should fail due to min_length=1)
    with pytest.raises(ValidationError):
        ResendEmailRequest(email_log_ids=[])

    # Too many items (should fail due to max_length=100)
    too_many_ids = [uuid4() for _ in range(101)]
    with pytest.raises(ValidationError):
        ResendEmailRequest(email_log_ids=too_many_ids)

    # Invalid item type
    with pytest.raises(ValidationError):
        ResendEmailRequest(email_log_ids=["not-a-uuid"])
