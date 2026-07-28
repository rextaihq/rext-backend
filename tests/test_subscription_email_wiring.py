"""
Guards for the subscription email pipeline.

Covers the two failure modes that silently stopped subscription emails:
  1. webhook idempotency collapsing every event onto one key
  2. handlers emitting an email_type that no dispatcher branch handles
"""
import json

from src.api.routes.subscriptions.webhook_routes import _EMAIL_DISPATCH, _money
from src.utils.lemonsqueezy_webhook import parse_webhook_payload


def _payload(event_name: str, subscription_id: str, **attrs) -> bytes:
    return json.dumps({
        "meta": {
            # Constant across every delivery to a given endpoint — this is exactly
            # what must NOT be used as the idempotency key.
            "webhook_id": "8ba0d5c1-fixed-endpoint-id",
            "event_name": event_name,
            "custom_data": {"user_id": "b1f0c2de-0000-4000-8000-000000000001"},
        },
        "data": {"type": "subscriptions", "id": subscription_id, "attributes": attrs},
    }).encode()


def test_distinct_events_get_distinct_idempotency_keys():
    """Two different events on one endpoint must not collide."""
    created = parse_webhook_payload(_payload("subscription_created", "111", status="active"))
    cancelled = parse_webhook_payload(_payload("subscription_cancelled", "111", status="cancelled"))

    assert created["event_id"] != cancelled["event_id"], (
        "distinct events collapsed onto one idempotency key — later webhooks "
        "would be discarded as duplicates"
    )
    # The endpoint id is still available, just not used for idempotency.
    assert created["webhook_endpoint_id"] == cancelled["webhook_endpoint_id"]


def test_identical_retry_reuses_the_same_key():
    """A LemonSqueezy retry resends the same bytes and must dedupe."""
    body = _payload("subscription_created", "222", status="active")
    assert parse_webhook_payload(body)["event_id"] == parse_webhook_payload(body)["event_id"]


def test_same_event_different_subscriptions_are_distinct():
    a = parse_webhook_payload(_payload("subscription_created", "333", status="active"))
    b = parse_webhook_payload(_payload("subscription_created", "444", status="active"))
    assert a["event_id"] != b["event_id"]


def test_every_handler_email_type_has_a_dispatcher_branch():
    """
    Any email_type a handler can return must be wired, or the email is dropped.

    Keep this list in sync with the "email_type" values in
    src/services/webhook_handlers/.
    """
    emitted = {
        "subscription_created",
        "subscription_upgraded",
        "subscription_downgraded",
        "subscription_cancelled",
        "subscription_expired",
        "subscription_renewed",
        "subscription_paused",
        "subscription_resumed",
        "payment_succeeded",
        "payment_failed",
        "payment_recovered",
    }
    missing = emitted - set(_EMAIL_DISPATCH)
    assert not missing, f"handlers emit email types with no sender wired: {sorted(missing)}"


def test_dispatcher_targets_exist_on_the_service():
    """Each dispatch entry must call a method BillingEmailService actually defines."""
    from src.services.billing_email_service import BillingEmailService

    class _Probe:
        def __init__(self):
            self.called = None

        def __getattr__(self, name):
            if not hasattr(BillingEmailService, name):
                raise AssertionError(f"BillingEmailService has no method {name!r}")

            async def _noop(**kwargs):
                return True

            return _noop

    for email_type, sender in _EMAIL_DISPATCH.items():
        coro = sender(_Probe(), "b1f0c2de-0000-4000-8000-000000000001", {})
        coro.close()  # never awaited; we only care that resolution succeeded


def test_money_formatting_handles_missing_and_null_amounts():
    assert _money({"amount_cents": 3900}) == "$39.00"
    assert _money({}) == "$0.00"
    assert _money({"amount_cents": None}) == "$0.00"


def test_plan_price_is_dollars_not_cents():
    """price_monthly/_yearly are Numeric dollar amounts — never divide by 100."""
    from decimal import Decimal
    from src.api.models.subscription_models.subscriptions import BillingPeriod
    from src.services.webhook_handlers.subscription_handlers import (
        _format_plan_price,
        _plan_features,
    )

    class _Plan:
        price_monthly = Decimal("39.00")
        price_yearly = Decimal("390.00")
        features = {"support": "Email Support", "custom_branding": False, "api_access": True}

    assert _format_plan_price(_Plan(), BillingPeriod.MONTHLY) == "$39.00"
    assert _format_plan_price(_Plan(), BillingPeriod.YEARLY) == "$390.00"

    features = _plan_features(_Plan())
    assert "Support: Email Support" in features
    assert "Api access" in features
    assert not any("branding" in f.lower() for f in features), "disabled flags must be omitted"


