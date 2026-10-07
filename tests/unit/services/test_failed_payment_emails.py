"""The emails and notices for a failed renewal (F11, revnix/rext-control#336).

Every failed attempt's email names when the renewal first failed and that Lemon
Squeezy retries for up to two weeks from then; when the retries run out, one
email says the plan stopped. The day-1/3/6 countdown emails are gone: they
counted down to a suspension date Lemon Squeezy's status no longer has.
"""

from unittest.mock import AsyncMock, patch

import pytest

from emails.templates import billing


def test_the_payment_failed_email_names_the_first_failure_and_the_two_weeks():
    html = billing.render_payment_failed_email(
        user_name="Ana", plan_name="Growth", amount="$89.00", failed_on="October 1, 2026"
    )

    assert "October 1, 2026" in html
    assert "up to two weeks" in html
    assert "retry the payment on" not in html


def test_the_unpaid_email_asks_for_a_card_and_promises_nothing_else():
    html = billing.render_subscription_unpaid_email(
        user_name="Ana", plan_name="Growth", update_payment_url="https://app.test/settings"
    )

    assert "Your plan has stopped" in html
    assert "Update your card" in html and "https://app.test/settings" in html
    assert "workspaces and content are kept" in html


def test_the_countdown_emails_are_gone():
    for name in (
        "render_payment_dunning_1_day_email",
        "render_payment_dunning_3_days_email",
        "render_payment_dunning_6_days_email",
        "render_subscription_suspended_email",
    ):
        assert not hasattr(billing, name), name


@pytest.mark.asyncio
async def test_the_webhook_sends_the_unpaid_email_and_notice():
    from src.api.routes.subscriptions import webhook_routes

    task = {
        "send_email": True,
        "email_type": "subscription_unpaid",
        "email_data": {"user_id": "u-1", "plan_name": "Growth", "subscription_id": "s-1"},
    }
    sender = AsyncMock()
    with patch("src.services.billing_email_service.BillingEmailService") as service:
        service.return_value.send_subscription_unpaid_email = sender
        await webhook_routes._send_webhook_email(task, None)
    notify = AsyncMock()
    with patch("src.services.notification_helper.notify_now", notify):
        await webhook_routes._send_webhook_notification(task)

    sender.assert_awaited_once_with(user_id="u-1", plan_name="Growth")
    assert notify.await_args.kwargs["pref_flag"] == "billing_payment_failed"
    assert "Growth plan has stopped" in notify.await_args.kwargs["message"]
    assert "$0.00" not in notify.await_args.kwargs["message"]


@pytest.mark.asyncio
async def test_the_payment_failed_email_gets_its_date():
    from src.api.routes.subscriptions import webhook_routes

    task = {
        "email_type": "payment_failed",
        "email_data": {
            "user_id": "u-1",
            "plan_name": "Growth",
            "amount_cents": 8900,
            "failed_on": "October 01, 2026",
        },
    }
    sender = AsyncMock()
    with patch("src.services.billing_email_service.BillingEmailService") as service:
        service.return_value.send_payment_failed_email = sender
        await webhook_routes._send_webhook_email(task, None)

    sender.assert_awaited_once_with(
        user_id="u-1", plan_name="Growth", amount="$89.00", failed_on="October 01, 2026"
    )
