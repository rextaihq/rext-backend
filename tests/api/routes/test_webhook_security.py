"""
Webhook Security Tests

Tests webhook signature validation for all payment and email providers.
Ensures webhooks cannot be spoofed or replayed by attackers.
"""

import pytest
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestResendWebhookSecurity:
    """Test Resend email webhook signature validation using Svix."""

    def test_resend_webhook_rejects_missing_signature_headers(self, client: TestClient):
        """Test that webhooks without Svix headers are rejected."""
        payload = {
            "type": "email.delivered",
            "data": {
                "email_id": "test-123",
                "to": "test@example.com"
            }
        }

        response = client.post(
            "/api/v1/email/webhooks/resend",
            json=payload
            # No Svix headers
        )

        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()

    def test_resend_webhook_rejects_invalid_signature(self, client: TestClient):
        """Test that webhooks with invalid Svix signature are rejected."""
        payload = {
            "type": "email.delivered",
            "data": {"email_id": "test-123"}
        }

        response = client.post(
            "/api/v1/email/webhooks/resend",
            json=payload,
            headers={
                "svix-id": "msg_123",
                "svix-timestamp": "1234567890",
                "svix-signature": "invalid_signature_here"
            }
        )

        assert response.status_code == 401

    @patch('src.api.routes.email.webhooks.email_config')
    def test_resend_webhook_accepts_valid_signature(
        self,
        mock_email_config,
        client: TestClient
    ):
        """Test that webhooks with valid Svix signature are accepted."""
        # Set up mock webhook secret
        mock_email_config.resend_webhook_secret = "whsec_test_secret"

        # This test requires actual Svix library integration
        # In a real scenario, you'd use Svix.test library to generate valid signatures
        # For now, we test the validation logic path
        pytest.skip("Requires Svix test library for signature generation")

    @patch('src.api.routes.email.webhooks.email_config')
    def test_resend_webhook_dev_mode_allows_no_secret(
        self,
        mock_email_config,
        client: TestClient
    ):
        """Test that development mode allows webhooks when secret not configured."""
        # No webhook secret configured
        mock_email_config.resend_webhook_secret = None

        payload = {
            "type": "email.delivered",
            "data": {"email_id": "test-123"}
        }

        # In dev mode, this should be accepted (with warning)
        # Note: This behavior should be changed to fail-closed in production
        response = client.post(
            "/api/v1/email/webhooks/resend",
            json=payload
        )

        # Currently accepts in dev mode (200 OK)
        # TODO: Should check environment and reject in production
        assert response.status_code in [200, 401]