def test_plan_features_tolerates_null_column():
    from src.services.webhook_handlers.subscription_handlers import _plan_features

    class _Plan:
        features = None

    assert _plan_features(_Plan()) == []


# --- upgrade/downgrade classification -------------------------------------

def _plan(monthly, yearly):
    from decimal import Decimal

    class _P:
        price_monthly = Decimal(monthly)
        price_yearly = Decimal(yearly)

    return _P()


def _classify(old, old_bp, new, new_bp):
    from src.api.models.subscription_models.subscriptions import BillingPeriod
    from src.services.webhook_handlers.subscription_handlers import _monthly_equivalent

    return (
        "upgrade"
        if _monthly_equivalent(new, new_bp) >= _monthly_equivalent(old, old_bp)
        else "downgrade"
    )


def test_cross_period_tier_change_classified_by_monthly_equivalent():
    """
    A tier change that also switches billing period must be classified on tier,
    not on raw period price. Growth-yearly ($890) -> Pro-monthly ($189) is an
    upgrade; comparing raw prices flags it a downgrade.
    """
    from src.api.models.subscription_models.subscriptions import BillingPeriod

    growth, pro, starter = _plan("89", "890"), _plan("189", "1890"), _plan("39", "390")

    assert _classify(growth, BillingPeriod.YEARLY, pro, BillingPeriod.MONTHLY) == "upgrade"
    assert _classify(pro, BillingPeriod.YEARLY, starter, BillingPeriod.MONTHLY) == "downgrade"
    assert _classify(starter, BillingPeriod.MONTHLY, growth, BillingPeriod.YEARLY) == "upgrade"


def test_same_period_tier_change_still_classifies():
    from src.api.models.subscription_models.subscriptions import BillingPeriod

    growth, pro = _plan("89", "890"), _plan("189", "1890")
    assert _classify(growth, BillingPeriod.MONTHLY, pro, BillingPeriod.MONTHLY) == "upgrade"
    assert _classify(pro, BillingPeriod.MONTHLY, growth, BillingPeriod.MONTHLY) == "downgrade"


def test_expired_email_uses_expired_template_not_expiring_soon():
    """The expired email must render expired content, never the 'expiring soon' reminder."""
    from emails.templates.billing import render_subscription_expired_email

    html = render_subscription_expired_email(
        user_name="Maria", plan_name="Growth", expiry_date="July 24, 2026"
    )
    assert "expired" in html.lower()
    assert "expiring soon" not in html.lower()
    assert "None" not in html


# src/config/__init__.py re-exports the `email_config` instance, which shadows
# the submodule name — so `import src.config.email_config` yields the instance,
# not the module. import_module returns the real module from sys.modules.
import importlib


def _email_config_module():
    return importlib.import_module("src.config.email_config")


def test_mock_provider_not_blocked_by_resend_sender_rules():
    """The Resend sender guard must not fire when Resend is not the active provider."""
    ec = _email_config_module()

    orig = (ec.email_config.email_provider, ec.email_config.email_fallback_provider,
            ec.email_config.resend_from_email, ec._is_deployed)
    try:
        ec.email_config.email_provider = "mock"
        ec.email_config.email_fallback_provider = None
        ec.email_config.resend_from_email = "onboarding@resend.dev"  # placeholder
        ec._is_deployed = True
        ec._validate_sender_config()  # must not raise
    finally:
        (ec.email_config.email_provider, ec.email_config.email_fallback_provider,
         ec.email_config.resend_from_email, ec._is_deployed) = orig


def test_resend_provider_still_blocked_by_placeholder_sender():
    import pytest

    ec = _email_config_module()
    orig = (ec.email_config.email_provider, ec.email_config.resend_from_email, ec._is_deployed)
    try:
        ec.email_config.email_provider = "resend"
        ec.email_config.resend_from_email = "onboarding@resend.dev"
        ec._is_deployed = True
        with pytest.raises(RuntimeError):
            ec._validate_sender_config()
    finally:
        (ec.email_config.email_provider, ec.email_config.resend_from_email, ec._is_deployed) = orig
