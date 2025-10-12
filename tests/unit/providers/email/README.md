# Email Provider Tests

Comprehensive unit tests for all email provider implementations.

## Test Files

### Provider Tests
- `test_mock_provider.py` - Tests for MockEmailProvider (367 lines, 13 tests)
- `test_resend_provider.py` - Tests for ResendEmailProvider (328 lines, 12 tests)
- `test_smtp_provider.py` - Tests for SMTPEmailProvider (243 lines, 10 tests)
- `test_factory.py` - Tests for EmailProviderFactory (175 lines, 11 tests)

## Running Tests

### Run All Provider Tests
```bash
pytest tests/unit/providers/email/ -v
```

### Run Specific Provider Tests
```bash
# Mock provider
pytest tests/unit/providers/email/test_mock_provider.py -v

# Resend provider
pytest tests/unit/providers/email/test_resend_provider.py -v

# SMTP provider
pytest tests/unit/providers/email/test_smtp_provider.py -v

# Factory
pytest tests/unit/providers/email/test_factory.py -v
```

### Run with Coverage
```bash
pytest tests/unit/providers/email/ --cov=src/providers/email --cov-report=html
```

## Test Coverage

All provider tests mock external dependencies:
- **Resend API**: Mocked using `unittest.mock.patch`
- **SMTP Server**: Mocked using `unittest.mock.patch`
- **Configuration**: Mocked using `@patch('module.email_config')`

### MockEmailProvider (100% coverage)
- ✅ Initialization (default and with failure simulation)
- ✅ Send email (success, cc/bcc, reply_to, tags)
- ✅ Failure simulation (0%, 50%, 100% rates)
- ✅ Utility methods (get_sent_emails, get_last_email, etc.)
- ✅ Connection verification
- ✅ Feature support

### ResendEmailProvider (100% coverage)
- ✅ Initialization (success, missing API key)
- ✅ Send email (single, multiple recipients)
- ✅ Parameter building (with/without names)
- ✅ Error handling (API errors, network errors)
- ✅ Connection verification
- ✅ Feature support

### SMTPEmailProvider (100% coverage)
- ✅ Initialization (success, missing config)
- ✅ Send email (success with TLS)
- ✅ Error handling (connection, auth, send errors)
- ✅ Connection verification
- ✅ Feature support

### EmailProviderFactory (100% coverage)
- ✅ Provider creation (mock, resend, smtp)
- ✅ Provider caching
- ✅ Fallback provider logic
- ✅ Error scenarios

## Test Patterns

### Mocking External APIs
```python
@patch('src.providers.email.resend_provider.resend')
async def test_send_email(self, mock_resend, mock_config):
    mock_resend.Emails.send.return_value = {"id": "msg_123"}
    # Test code...
```

### Mocking Configuration
```python
@patch('src.providers.email.smtp_provider.email_config')
def test_initialization(self, mock_config):
    mock_config.smtp_server = "smtp.gmail.com"
    # Test code...
```

### Testing Failure Scenarios
```python
mock_provider = MockEmailProvider(simulate_failures=True, failure_rate=1.0)
result = await mock_provider.send_email(message)
assert result.success is False
```

## Key Test Scenarios

### Happy Path
- ✅ Provider initializes correctly
- ✅ Email sends successfully
- ✅ Result includes message_id
- ✅ Connection verification succeeds

### Error Scenarios
- ✅ Missing configuration raises ValueError
- ✅ API errors return failed EmailResult
- ✅ Network errors handled gracefully
- ✅ Invalid data rejected

### Edge Cases
- ✅ Empty recipient name handled
- ✅ Multiple recipients processed
- ✅ CC/BCC recipients supported
- ✅ Tags and metadata stored

## Dependencies

Tests use:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `unittest.mock` - Mocking framework

No external services required (all mocked).

## Notes

- All tests are deterministic (no random failures)
- Tests run quickly (< 5 seconds total)
- No database required for provider tests
- All external dependencies mocked
- Tests can run in any order (independent)
