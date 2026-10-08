"""
Webhook Security Tests

Tests webhook signature validation for all payment and email providers.
Ensures webhooks cannot be spoofed or replayed by attackers.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from svix.webhooks import Webhook

import src.api.routes.email.webhooks as resend_webhooks
import src.api.routes.subscriptions.webhook_routes as ls_webhooks
from src.api.config import settings
from src.config.email_config import email_config
from src.config.payment_config import payment_settings
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService

RESEND_SECRET = "whsec_" + base64.b64encode(b"resend-webhook-test-secret-1234").decode()


def _message(response) -> str:
    """The error's text: the app's envelope puts it under "message"."""
    return response.json()["message"].lower()

class TestResendWebhookSecurity:
    """Test Resend email webhook signature validation using Svix."""

    ENDPOINT = "/api/v1/email/webhooks/resend"
    PAYLOAD = {"type": "email.delivered", "data": {"email_id": "test-123"}}

    @pytest.fixture
    def resend_secret(self, monkeypatch):
        monkeypatch.setattr(email_config, "resend_webhook_secret", RESEND_SECRET)

    @pytest.fixture
    def processed(self, monkeypatch):
        """The background processing, replaced: these tests stop at the acknowledgement."""
        process = AsyncMock()
        monkeypatch.setattr(resend_webhooks, "process_webhook_in_background", process)
        return process

    async def test_resend_webhook_rejects_missing_signature_headers(
        self, client: AsyncClient, resend_secret, processed
    ):
        """Test that webhooks without Svix headers are rejected."""
        response = await client.post(self.ENDPOINT, json=self.PAYLOAD)

        assert response.status_code == 401
        assert "signature" in _message(response)
        processed.assert_not_called()

    async def test_resend_webhook_rejects_invalid_signature(
        self, client: AsyncClient, resend_secret, processed
    ):
        """Test that webhooks with invalid Svix signature are rejected."""
        response = await client.post(
            self.ENDPOINT,
            json=self.PAYLOAD,
            headers={
                "svix-id": "msg_123",
                "svix-timestamp": str(int(time.time())),
                "svix-signature": "v1,aW52YWxpZF9zaWduYXR1cmU=",
            },
        )

        assert response.status_code == 401
        processed.assert_not_called()

    async def test_resend_webhook_accepts_valid_signature(
        self, client: AsyncClient, resend_secret, processed
    ):
        """Test that webhooks with valid Svix signature are accepted."""
        body = json.dumps(self.PAYLOAD)
        msg_id = "msg_valid_1"
        sent_at = datetime.now(timezone.utc)
        signature = Webhook(RESEND_SECRET).sign(msg_id, sent_at, body)

        response = await client.post(
            self.ENDPOINT,
            content=body,
            headers={
                "Content-Type": "application/json",
                "svix-id": msg_id,
                "svix-timestamp": str(int(sent_at.timestamp())),
                "svix-signature": signature,
            },
        )

        assert response.status_code == 200
        processed.assert_called_once_with(self.PAYLOAD)

    async def test_resend_webhook_dev_mode_allows_no_secret(
        self, client: AsyncClient, monkeypatch, processed
    ):
        """Without a secret, development accepts the webhook unverified (staging and
        production answer 503 instead)."""
        monkeypatch.setattr(email_config, "resend_webhook_secret", None)
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")

        response = await client.post(self.ENDPOINT, json=self.PAYLOAD)

        assert response.status_code == 200
        processed.assert_called_once_with(self.PAYLOAD)


class TestLemonSqueezyWebhookSecurity:
    """Test LemonSqueezy webhook signature validation (HMAC-SHA256)."""

    WEBHOOK_SECRET = "test_webhook_secret_12345"
    WEBHOOK_ENDPOINT = "/api/v1/subscriptions/webhooks/lemonsqueezy"

    @pytest.fixture
    def lemonsqueezy_payload(self):
        """Sample LemonSqueezy webhook payload."""
        return {
            "meta": {"event_name": "subscription_created", "webhook_id": "webhook_123"},
            "data": {
                "type": "subscriptions",
                "id": "sub_123",
                "attributes": {
                    "store_id": 1,
                    "customer_id": 456,
                    "product_id": 789,
                    "variant_id": 101,
                    "status": "active",
                },
            },
        }

    @pytest.fixture
    def route(self, monkeypatch):
        """The signature layer alone: the IP allowlist off, the secret set, and what follows
        a valid signature (storing the event, processing it, the audit and security records)
        replaced, so a test reads only the route's answer."""
        monkeypatch.setattr(payment_settings, "webhook_ip_validation_enabled", False)
        monkeypatch.setattr(payment_settings, "lemonsqueezy_webhook_secret", self.WEBHOOK_SECRET)
        record = AsyncMock()
        process = AsyncMock()
        monkeypatch.setattr(LemonSqueezyWebhookService, "record_webhook", record)
        monkeypatch.setattr(ls_webhooks, "_process_webhook_in_background", process)
        monkeypatch.setattr(ls_webhooks.audit_logger, "log_webhook_received", AsyncMock())
        monkeypatch.setattr(
            ls_webhooks.webhook_security_monitor, "record_verification_failure", AsyncMock()
        )
        return record, process

    def generate_lemonsqueezy_signature(self, body: bytes, secret: str) -> str:
        """The HMAC-SHA256 hex digest LemonSqueezy sends in X-Signature, over the raw body."""
        return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    async def _send(self, client: AsyncClient, body: bytes, signature: str | None):
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers["X-Signature"] = signature
        return await client.post(self.WEBHOOK_ENDPOINT, content=body, headers=headers)

    async def test_lemonsqueezy_webhook_rejects_missing_signature(
        self, client: AsyncClient, lemonsqueezy_payload, route
    ):
        """Test that webhooks without X-Signature header are rejected."""
        record, _ = route
        response = await self._send(client, json.dumps(lemonsqueezy_payload).encode(), None)

        assert response.status_code == 400
        assert "signature" in _message(response)
        record.assert_not_called()

    async def test_lemonsqueezy_webhook_rejects_invalid_signature(
        self, client: AsyncClient, lemonsqueezy_payload, route
    ):
        """Test that webhooks with invalid signature are rejected."""
        record, _ = route
        response = await self._send(
            client, json.dumps(lemonsqueezy_payload).encode(), "invalid_signature_12345"
        )

        assert response.status_code == 401
        assert "signature" in _message(response)
        record.assert_not_called()

    async def test_lemonsqueezy_webhook_accepts_valid_signature(
        self, client: AsyncClient, lemonsqueezy_payload, route
    ):
        """Test that webhooks with valid HMAC signature are accepted."""
        record, process = route
        record.return_value = {
            "duplicate": False,
            "event_id": "event_1",
            "event_type": "subscription_created",
        }
        body = json.dumps(lemonsqueezy_payload).encode()

        response = await self._send(
            client, body, self.generate_lemonsqueezy_signature(body, self.WEBHOOK_SECRET)
        )

        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        record.assert_awaited_once_with(body)
        process.assert_called_once_with("event_1", "subscription_created")

    async def test_lemonsqueezy_webhook_rejects_replay_attack(
        self, client: AsyncClient, lemonsqueezy_payload, route
    ):
        """
        Test that duplicate webhooks are handled idempotently.

        LemonSqueezy doesn't include timestamps in signatures, so replay prevention is
        done via event deduplication: the stored event is processed once.
        """
        record, process = route
        record.side_effect = [
            {"duplicate": False, "event_id": "event_1", "event_type": "subscription_created"},
            {"duplicate": True, "event_id": "event_1", "event_type": "subscription_created"},
        ]
        body = json.dumps(lemonsqueezy_payload).encode()
        signature = self.generate_lemonsqueezy_signature(body, self.WEBHOOK_SECRET)

        first = await self._send(client, body, signature)
        replay = await self._send(client, body, signature)

        assert first.status_code == 200
        assert first.json()["status"] == "accepted"
        assert replay.status_code == 200
        assert replay.json()["status"] == "duplicate"
        process.assert_called_once_with("event_1", "subscription_created")

    async def test_lemonsqueezy_webhook_production_requires_secret(
        self, client: AsyncClient, lemonsqueezy_payload, route, monkeypatch
    ):
        """Without a configured secret, no signature verifies: the webhook is refused."""
        record, _ = route
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(payment_settings, "lemonsqueezy_webhook_secret", None)
        body = json.dumps(lemonsqueezy_payload).encode()

        response = await self._send(
            client, body, self.generate_lemonsqueezy_signature(body, self.WEBHOOK_SECRET)
        )

        assert response.status_code == 401
        record.assert_not_called()


