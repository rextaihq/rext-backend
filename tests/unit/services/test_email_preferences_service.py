"""
Unit Tests for Email Preferences Service

Tests the EmailPreferencesService which manages user email notification preferences.
"""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from uuid import uuid4
import secrets

from src.services.email_preferences_service import EmailPreferencesService
from src.api.models.user_models.email_preferences import EmailPreferences


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
    """Sample email preferences object."""
    return EmailPreferences(
        id=uuid4(),
        user_id=sample_user_id,
        workspace_invitation=True,
        invitation_accepted=True,
        role_changed=True,
        member_removed=True,
        marketing=False,
        unsubscribe_token=secrets.token_urlsafe(32)
    )


class TestGetOrCreatePreferences:
    """Tests for get_or_create_preferences method."""

    @pytest.mark.asyncio
    async def test_get_existing_preferences(self, mock_db, sample_user_id, sample_preferences):
        """Test retrieving existing preferences."""
        # Setup mock to return existing preferences
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        prefs = await service.get_or_create_preferences(sample_user_id, mock_db)

        # Assertions
        assert prefs == sample_preferences
        assert prefs.user_id == sample_user_id
        mock_db.execute.assert_called_once()
        mock_db.add.assert_not_called()  # Should not create new

    @pytest.mark.asyncio
    async def test_create_new_preferences(self, mock_db, sample_user_id):
        """Test creating new preferences when none exist."""
        # Setup mock to return None (no existing preferences)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        prefs = await service.get_or_create_preferences(sample_user_id, mock_db)

        # Assertions
        mock_db.execute.assert_called_once()
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Check that new preferences have default values
        added_prefs = mock_db.add.call_args[0][0]
        assert added_prefs.user_id == sample_user_id
        assert added_prefs.workspace_invitation is True  # Default
        assert added_prefs.marketing is False  # Default


class TestCheckCanSend:
    """Tests for check_can_send method."""

    @pytest.mark.asyncio
    async def test_can_send_when_preference_enabled(self, mock_db, sample_user_id, sample_preferences):
        """Test that email is allowed when preference is enabled."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        can_send = await service.check_can_send(sample_user_id, "workspace_invitation", mock_db)

        # Assertions
        assert can_send is True

    @pytest.mark.asyncio
    async def test_cannot_send_when_preference_disabled(self, mock_db, sample_user_id, sample_preferences):
        """Test that email is blocked when preference is disabled."""
        # Disable marketing preference
        sample_preferences.marketing = False

        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        can_send = await service.check_can_send(sample_user_id, "marketing", mock_db)

        # Assertions
        assert can_send is False

    @pytest.mark.asyncio
    async def test_can_send_with_alias_email_type(self, mock_db, sample_user_id, sample_preferences):
        """Test that email type aliases work correctly."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function with alias "invitation" (should map to "workspace_invitation")
        service = EmailPreferencesService(mock_db)
        can_send = await service.check_can_send(sample_user_id, "invitation", mock_db)

        # Assertions
        assert can_send is True

    @pytest.mark.asyncio
    async def test_can_send_unknown_email_type_defaults_to_true(self, mock_db, sample_user_id, sample_preferences):
        """Test that unknown email types default to allowing email."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function with unknown email type
        service = EmailPreferencesService(mock_db)
        can_send = await service.check_can_send(sample_user_id, "unknown_type", mock_db)

        # Assertions - should default to True for unknown types
        assert can_send is True


class TestUpdatePreferences:
    """Tests for update_preferences method."""

    @pytest.mark.asyncio
    async def test_update_single_preference(self, mock_db, sample_user_id, sample_preferences):
        """Test updating a single preference field."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        updates = {"marketing": True}
        prefs = await service.update_preferences(sample_user_id, updates, mock_db)

        # Assertions
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()
        assert sample_preferences.marketing is True

    @pytest.mark.asyncio
    async def test_update_multiple_preferences(self, mock_db, sample_user_id, sample_preferences):
        """Test updating multiple preference fields."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        updates = {
            "workspace_invitation": False,
            "invitation_accepted": False,
            "role_changed": False
        }
        prefs = await service.update_preferences(sample_user_id, updates, mock_db)

        # Assertions
        assert sample_preferences.workspace_invitation is False
        assert sample_preferences.invitation_accepted is False
        assert sample_preferences.role_changed is False
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_ignores_invalid_fields(self, mock_db, sample_user_id, sample_preferences):
        """Test that invalid fields are ignored during update."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function with invalid field
        service = EmailPreferencesService(mock_db)
        updates = {
            "marketing": True,
            "invalid_field": True,  # Should be ignored
            "another_invalid": "value"  # Should be ignored
        }
        prefs = await service.update_preferences(sample_user_id, updates, mock_db)

        # Assertions
        assert sample_preferences.marketing is True
        assert not hasattr(sample_preferences, "invalid_field")
        mock_db.flush.assert_called_once()


class TestUnsubscribe:
    """Tests for unsubscribe method."""

    @pytest.mark.asyncio
    async def test_unsubscribe_from_specific_types(self, mock_db, sample_preferences):
        """Test unsubscribing from specific email types."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        success = await service.unsubscribe(
            sample_preferences.unsubscribe_token,
            ["workspace_invitation", "role_changed"],
            mock_db
        )

        # Assertions
        assert success is True
        assert sample_preferences.workspace_invitation is False
        assert sample_preferences.role_changed is False
        assert sample_preferences.invitation_accepted is True  # Not unsubscribed
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_from_all(self, mock_db, sample_preferences):
        """Test unsubscribing from all emails (empty list)."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function with empty email_types list
        service = EmailPreferencesService(mock_db)
        success = await service.unsubscribe(
            sample_preferences.unsubscribe_token,
            [],  # Empty list = unsubscribe all
            mock_db
        )

        # Assertions
        assert success is True
        assert sample_preferences.workspace_invitation is False
        assert sample_preferences.invitation_accepted is False
        assert sample_preferences.role_changed is False
        assert sample_preferences.member_removed is False
        assert sample_preferences.marketing is False
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_with_invalid_token(self, mock_db):
        """Test unsubscribe with invalid token returns False."""
        # Setup mock to return None (invalid token)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        success = await service.unsubscribe("invalid-token", ["marketing"], mock_db)

        # Assertions
        assert success is False
        mock_db.commit.assert_not_called()


class TestGetUnsubscribeLink:
    """Tests for get_unsubscribe_link method."""

    @pytest.mark.asyncio
    async def test_get_unsubscribe_link(self, mock_db, sample_user_id, sample_preferences):
        """Test generating unsubscribe link."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_preferences
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        frontend_url = "https://app.wrext.com"
        link = await service.get_unsubscribe_link(sample_user_id, frontend_url, mock_db)

        # Assertions
        assert link.startswith(frontend_url)
        assert "/unsubscribe?token=" in link
        assert sample_preferences.unsubscribe_token in link

    @pytest.mark.asyncio
    async def test_get_unsubscribe_link_creates_preferences_if_not_exist(self, mock_db, sample_user_id):
        """Test that get_unsubscribe_link creates preferences if they don't exist."""
        # Setup mock to return None first (no preferences)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Call function
        service = EmailPreferencesService(mock_db)
        frontend_url = "https://app.wrext.com"
        link = await service.get_unsubscribe_link(sample_user_id, frontend_url, mock_db)

        # Assertions
        mock_db.add.assert_called_once()  # Should create new preferences
        mock_db.flush.assert_called_once()
        assert link.startswith(frontend_url)
        assert "/unsubscribe?token=" in link


# Test coverage report
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src.services.email_preferences_service", "--cov-report=term-missing"])
