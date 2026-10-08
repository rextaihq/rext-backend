"""The emails a webhook sends are recorded (F23, revnix/rext-control#805).

The email step works on a session of its own. The email service only flushes its
log row, so the step has to commit it: without that, the welcome and the receipt
reached the buyer and left no row in `email_logs`.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.api.routes.subscriptions import webhook_routes
from src.providers.email.base import EmailResult
from src.providers.email.mock_provider import MockEmailProvider
from src.services.email_service import EmailService

EMAIL_TYPES = [
    "subscription_created",
    "payment_succeeded",
    "payment_failed",
    "payment_recovered",
    "subscription_unpaid",
    "subscription_cancelled",
    "subscription_upgraded",
    "subscription_downgraded",
]


class _Session:
    """A session that keeps a row only once it is committed, as a real one does."""

    def __init__(self):
        self.pending = []
        self.kept = []
        self.steps = []

    def add(self, row):
        row.retry_count = row.retry_count or 0  # the column's default, set by the flush
        self.pending.append(row)

    async def flush(self):
        pass

    async def commit(self):
        self.kept += self.pending
        self.pending = []
        self.steps.append("commit")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *error):
        self.pending = []  # what was only flushed is rolled back
        self.steps.append("close")


class _Billing:
    """Every billing email ends in `EmailService.send_email`, the real one here.

    The buyer's lookup, their preferences and the template are not this test's.
    """

    def __init__(self, db):
        self.email_service = EmailService(db)

    def __getattr__(self, name):
        if not (name.startswith("send_") and name.endswith("_email")):
            raise AttributeError(name)

        async def send(**_):
            await self.email_service.send_email(
                to="buyer@example.com",
                subject=name,
                html="<p>Thank you.</p>",
                template_type=name.removeprefix("send_").removesuffix("_email"),
            )
            return True

        return send


@pytest.fixture
def session(monkeypatch):
    opened = _Session()
    monkeypatch.setattr(webhook_routes, "AsyncSessionLocal", lambda: opened)
    return opened


@pytest.fixture
def provider():
    """Email on, sent through a provider that stores it in memory."""
    mock = MockEmailProvider()
    with (
        patch("src.services.email_service.email_config") as config,
        patch("src.services.email_service.get_email_provider", return_value=mock),
        patch("src.services.email_service.get_fallback_email_provider", return_value=None),
        patch("src.services.billing_email_service.BillingEmailService", _Billing),
        patch(
            "src.services.monitoring_service.MonitoringService.report_third_party_failure",
            AsyncMock(),
        ),
    ):
        config.email_enabled = True
        config.resend_from_email = "noreply@rext.com"
        config.resend_from_name = "Rext AI"
        config.email_retry_enabled = False
        config.email_retry_max_attempts = 1
        config.email_retry_delay_seconds = 0
        yield mock


def _task(email_type):
    return {
        "send_email": True,
        "email_type": email_type,
        "email_data": {"user_id": "u-1", "plan_name": "Growth", "amount_cents": 8900},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("email_type", EMAIL_TYPES)
async def test_a_webhooks_email_keeps_its_record(email_type, session, provider):
    await webhook_routes._send_webhook_email(_task(email_type), None)

    assert len(provider.sent_emails) == 1
    [row] = session.kept
    assert row.template_type == email_type
    assert row.status == "sent"
    assert row.provider_message_id
    assert session.steps == ["commit", "close"]


@pytest.mark.asyncio
async def test_a_failed_send_keeps_its_record_for_the_retry(session, provider):
    provider.send_email = AsyncMock(return_value=EmailResult(success=False, error="rejected"))

    await webhook_routes._send_webhook_email(_task("payment_succeeded"), None)

    [row] = session.kept
    assert row.status == "failed"
    assert row.error_message == "rejected"
    assert row.html_content == "<p>Thank you.</p>"  # what the retry sends again


@pytest.mark.asyncio
async def test_an_email_that_raised_commits_nothing_and_the_error_is_the_callers(session):
    with patch("src.services.billing_email_service.BillingEmailService") as service:
        service.return_value.send_payment_succeeded_email = AsyncMock(
            side_effect=RuntimeError("no such buyer")
        )
        with pytest.raises(RuntimeError):
            await webhook_routes._send_webhook_email(_task("payment_succeeded"), None)

    assert session.kept == []
    assert session.steps == ["close"]


@pytest.mark.asyncio
async def test_a_task_without_a_buyer_opens_no_session(session):
    await webhook_routes._send_webhook_email({"email_type": "payment_succeeded"}, None)

    assert session.steps == []
