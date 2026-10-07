"""
Unit Tests for Email Preferences Service

Tests the EmailPreferencesService, which reads and writes the user's
NotificationPreferences: the global email switch and marketing are columns, every
other email type is a category key in its JSONB (`get_preference` / `set_preference`).
The database is a mock: no test here reaches a database or the network.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.services.email_preferences_service import EmailPreferencesService


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = Mock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def sample_user_id():
    """Sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_preferences(sample_user_id):
    """A user's notification preferences, every email allowed but marketing."""
    return NotificationPreferences(
        id=uuid4(),
        user_id=sample_user_id,
        email_notifications=True,
        in_app_notifications=True,
        marketing_updates=False,
        category_preferences={},
        unsubscribe_token=secrets.token_urlsafe(32),
    )


def _returns(mock_db, value):
    result = Mock()
    result.scalar_one_or_none.return_value = value
    mock_db.execute.return_value = result


class TestGetOrCreatePreferences:
    """Tests for get_or_create_preferences method."""

    @pytest.mark.asyncio
    async def test_get_existing_preferences(self, mock_db, sample_user_id, sample_preferences):
        """Test retrieving existing preferences."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        prefs = await service.get_or_create_preferences(sample_user_id)

        assert prefs == sample_preferences
        assert prefs.user_id == sample_user_id
        mock_db.execute.assert_called_once()
        mock_db.add.assert_not_called()  # Should not create new

    @pytest.mark.asyncio
    async def test_create_new_preferences(self, mock_db, sample_user_id):
        """Test creating new preferences when none exist."""
        _returns(mock_db, None)

        service = EmailPreferencesService(mock_db)
        await service.get_or_create_preferences(sample_user_id)

        mock_db.execute.assert_called_once()
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

        added = mock_db.add.call_args[0][0]
        assert isinstance(added, NotificationPreferences)
        assert added.user_id == sample_user_id
        assert added.unsubscribe_token  # an unsubscribe link works from the first email
        assert added.get_preference("ws_invite_received") is True  # the default


class TestCheckCanSend:
    """Tests for check_can_send method."""

    @pytest.mark.asyncio
    async def test_can_send_when_preference_enabled(
        self, mock_db, sample_user_id, sample_preferences
    ):
        """Test that email is allowed when preference is enabled."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        can_send = await service.check_can_send(sample_user_id, "workspace_invitation")

        assert can_send is True

    @pytest.mark.asyncio
    async def test_cannot_send_when_preference_disabled(
        self, mock_db, sample_user_id, sample_preferences
    ):
        """Test that email is blocked when preference is disabled (marketing, a column)."""
        sample_preferences.marketing_updates = False
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        can_send = await service.check_can_send(sample_user_id, "marketing")

        assert can_send is False

    @pytest.mark.asyncio
    async def test_can_send_with_alias_email_type(
        self, mock_db, sample_user_id, sample_preferences
    ):
        """Test that email type aliases work correctly ("invitation" is the workspace invite)."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        can_send = await service.check_can_send(sample_user_id, "invitation")

        assert can_send is True

    @pytest.mark.asyncio
    async def test_can_send_unknown_email_type_defaults_to_true(
        self, mock_db, sample_user_id, sample_preferences
    ):
        """Test that unknown email types default to allowing email."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        can_send = await service.check_can_send(sample_user_id, "unknown_type")

        assert can_send is True

    @pytest.mark.asyncio
    async def test_cannot_send_when_a_category_is_turned_off(
        self, mock_db, sample_user_id, sample_preferences
    ):
        """A category turned off (a JSONB key) stops that email, and only that one (G61 #523)."""
        sample_preferences.set_preference("billing_payment_success", False)
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)

        assert await service.check_can_send(sample_user_id, "payment_succeeded") is False
        assert await service.check_can_send(sample_user_id, "payment_recovered") is False
        assert await service.check_can_send(sample_user_id, "payment_failed") is True


