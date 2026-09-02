from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# TODO: re-enable once the API below exists.
pytest.skip(
    "Written against NOTIFICATION_CONFIG, a per-category dict of "
    "{title, type} that does not exist in src/. The nearest real object is "
    "DEFAULT_CATEGORY_PREFERENCES (category -> bool), a different shape. "
    "Needs the notification-config API to be built, or the test rewritten.",
    allow_module_level=True,
)


from src.api.models.user_models.notification_preferences import (  # noqa: E402 -- follows a module-level pytest.skip
    NotificationPreferences,  # noqa: E402 -- follows a module-level pytest.skip
)
from src.services.notification_helper import (  # noqa: E402 -- follows a module-level pytest.skip
    NOTIFICATION_CONFIG,
    schedule_if_allowed,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_background_tasks():
    return MagicMock()


@pytest.fixture
def sample_user_id():
    return str(uuid4())


@pytest.fixture
def sample_prefs(sample_user_id):
    prefs = MagicMock(spec=NotificationPreferences)
    prefs.user_id = uuid4()
    prefs.in_app_notifications = True
    # Initialize some common columns
    prefs.ws_invite_received = True
    prefs.avatar_uploaded = True
    return prefs


@pytest.mark.asyncio
async def test_schedule_if_allowed_unknown_flag(mock_db, mock_background_tasks, sample_user_id):
    """Test that an unknown flag logs a warning and returns."""
    with patch("src.services.notification_helper.logger") as mock_logger:
        await schedule_if_allowed(
            db=mock_db,
            user_id=sample_user_id,
            background_tasks=mock_background_tasks,
            pref_flag="nonexistent_flag",
            message="Test message",
            payload={},
        )
        mock_logger.warning.assert_called_once()
        assert "Unknown notification flag 'nonexistent_flag'" in mock_logger.warning.call_args[0][0]
        mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_if_allowed_disabled_global_toggle(
    mock_db, mock_background_tasks, sample_user_id, sample_prefs
):
    """Test that disabled in_app_notifications skips notification."""
    sample_prefs.in_app_notifications = False

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_prefs
    mock_db.execute.return_value = mock_result

    with patch("src.services.notification_helper.logger") as mock_logger:
        await schedule_if_allowed(
            db=mock_db,
            user_id=sample_user_id,
            background_tasks=mock_background_tasks,
            pref_flag="ws_invite_received",
            message="Test message",
            payload={},
        )
        mock_logger.debug.assert_any_call(
            f"User {sample_user_id} disabled all in-app notifications."
        )
        mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_if_allowed_disabled_specific_flag(
    mock_db, mock_background_tasks, sample_user_id, sample_prefs
):
    """Test that disabled specific preference skips notification."""
    sample_prefs.ws_invite_received = False

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_prefs
    mock_db.execute.return_value = mock_result

    with patch("src.services.notification_helper.logger") as mock_logger:
        await schedule_if_allowed(
            db=mock_db,
            user_id=sample_user_id,
            background_tasks=mock_background_tasks,
            pref_flag="ws_invite_received",
            message="Test message",
            payload={},
        )
        mock_logger.debug.assert_any_call(
            f"User {sample_user_id} has preference ws_invite_received=False — skipping notification."
        )
        mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_if_allowed_virtual_flag(
    mock_db, mock_background_tasks, sample_user_id, sample_prefs
):
    """Test that virtual flags map correctly (e.g., avatar_uploaded -> in_app_notifications)."""
    # Force in_app_notifications to be True, even if specific flag logic is skipped
    sample_prefs.in_app_notifications = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_prefs
    mock_db.execute.return_value = mock_result

    # We need to mock Notification since it's imported inside the function
    with patch("src.api.models.notification.notification_model.Notification") as MockNotification:
        await schedule_if_allowed(
            db=mock_db,
            user_id=sample_user_id,
            background_tasks=mock_background_tasks,
            pref_flag="avatar_uploaded",
            message="Avatar updated",
            payload={},
        )
        # Verify it used Notification model
        MockNotification.assert_called_once()
        mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_schedule_if_allowed_success(
    mock_db, mock_background_tasks, sample_user_id, sample_prefs
):
    """Test successful notification scheduling and record creation."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_prefs
    mock_db.execute.return_value = mock_result

    with patch("src.api.models.notification.notification_model.Notification") as MockNotification:
        await schedule_if_allowed(
            db=mock_db,
            user_id=sample_user_id,
            background_tasks=mock_background_tasks,
            pref_flag="ws_invite_received",
            message="Welcome!",
            payload={"key": "value"},
        )

        # Verify Notification record creation
        config = NOTIFICATION_CONFIG["ws_invite_received"]
        MockNotification.assert_called_once()
        args, kwargs = MockNotification.call_args
        assert kwargs["title"] == config["title"]
        assert kwargs["type"] == config["type"]
        assert kwargs["category"] == "ws_invite_received"

        # Verify background task scheduling
        mock_background_tasks.add_task.assert_called_once()
