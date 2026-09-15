import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Add src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.webhooks import WebhookEvent
from src.services.webhook_monitoring_service import WebhookMonitoringService


def test_email_masking():
    service = WebhookMonitoringService(MagicMock())
    assert service._mask_email("test@example.com") == "te***@example.com"
    assert service._mask_email("a@b.com") == "***@b.com"
    assert service._mask_email("ab@c.com") == "***@c.com"
    assert service._mask_email("abc@d.com") == "ab***@d.com"
    assert service._mask_email(None) is None
    assert service._mask_email("") == ""
    print("✅ test_email_masking passed")


def test_payload_redaction():
    service = WebhookMonitoringService(MagicMock())
    payload = {
        "event": "test",
        "data": {
            "attributes": {
                "user_email": "user@example.com",
                "customer_name": "John Doe",
                "nested": {"api_key": "secret-key", "phone": "123456789"},
            }
        },
        "meta": {"custom_data": {"token": "abc"}},
    }

    redacted = service._redact_payload(payload)

    assert redacted["data"]["attributes"]["user_email"] == "us***@example.com"
    assert redacted["data"]["attributes"]["nested"]["api_key"] == "[REDACTED]"
    assert redacted["data"]["attributes"]["nested"]["phone"] == "[REDACTED]"
    assert redacted["meta"]["custom_data"] == "[REDACTED]"
    # Ensure original payload is not mutated
    assert payload["data"]["attributes"]["nested"]["api_key"] == "secret-key"
    print("✅ test_payload_redaction passed")


def test_summarize_payload_redaction():
    service = WebhookMonitoringService(MagicMock())
    payload = {
        "data": {
            "id": "1",
            "type": "subscriptions",
            "attributes": {
                "status": "active",
                "user_email": "user@example.com",
                "customer_id": "cust_123",
            },
        }
    }

    summary = service._summarize_payload(payload)
    assert summary["user_email_masked"] == "us***@example.com"
    assert "user_email" not in summary
    print("✅ test_summarize_payload_redaction passed")


async def test_get_failed_webhooks_redaction():
    # Mock DB
    db = MagicMock(spec=AsyncSession)

    # Create mock events
    event = WebhookEvent(
        id="8547480a-9dbe-40f4-9494-0cfd68748981",
        event_id="evt_1",
        event_name="test_event",
        payload={"data": {"attributes": {"user_email": "user@example.com", "api_key": "secret"}}},
        processed=False,
        error_message="Error",
    )

    # Mock execution
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [event]
    mock_result.scalar.return_value = 1
    db.execute = AsyncMock(return_value=mock_result)

    service = WebhookMonitoringService(db)

    # Test without payload
    result = await service.get_failed_webhooks(include_payload=False)
    assert result["events"][0]["payload"] is None
    assert result["events"][0]["payload_summary"]["user_email_masked"] == "us***@example.com"

    # Test with payload
    result = await service.get_failed_webhooks(include_payload=True)
    assert result["events"][0]["payload"]["data"]["attributes"]["user_email"] == "us***@example.com"
    assert result["events"][0]["payload"]["data"]["attributes"]["api_key"] == "[REDACTED]"

    print("✅ test_get_failed_webhooks_redaction passed")


if __name__ == "__main__":
    from sqlalchemy.ext.asyncio import AsyncSession

    test_email_masking()
    test_payload_redaction()
    test_summarize_payload_redaction()
    asyncio.run(test_get_failed_webhooks_redaction())
    print("\nAll integration-style tests passed! 🚀")