class TestUpdatePreferences:
    """Tests for update_preferences method."""

    @pytest.mark.asyncio
    async def test_update_single_preference(self, mock_db, sample_user_id, sample_preferences):
        """Test updating a single preference field (marketing, a column)."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        await service.update_preferences(sample_user_id, {"marketing": True})

        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()
        assert sample_preferences.marketing_updates is True

    @pytest.mark.asyncio
    async def test_update_multiple_preferences(self, mock_db, sample_user_id, sample_preferences):
        """Test updating several category preferences (JSONB keys)."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        updates = {
            "workspace_invitation": False,
            "invitation_accepted": False,
            "role_changed": False,
        }
        await service.update_preferences(sample_user_id, updates)

        assert sample_preferences.get_preference("ws_invite_received") is False
        assert sample_preferences.get_preference("ws_invite_accepted") is False
        assert sample_preferences.get_preference("ws_role_changed") is False
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_ignores_invalid_fields(self, mock_db, sample_user_id, sample_preferences):
        """Test that invalid fields are ignored during update."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        updates = {
            "marketing": True,
            "invalid_field": True,  # Should be ignored
            "another_invalid": "value",  # Should be ignored
        }
        await service.update_preferences(sample_user_id, updates)

        assert sample_preferences.marketing_updates is True
        assert not hasattr(sample_preferences, "invalid_field")
        assert "invalid_field" not in (sample_preferences.category_preferences or {})
        mock_db.flush.assert_called_once()


class TestUnsubscribe:
    """Tests for unsubscribe method."""

    @pytest.mark.asyncio
    async def test_unsubscribe_from_specific_types(self, mock_db, sample_preferences):
        """Test unsubscribing from specific email types (JSONB keys)."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        success = await service.unsubscribe(
            sample_preferences.unsubscribe_token, ["workspace_invitation", "role_changed"]
        )

        assert success is True
        assert sample_preferences.get_preference("ws_invite_received") is False
        assert sample_preferences.get_preference("ws_role_changed") is False
        assert sample_preferences.get_preference("ws_invite_accepted") is True  # Not unsubscribed
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_from_all(self, mock_db, sample_preferences):
        """Test unsubscribing from all emails (empty list): the global switch goes off."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        success = await service.unsubscribe(sample_preferences.unsubscribe_token, [])

        assert success is True
        assert sample_preferences.email_notifications is False
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_with_invalid_token(self, mock_db):
        """Test unsubscribe with invalid token returns False."""
        _returns(mock_db, None)

        service = EmailPreferencesService(mock_db)
        success = await service.unsubscribe("invalid-token", ["marketing"])

        assert success is False
        mock_db.flush.assert_not_called()


class TestGetUnsubscribeLink:
    """Tests for get_unsubscribe_link method."""

    @pytest.mark.asyncio
    async def test_get_unsubscribe_link(self, mock_db, sample_user_id, sample_preferences):
        """Test generating unsubscribe link."""
        _returns(mock_db, sample_preferences)

        service = EmailPreferencesService(mock_db)
        frontend_url = "https://app.rext.com"
        link = await service.get_unsubscribe_link(sample_user_id, frontend_url)

        assert link.startswith(frontend_url)
        assert "/unsubscribe?token=" in link
        assert sample_preferences.unsubscribe_token in link

    @pytest.mark.asyncio
    async def test_get_unsubscribe_link_creates_preferences_if_not_exist(
        self, mock_db, sample_user_id
    ):
        """Test that get_unsubscribe_link creates preferences if they don't exist."""
        _returns(mock_db, None)

        service = EmailPreferencesService(mock_db)
        link = await service.get_unsubscribe_link(sample_user_id, "https://app.rext.com")

        mock_db.add.assert_called_once()
        created = mock_db.add.call_args[0][0]
        assert link == f"https://app.rext.com/unsubscribe?token={created.unsubscribe_token}"
