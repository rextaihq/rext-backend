"""
Unit tests for MockEmailProvider.

Tests cover:
- Email sending and storage
- Failure simulation
- Utility methods (get_sent_emails, get_last_email, etc.)
- State management (clear_sent_emails)
- Connection verification
"""

import pytest
from datetime import datetime
from src.providers.email.mock_provider import MockEmailProvider
from src.providers.email.base import EmailMessage, EmailRecipient, EmailResult


class TestMockEmailProviderBasics:
    """Test basic MockEmailProvider functionality"""

    @pytest.mark.asyncio
    async def test_initialization_default(self):
        """Should initialize with default settings"""
        provider = MockEmailProvider()

        assert provider.get_provider_name() == "mock"
        assert provider.simulate_failures is False
        assert provider.failure_rate == 0.0
        assert provider.get_sent_count() == 0
        assert provider.sent_emails == []

    @pytest.mark.asyncio
    async def test_initialization_with_failures(self):
        """Should initialize with failure simulation enabled"""
        provider = MockEmailProvider(simulate_failures=True, failure_rate=0.5)

        assert provider.simulate_failures is True
        assert provider.failure_rate == 0.5

    @pytest.mark.asyncio
    async def test_failure_rate_clamping(self):
        """Should clamp failure rate between 0 and 1"""
        # Test upper bound
        provider1 = MockEmailProvider(simulate_failures=True, failure_rate=2.0)
        assert provider1.failure_rate == 1.0

        # Test lower bound
        provider2 = MockEmailProvider(simulate_failures=True, failure_rate=-0.5)
        assert provider2.failure_rate == 0.0


class TestMockEmailProviderSendEmail:
    """Test send_email method"""

    @pytest.mark.asyncio
    async def test_send_email_success(self):
        """Should send email and store in memory"""
        provider = MockEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="test@example.com", name="Test User")],
            subject="Test Subject",
            html="<p>Test Body</p>",
            from_email="noreply@wrext.com",
            from_name="WREXT"
        )

        result = await provider.send_email(message)

        # Verify result
        assert result.success is True
        assert result.message_id is not None
        assert result.message_id.startswith("mock-1-")
        assert result.error is None
        assert result.provider_response["mock"] is True
        assert result.provider_response["stored"] is True

        # Verify email stored
        assert provider.get_sent_count() == 1
        last_email = provider.get_last_email()
        assert last_email is not None
        assert last_email["to"] == ["test@example.com"]
        assert last_email["subject"] == "Test Subject"
        assert last_email["html"] == "<p>Test Body</p>"
        assert last_email["from_email"] == "noreply@wrext.com"
        assert last_email["from_name"] == "WREXT"

    @pytest.mark.asyncio
    async def test_send_email_with_cc_bcc(self):
        """Should handle cc and bcc recipients"""
        provider = MockEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@example.com",
            cc=[EmailRecipient(email="cc@example.com")],
            bcc=[EmailRecipient(email="bcc@example.com")]
        )

        result = await provider.send_email(message)

        assert result.success is True
        last_email = provider.get_last_email()
        assert last_email["cc"] == ["cc@example.com"]
        assert last_email["bcc"] == ["bcc@example.com"]

    @pytest.mark.asyncio
    async def test_send_email_with_reply_to(self):
        """Should store reply_to address"""
        provider = MockEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@example.com",
            reply_to="reply@example.com"
        )

        result = await provider.send_email(message)

        assert result.success is True
        last_email = provider.get_last_email()
        assert last_email["reply_to"] == "reply@example.com"

    @pytest.mark.asyncio
    async def test_send_email_with_tags(self):
        """Should store email tags"""
        provider = MockEmailProvider()

        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@example.com",
            tags={"type": "auth", "action": "verify"}
        )

        result = await provider.send_email(message)

        assert result.success is True
        last_email = provider.get_last_email()
        assert last_email["tags"] == {"type": "auth", "action": "verify"}

    @pytest.mark.asyncio
    async def test_send_multiple_emails(self):
        """Should track multiple emails with incrementing IDs"""
        provider = MockEmailProvider()

        for i in range(3):
            message = EmailMessage(
                to=[EmailRecipient(email=f"user{i}@example.com")],
                subject=f"Email {i}",
                html=f"<p>Body {i}</p>",
                from_email="noreply@wrext.com"
            )
            result = await provider.send_email(message)
            assert result.success is True

        assert provider.get_sent_count() == 3
        sent_emails = provider.get_sent_emails()
        assert len(sent_emails) == 3
        assert sent_emails[0]["subject"] == "Email 0"
        assert sent_emails[1]["subject"] == "Email 1"
        assert sent_emails[2]["subject"] == "Email 2"