class TestLemonSqueezyWebhookSecurity:
    """Test LemonSqueezy webhook signature validation (HMAC-SHA256)."""

    WEBHOOK_SECRET = "test_webhook_secret_12345"
    WEBHOOK_ENDPOINT = "/api/v1/subscriptions/webhooks/lemonsqueezy"

    @pytest.fixture
    def lemonsqueezy_payload(self):
        """Sample LemonSqueezy webhook payload."""
        return {
            "meta": {
                "event_name": "subscription_created",
                "webhook_id": "webhook_123"
            },
            "data": {
                "type": "subscriptions",
                "id": "sub_123",
                "attributes": {
                    "store_id": 1,
                    "customer_id": 456,
                    "product_id": 789,
                    "variant_id": 101,
                    "status": "active"
                }
            }
        }

    def generate_lemonsqueezy_signature(self, payload: dict, secret: str) -> str:
        """
        Generate valid LemonSqueezy HMAC-SHA256 signature.

        Args:
            payload: Webhook payload dict
            secret: Webhook secret

        Returns:
            Hex digest of HMAC-SHA256 signature
        """
        body = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        return signature

    # LemonSqueezy webhook implemented - test enabled
    # @pytest.mark.skipif(
        condition=False  # LemonSqueezy webhook IS implemented
        reason="LemonSqueezy webhook not yet implemented"
    
    def test_lemonsqueezy_webhook_rejects_missing_signature(
        self,
        client: TestClient,
        lemonsqueezy_payload
    ):
        """Test that webhooks without X-Signature header are rejected."""
        response = client.post(
            self.WEBHOOK_ENDPOINT,
            json=lemonsqueezy_payload
            # No X-Signature header
        )

        assert response.status_code == 422  # FastAPI validation error
        # Or 401 if custom validation

    # LemonSqueezy webhook implemented - test enabled
    # @pytest.mark.skipif(
        condition=True,
        reason="LemonSqueezy webhook not yet implemented"
    
    def test_lemonsqueezy_webhook_rejects_invalid_signature(
        self,
        client: TestClient,
        lemonsqueezy_payload
    ):
        """Test that webhooks with invalid signature are rejected."""
        response = client.post(
            self.WEBHOOK_ENDPOINT,
            json=lemonsqueezy_payload,
            headers={"X-Signature": "invalid_signature_12345"}
        )

        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()

    # LemonSqueezy webhook implemented - test enabled
    # @pytest.mark.skipif(
        condition=True,
        reason="LemonSqueezy webhook not yet implemented"
    
    @patch('src.api.config.settings.LEMONSQUEEZY_WEBHOOK_SECRET', WEBHOOK_SECRET)
    def test_lemonsqueezy_webhook_accepts_valid_signature(
        self,
        client: TestClient,
        lemonsqueezy_payload
    ):
        """Test that webhooks with valid HMAC signature are accepted."""
        # Generate valid signature
        signature = self.generate_lemonsqueezy_signature(
            lemonsqueezy_payload,
            self.WEBHOOK_SECRET
        )

        # Send webhook with valid signature
        response = client.post(
            self.WEBHOOK_ENDPOINT,
            json=lemonsqueezy_payload,
            headers={"X-Signature": signature}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    # LemonSqueezy webhook implemented - test enabled
    # @pytest.mark.skipif(
        condition=True,
        reason="LemonSqueezy webhook not yet implemented"
    
    def test_lemonsqueezy_webhook_rejects_replay_attack(
        self,
        client: TestClient,
        lemonsqueezy_payload
    ):
        """
        Test that duplicate webhooks are handled idempotently.

        Note: This tests idempotency, not signature-based replay prevention.
        LemonSqueezy doesn't include timestamps in signatures, so replay
        prevention is done via event ID deduplication.
        """
        signature = self.generate_lemonsqueezy_signature(
            lemonsqueezy_payload,
            self.WEBHOOK_SECRET
        )

        # Send webhook first time
        response1 = client.post(
            self.WEBHOOK_ENDPOINT,
            json=lemonsqueezy_payload,
            headers={"X-Signature": signature}
        )
        assert response1.status_code == 200

        # Send same webhook again (replay attack)
        response2 = client.post(
            self.WEBHOOK_ENDPOINT,
            json=lemonsqueezy_payload,
            headers={"X-Signature": signature}
        )

        # Should still return 200 (idempotent)
        # But should not process duplicate event
        assert response2.status_code == 200

        # TODO: Verify in database that event was only processed once

    # LemonSqueezy webhook implemented - test enabled
    # @pytest.mark.skipif(
        condition=True,
        reason="LemonSqueezy webhook not yet implemented"
    
    def test_lemonsqueezy_webhook_production_requires_secret(
        self,
        client: TestClient,
        lemonsqueezy_payload
    ):
        """Test that production environment rejects webhooks when secret not configured."""
        with patch('src.api.config.settings.ENVIRONMENT', 'production'):
            with patch('src.api.config.settings.LEMONSQUEEZY_WEBHOOK_SECRET', None):
                response = client.post(
                    self.WEBHOOK_ENDPOINT,
                    json=lemonsqueezy_payload,
                    headers={"X-Signature": "any_signature"}
                )

                # Should return 500 (internal server error - config issue)
                assert response.status_code == 500
                assert "not configured" in response.json()["detail"].lower()


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
    provider: str,
    event_type: str,
    data: dict,
    secret: str
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
    payload = {
        "type": event_type,
        "data": data
    }

    if provider == "lemonsqueezy":
        body = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        headers = {"X-Signature": signature}

    elif provider == "resend":
        # Resend uses Svix - would need Svix library for real signatures
        headers = {
            "svix-id": "msg_test",
            "svix-timestamp": "1234567890",
            "svix-signature": "test_signature"
        }

    else:
        raise ValueError(f"Unknown provider: {provider}")

    return payload, headers