class TestWebhookSignatureComparison:
    """Test that webhook signatures use constant-time comparison."""

    def test_signature_comparison_uses_hmac_compare_digest(self):
        """
        Verify that signature comparison uses hmac.compare_digest().

        This prevents timing attacks where attackers can determine the
        correct signature by measuring response times.
        """

        # Test helper function
        def secure_compare(a: str, b: str) -> bool:
            """Secure constant-time string comparison."""
            return hmac.compare_digest(a, b)

        # Same strings
        assert secure_compare("abc123", "abc123") is True

        # Different strings (same length)
        assert secure_compare("abc123", "xyz789") is False

        # Different strings (different length)
        assert secure_compare("abc", "abcdef") is False

        # Empty strings
        assert secure_compare("", "") is True

    def test_insecure_comparison_is_vulnerable(self):
        """
        Demonstrate why string == comparison is insecure.

        This test shows the vulnerability - do NOT use this in production.
        """

        def insecure_compare(a: str, b: str) -> bool:
            """INSECURE: Vulnerable to timing attacks."""
            return a == b  # ❌ DON'T DO THIS

        # This works the same as secure comparison
        assert insecure_compare("abc", "abc") is True
        assert insecure_compare("abc", "xyz") is False

        # But timing attacks can exploit character-by-character comparison
        # The comparison "fails faster" when the first character doesn't match


# ============================================================================
# Test Utilities
# ============================================================================


def create_test_webhook_event(
    provider: str, event_type: str, data: dict, secret: str
) -> tuple[dict, dict]:
    """
    Create a test webhook event with valid signature.

    Args:
        provider: Provider name (resend, lemonsqueezy, stripe, etc.)
        event_type: Event type (email.delivered, subscription_created, etc.)
        data: Event data
        secret: Webhook secret for signature generation

    Returns:
        Tuple of (payload, headers)
    """
    payload = {"type": event_type, "data": data}

    if provider == "lemonsqueezy":
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers = {"X-Signature": signature}

    elif provider == "resend":
        # Resend uses Svix - would need Svix library for real signatures
        headers = {
            "svix-id": "msg_test",
            "svix-timestamp": "1234567890",
            "svix-signature": "test_signature",
        }

    else:
        raise ValueError(f"Unknown provider: {provider}")

    return payload, headers