class TestMockEmailProviderFailureSimulation:
    """Test failure simulation functionality"""

    @pytest.mark.asyncio
    async def test_failure_simulation_disabled(self):
        """Should always succeed when failure simulation disabled"""
        provider = MockEmailProvider(simulate_failures=False)

        message = EmailMessage(
            to=[EmailRecipient(email="test@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@example.com"
        )

        # Send 10 emails - all should succeed
        for _ in range(10):
            result = await provider.send_email(message)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_failure_simulation_100_percent(self):
        """Should always fail with 100% failure rate"""
        provider = MockEmailProvider(simulate_failures=True, failure_rate=1.0)

        message = EmailMessage(
            to=[EmailRecipient(email="test@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@example.com"
        )

        result = await provider.send_email(message)

        assert result.success is False
        assert result.error == "Simulated failure for testing"
        assert result.provider_response["simulated"] is True
        assert provider.get_sent_count() == 0  # Failed email not stored

    @pytest.mark.asyncio
    async def test_failure_simulation_partial(self):
        """Should fail approximately at the configured rate"""
        provider = MockEmailProvider(simulate_failures=True, failure_rate=0.5)

        message = EmailMessage(
            to=[EmailRecipient(email="test@example.com")],
            subject="Test",
            html="<p>Test</p>",
            from_email="from@example.com"
        )

        # Send 100 emails and count failures
        failures = 0
        for _ in range(100):
            result = await provider.send_email(message)
            if not result.success:
                failures += 1

        # Should be approximately 50% (allow 30-70% range for randomness)
        assert 30 <= failures <= 70


class TestMockEmailProviderUtilityMethods:
    """Test utility methods for test verification"""

    @pytest.mark.asyncio
    async def test_get_sent_emails(self):
        """Should return copy of all sent emails"""
        provider = MockEmailProvider()

        # Send 3 emails
        for i in range(3):
            message = EmailMessage(
                to=[EmailRecipient(email=f"user{i}@example.com")],
                subject=f"Email {i}",
                html="<p>Test</p>",
                from_email="from@example.com"
            )
            await provider.send_email(message)

        sent = provider.get_sent_emails()
        assert len(sent) == 3

        # Verify it's a copy (modifying returned list doesn't affect internal state)
        sent.append({"fake": "email"})
        assert provider.get_sent_count() == 3

    @pytest.mark.asyncio
    async def test_get_last_email(self):
        """Should return most recent email"""
        provider = MockEmailProvider()

        # Send 2 emails
        message1 = EmailMessage(
            to=[EmailRecipient(email="first@example.com")],
            subject="First",
            html="<p>First</p>",
            from_email="from@example.com"
        )
        await provider.send_email(message1)

        message2 = EmailMessage(
            to=[EmailRecipient(email="second@example.com")],
            subject="Second",
            html="<p>Second</p>",
            from_email="from@example.com"
        )
        await provider.send_email(message2)

        last = provider.get_last_email()
        assert last is not None
        assert last["subject"] == "Second"
        assert last["to"] == ["second@example.com"]

    @pytest.mark.asyncio
    async def test_get_last_email_empty(self):
        """Should return None when no emails sent"""
        provider = MockEmailProvider()
        assert provider.get_last_email() is None

    @pytest.mark.asyncio
    async def test_get_emails_to(self):
        """Should filter emails by recipient"""
        provider = MockEmailProvider()

        # Send emails to different recipients
        message1 = EmailMessage(
            to=[EmailRecipient(email="alice@example.com")],
            subject="To Alice",
            html="<p>Hi Alice</p>",
            from_email="from@example.com"
        )
        await provider.send_email(message1)

        message2 = EmailMessage(
            to=[EmailRecipient(email="bob@example.com")],
            subject="To Bob",
            html="<p>Hi Bob</p>",
            from_email="from@example.com"
        )
        await provider.send_email(message2)

        message3 = EmailMessage(
            to=[EmailRecipient(email="alice@example.com")],
            subject="To Alice Again",
            html="<p>Hi Alice Again</p>",
            from_email="from@example.com"
        )
        await provider.send_email(message3)

        # Get emails to Alice
        alice_emails = provider.get_emails_to("alice@example.com")
        assert len(alice_emails) == 2
        assert alice_emails[0]["subject"] == "To Alice"
        assert alice_emails[1]["subject"] == "To Alice Again"

        # Get emails to Bob
        bob_emails = provider.get_emails_to("bob@example.com")
        assert len(bob_emails) == 1
        assert bob_emails[0]["subject"] == "To Bob"

    @pytest.mark.asyncio
    async def test_get_emails_with_subject(self):
        """Should filter emails by subject"""
        provider = MockEmailProvider()

        # Send emails with different subjects
        for i in range(3):
            message = EmailMessage(
                to=[EmailRecipient(email=f"user{i}@example.com")],
                subject="Welcome Email" if i % 2 == 0 else "Reset Password",
                html="<p>Test</p>",
                from_email="from@example.com"
            )
            await provider.send_email(message)

        welcome_emails = provider.get_emails_with_subject("Welcome Email")
        assert len(welcome_emails) == 2

        reset_emails = provider.get_emails_with_subject("Reset Password")
        assert len(reset_emails) == 1

    @pytest.mark.asyncio
    async def test_clear_sent_emails(self):
        """Should clear all sent emails and reset counter"""
        provider = MockEmailProvider()

        # Send 3 emails
        for i in range(3):
            message = EmailMessage(
                to=[EmailRecipient(email=f"user{i}@example.com")],
                subject=f"Email {i}",
                html="<p>Test</p>",
                from_email="from@example.com"
            )
            await provider.send_email(message)

        assert provider.get_sent_count() == 3

        # Clear
        provider.clear_sent_emails()

        assert provider.get_sent_count() == 0
        assert provider.get_last_email() is None
        assert provider.get_sent_emails() == []

    @pytest.mark.asyncio
    async def test_get_sent_count(self):
        """Should return accurate count of sent emails"""
        provider = MockEmailProvider()

        assert provider.get_sent_count() == 0

        # Send emails
        for i in range(5):
            message = EmailMessage(
                to=[EmailRecipient(email=f"user{i}@example.com")],
                subject=f"Email {i}",
                html="<p>Test</p>",
                from_email="from@example.com"
            )
            await provider.send_email(message)

        assert provider.get_sent_count() == 5


class TestMockEmailProviderConnectionVerification:
    """Test connection verification"""

    @pytest.mark.asyncio
    async def test_verify_connection(self):
        """Should always return True for mock provider"""
        provider = MockEmailProvider()
        result = await provider.verify_connection()
        assert result is True


class TestMockEmailProviderFeatureSupport:
    """Test feature support checking"""

    @pytest.mark.asyncio
    async def test_supports_feature(self):
        """Should support all listed features"""
        provider = MockEmailProvider()

        # Should support all features
        assert provider.supports_feature('basic_email') is True
        assert provider.supports_feature('webhooks') is True
        assert provider.supports_feature('tags') is True
        assert provider.supports_feature('cc_bcc') is True
        assert provider.supports_feature('reply_to') is True
        assert provider.supports_feature('html') is True
        assert provider.supports_feature('attachments') is True
        assert provider.supports_feature('templates') is True

        # Should not support unknown features
        assert provider.supports_feature('unknown_feature') is False
