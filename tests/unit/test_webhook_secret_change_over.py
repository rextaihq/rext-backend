"""The Lemon Squeezy webhook secret can be changed with no event refused.

While the secret is being changed, the one it replaces is kept in a setting of its own
(LEMONSQUEEZY_WEBHOOK_SECRET_PREVIOUS) for the minutes between changing it here and at the
provider: an event signed with either is accepted, and one signed with anything else is refused
as before. Each value is taken whole.
"""

import hashlib
import hmac

import pytest

from src.providers.payment.providers.lemonsqueezy import LemonSqueezyProvider
from src.utils.lemonsqueezy_webhook import signing_secrets, verify_webhook_signature

PAYLOAD = b'{"meta": {"event_name": "subscription_created"}}'


def _signed(secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), PAYLOAD, hashlib.sha256).hexdigest()


@pytest.mark.parametrize(
    ("secret", "previous", "accepted", "refused"),
    [
        ("only-one", None, ["only-one"], ["another"]),
        ("the-new", "the-old", ["the-new", "the-old"], ["a-third"]),
        (" the-new ", " the-old ", ["the-new", "the-old"], [" the-new "]),
        # Each value is taken whole: a comma in one makes no second secret of its parts.
        ("has,a-comma", None, ["has,a-comma"], ["has", "a-comma"]),
        ("the-new", "old,with-a-comma", ["the-new", "old,with-a-comma"], ["old", "with-a-comma"]),
        # The same value in both is one secret.
        ("same", "same", ["same"], ["another"]),
    ],
)
def test_an_event_signed_with_the_secret_or_the_one_it_replaces_is_accepted(
    secret, previous, accepted, refused
):
    for signed_with in accepted:
        assert verify_webhook_signature(PAYLOAD, _signed(signed_with), secret, previous) is True
    for signed_with in refused:
        assert verify_webhook_signature(PAYLOAD, _signed(signed_with), secret, previous) is False


@pytest.mark.parametrize(("secret", "previous"), [(None, None), ("", "  "), ("  ", None)])
def test_no_secret_accepts_nothing(secret, previous):
    assert signing_secrets(secret, previous) == []
    assert verify_webhook_signature(PAYLOAD, _signed(""), secret, previous) is False


def test_the_replaced_secret_alone_is_still_a_secret():
    # A secret cleared too early must not open the door: with only the old one set, it is the one.
    assert signing_secrets(None, "the-old") == ["the-old"]


def test_a_missing_signature_is_refused():
    assert verify_webhook_signature(PAYLOAD, "", "the-new", "the-old") is False


def test_a_refusal_logs_nothing_made_from_a_secret(caplog):
    with caplog.at_level("DEBUG"):
        verify_webhook_signature(PAYLOAD, "0" * 64, "the-new", "the-old")

    for secret in ("the-new", "the-old"):
        assert secret not in caplog.text
        assert _signed(secret)[:8] not in caplog.text


@pytest.mark.asyncio
async def test_the_providers_own_check_follows_the_same_rule(monkeypatch):
    from src.config.payment_config import payment_settings

    monkeypatch.setattr(payment_settings, "lemonsqueezy_webhook_secret_previous", "the-old")
    provider = LemonSqueezyProvider.__new__(LemonSqueezyProvider)
    provider.webhook_secret = "the-new"

    assert await provider.verify_webhook_signature(PAYLOAD, _signed("the-old")) is True
    assert await provider.verify_webhook_signature(PAYLOAD, _signed("the-new")) is True
    assert await provider.verify_webhook_signature(PAYLOAD, _signed("a-third")) is False
    # A secret passed in by the caller stands alone: the replaced one is not accepted beside it.
    assert await provider.verify_webhook_signature(PAYLOAD, _signed("own"), "own") is True
    assert await provider.verify_webhook_signature(PAYLOAD, _signed("the-old"), "own") is False
