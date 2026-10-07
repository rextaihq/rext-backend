"""
Unit tests for NotificationPreferences model (JSONB refactor — TASK-296).

Tests cover:
- DEFAULT_CATEGORY_PREFERENCES completeness
- get_preference() with known key, missing key, and None category_preferences
- set_preference() creates a new dict (SQLAlchemy mutation detection requirement)
- to_dict() returns the correct backward-compatible nested shape
"""

from uuid import uuid4

import pytest

from src.api.models.user_models.notification_preferences import (
    DEFAULT_CATEGORY_PREFERENCES,
    NotificationPreferences,
)


@pytest.fixture
def prefs() -> NotificationPreferences:
    """A fresh NotificationPreferences instance (not persisted)."""
    return NotificationPreferences(
        user_id=uuid4(),
        category_preferences=dict(DEFAULT_CATEGORY_PREFERENCES),
    )


# ── DEFAULT_CATEGORY_PREFERENCES ──────────────────────────────────────────────


class TestDefaultCategoryPreferences:
    def test_contains_all_expected_keys(self):
        expected = {
            "ws_invite_received",
            "ws_invite_accepted",
            "ws_role_changed",
            "ws_member_removed",
            "gen_started",
            "gen_completed",
            "gen_failed",
            "gen_published",
            "billing_payment_success",
            "billing_payment_failed",
            "billing_subscription_cancelled",
            "billing_subscription_expiring",
            "billing_trial_ending",
            "billing_usage_limit_warning",
            "billing_usage_limit_exceeded",
        }
        assert expected.issubset(DEFAULT_CATEGORY_PREFERENCES.keys())

    def test_most_defaults_are_true(self):
        # All core notification keys should default to True
        core_keys = [
            k
            for k in DEFAULT_CATEGORY_PREFERENCES
            if k.startswith(("ws_", "gen_", "billing_", "kb_"))
        ]
        for key in core_keys:
            assert DEFAULT_CATEGORY_PREFERENCES[key] is True, f"{key} should default to True"

    def test_product_update_defaults_are_false(self):
        assert DEFAULT_CATEGORY_PREFERENCES["email_product_updates"] is False
        assert DEFAULT_CATEGORY_PREFERENCES["in_app_product_updates"] is False


# ── get_preference() ──────────────────────────────────────────────────────────


class TestGetPreference:
    def test_returns_value_from_jsonb(self, prefs):
        prefs.category_preferences = {"ws_invite_received": False}
        assert prefs.get_preference("ws_invite_received") is False

    def test_falls_back_to_default_for_missing_key(self, prefs):
        prefs.category_preferences = {}
        # ws_invite_received has a True default
        assert prefs.get_preference("ws_invite_received") is True

    def test_falls_back_to_true_for_completely_unknown_key(self, prefs):
        prefs.category_preferences = {}
        assert prefs.get_preference("some_future_notification_type") is True

    def test_handles_none_category_preferences(self, prefs):
        prefs.category_preferences = None
        assert prefs.get_preference("ws_invite_received") is True

    def test_returns_false_default_for_opt_in_keys(self, prefs):
        prefs.category_preferences = {}
        assert prefs.get_preference("email_product_updates") is False


# ── set_preference() ──────────────────────────────────────────────────────────


class TestSetPreference:
    def test_updates_value(self, prefs):
        prefs.set_preference("ws_invite_received", False)
        assert prefs.category_preferences["ws_invite_received"] is False

    def test_creates_new_dict_object(self, prefs):
        """SQLAlchemy JSONB mutation tracking requires a new dict, not in-place mutation."""
        original = prefs.category_preferences
        prefs.set_preference("gen_started", False)
        assert prefs.category_preferences is not original

    def test_handles_none_category_preferences(self, prefs):
        prefs.category_preferences = None
        prefs.set_preference("gen_completed", False)
        # Should initialize from defaults and set the value
        assert prefs.category_preferences["gen_completed"] is False
        assert "ws_invite_received" in prefs.category_preferences  # defaults carried over

    def test_preserves_other_values(self, prefs):
        prefs.set_preference("billing_payment_failed", False)
        # All other keys should remain intact
        assert prefs.get_preference("ws_invite_received") is True
        assert prefs.get_preference("gen_completed") is True


# ── to_dict() ─────────────────────────────────────────────────────────────────


class TestToDict:
    def test_returns_correct_top_level_keys(self, prefs):
        result = prefs.to_dict()
        expected_keys = {
            "email_enabled",
            "in_app_enabled",
            "digest_enabled",
            "digest_frequency",
            "workspace_notifications",
            "content_generation",
            "billing",
            "marketing",
        }
        assert set(result.keys()) == expected_keys

    def test_workspace_notifications_shape(self, prefs):
        result = prefs.to_dict()
        ws = result["workspace_notifications"]
        assert set(ws.keys()) == {
            "invite_received",
            "invite_accepted",
            "role_changed",
            "member_removed",
        }

    def test_billing_shape(self, prefs):
        result = prefs.to_dict()
        billing = result["billing"]
        expected_keys = {
            "payment_success",
            "payment_failed",
            "subscription_cancelled",
            "subscription_expiring",
            "trial_ending",
            "usage_limit_warning",
            "usage_limit_exceeded",
        }
        assert set(billing.keys()) == expected_keys

    def test_defaults_all_true_for_core_prefs(self, prefs):
        result = prefs.to_dict()
        assert result["workspace_notifications"]["invite_received"] is True
        assert result["content_generation"]["generation_started"] is True
        assert result["billing"]["payment_success"] is True

    def test_reflects_updated_preference(self, prefs):
        prefs.set_preference("ws_invite_received", False)
        result = prefs.to_dict()
        assert result["workspace_notifications"]["invite_received"] is False

    def test_works_when_category_preferences_is_none(self, prefs):
        """Edge case: row loaded from DB before migration (category_preferences is empty/None)."""
        prefs.category_preferences = None
        result = prefs.to_dict()
        # Should not raise and should return defaults
        assert result["workspace_notifications"]["invite_received"] is True
        assert result["billing"]["payment_success"] is True

    def test_email_enabled_uses_dedicated_column(self, prefs):
        prefs.email_notifications = False
        result = prefs.to_dict()
        assert result["email_enabled"] is False

    def test_in_app_enabled_uses_dedicated_column(self, prefs):
        prefs.in_app_notifications = False
        result = prefs.to_dict()
        assert result["in_app_enabled"] is False
