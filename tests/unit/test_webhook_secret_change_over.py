"""The Lemon Squeezy webhook secret can be changed with no event refused.

The setting may hold the new secret and the old one, comma-separated, for the minutes between
changing it here and at the provider: an event signed with either is accepted, and one signed
with anything else is refused as before.
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
    ("setting", "accepted", "refused"),
    [
        ("only-one", ["only-one"], ["another"]),
        ("the-new,the-old", ["the-new", "the-old"], ["a-third"]),
        (" the-new , the-old ", ["the-new", "the-old"], ["a-third", " the-new"]),
        # A secret that itself holds a comma still works as one.
        ("has,a-comma", ["has,a-comma"], ["neither"]),
    ],
)
def test_an_event_signed_with_any_listed_secret_is_accepted(setting, accepted, refused):
    for secret in accepted:
        assert verify_webhook_signature(PAYLOAD, _signed(secret), setting) is True
    for secret in refused:
        assert verify_webhook_signature(PAYLOAD, _signed(secret), setting) is False


@pytest.mark.parametrize("setting", [None, "", "  ", " , "])
def test_no_secret_accepts_nothing(setting):
    assert signing_secrets(setting) == []
    assert verify_webhook_signature(PAYLOAD, _signed(""), setting) is False


def test_a_missing_signature_is_refused():
    assert verify_webhook_signature(PAYLOAD, "", "the-new,the-old") is False


def test_a_refusal_logs_nothing_made_from_a_secret(caplog):
    with caplog.at_level("DEBUG"):
        verify_webhook_signature(PAYLOAD, "0" * 64, "the-new,the-old")

    for secret in ("the-new", "the-old"):
        assert secret not in caplog.text
        assert _signed(secret)[:8] not in caplog.text


@pytest.mark.asyncio
async def test_the_providers_own_check_follows_the_same_rule():
    provider = LemonSqueezyProvider.__new__(LemonSqueezyProvider)
    provider.webhook_secret = "the-new,the-old"

    assert await provider.verify_webhook_signature(PAYLOAD, _signed("the-old")) is True
    assert await provider.verify_webhook_signature(PAYLOAD, _signed("the-new")) is True
    assert await provider.verify_webhook_signature(PAYLOAD, _signed("a-third")) is False
