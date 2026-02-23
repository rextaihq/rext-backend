import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
from src.services.monitoring_service import MonitoringService
from src.api.models.admin_models.error_log import ErrorLog

def mock_db():
    return AsyncMock()

def service(db):
    return MonitoringService(db)

def test_redact_text_bearer_token(service):
    text = "Authorization: Bearer sk_test_12345"
    redacted = service._redact_text(text)
    assert redacted == "Authorization: Bearer [REDACTED]"

def test_redact_text_api_key(service):
    text = "Connection failed with api-key=abc-123-def"
    redacted = service._redact_text(text)
    assert redacted == "Connection failed with api-key=[REDACTED]"
    
    text2 = "API_KEY: mysecret"
    assert service._redact_text(text2) == "API_KEY: [REDACTED]"

def test_redact_text_password(service):
    text = "Login error for user, password: superpassword123"
    redacted = service._redact_text(text)
    assert redacted == "Login error for user, password: [REDACTED]"

def test_redact_text_truncation(service):
    long_text = "A" * 5000
    redacted = service._redact_text(long_text)
    assert len(redacted) <= 4100
    assert "...[truncated]" in redacted

def test_redact_json_sensitive_keys(service):
    metadata = {
        "user_email": "test@example.com",
        "api_key": "secret-key",
        "nested": {
            "token": "sensitive-token",
            "public": "info"
        },
        "list": [{"password": "123"}, {"safe": "val"}]
    }
    redacted = service._redact_json(metadata)
    assert redacted["user_email"] == "test@example.com"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["public"] == "info"
    assert redacted["list"][0]["password"] == "[REDACTED]"
    assert redacted["list"][1]["safe"] == "val"

@pytest.mark.asyncio
async def test_get_error_logs_redaction(service, mock_db):
    # Setup mock logs
    mock_log = MagicMock(spec=ErrorLog)
    mock_log.id = "123e4567-e89b-12d3-a456-426614174000"
    mock_log.timestamp = datetime.now(timezone.utc)
    mock_log.severity = "error"
    mock_log.message = "Error with api_key: test-key"
    mock_log.source = "file.py:10"
    mock_log.user_id = None
    mock_log.request_id = "req-1"
    mock_log.stack_trace = "Traceback...\nsecret=password123"
    mock_log.metadata = {"token": "abc"}
    mock_log.resolved = False
    mock_log.resolved_at = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_log]
    mock_db.execute.return_value = mock_result
    
    # Mock count
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1
    mock_db.execute.side_effect = [mock_count_result, mock_result]

    # Test without stack trace
    result = await service.get_error_logs(include_stack_trace=False)
    log = result["logs"][0]
    assert log["message"] == "Error with api_key: [REDACTED]"
    assert log["stack_trace"] is None
    assert log["metadata"]["token"] == "[REDACTED]"

    # Test with stack trace
    mock_db.execute.side_effect = [mock_count_result, mock_result]
    result = await service.get_error_logs(include_stack_trace=True)
    log = result["logs"][0]
    assert log["stack_trace"] == "Traceback...\nsecret=[REDACTED]"
    print("All tests passed!")

if __name__ == "__main__":
    import asyncio
    
    # Simple manual runner
    async def run_all():
        db = mock_db()
        s = service(db)
        
        print("Running test_redact_text_bearer_token...")
        test_redact_text_bearer_token(s)
        
        print("Running test_redact_text_api_key...")
        test_redact_text_api_key(s)
        
        print("Running test_redact_text_password...")
        test_redact_text_password(s)
        
        print("Running test_redact_text_truncation...")
        test_redact_text_truncation(s)
        
        print("Running test_redact_json_sensitive_keys...")
        test_redact_json_sensitive_keys(s)
        
        print("Running test_get_error_logs_redaction...")
        await test_get_error_logs_redaction(s, db)
        
    asyncio.run(run_all())
