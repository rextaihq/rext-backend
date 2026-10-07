"""schedule_if_allowed: an in-app notification is stored and its live delivery scheduled only
when the user allows it.

The preferences service, the locked re-check and the database are stubs (the real Notification
model is built, with no session): nothing here reaches a database or the network.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.services.notification_helper import NOTIFICATION_CONFIG, schedule_if_allowed

HELPER = "src.services.notification_helper"


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    no_duplicate = MagicMock()
    no_duplicate.scalar.return_value = 0  # nothing alike within the de-duplication window
    db.execute = AsyncMock(return_value=no_duplicate)
    return db


@pytest.fixture
def mock_background_tasks():
    return MagicMock()


@pytest.fixture
def sample_user_id():
    return str(uuid4())


@pytest.fixture
def sample_prefs():
    return NotificationPreferences(
        user_id=uuid4(),
        email_notifications=True,
        in_app_notifications=True,
        category_preferences={},
    )


@pytest.fixture
def logger(sample_prefs):
    """The helper's preferences read and its locked re-check as stubs; yields its logger."""
    service = MagicMock()
    service.get_or_create = AsyncMock(return_value=sample_prefs)
    with (
        patch(f"{HELPER}.NotificationPreferencesService", return_value=service),
        patch(f"{HELPER}._recheck_preference_enabled", AsyncMock(return_value=True)),
        patch(f"{HELPER}.logger") as mock_logger,
    ):
        yield mock_logger


async def _schedule(db, tasks, user_id, flag, message="Test message", payload=None):
    await schedule_if_allowed(
        db=db,
        user_id=user_id,
        background_tasks=tasks,
        pref_flag=flag,
        message=message,
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_schedule_if_allowed_unknown_flag(
    mock_db, mock_background_tasks, sample_user_id, logger
):
    """A flag the registry doesn't know is logged as an error, and nothing is stored or sent."""
    await _schedule(mock_db, mock_background_tasks, sample_user_id, "nonexistent_flag")

    logger.error.assert_any_call(
        "Notification flag %r not found in NOTIFICATION_REGISTRY – "
        "skipping notification for user %s",
        "nonexistent_flag",
        sample_user_id,
    )
    mock_db.add.assert_not_called()
    mock_background_tasks.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_if_allowed_disabled_global_toggle(
    mock_db, mock_background_tasks, sample_user_id, sample_prefs, logger
):
    """Test that disabled in_app_notifications skips notification."""
    sample_prefs.in_app_notifications = False

    await _schedule(mock_db, mock_background_tasks, sample_user_id, "ws_invite_received")

    logger.debug.assert_any_call("User %s disabled all in-app notifications.", sample_user_id)
    mock_db.add.assert_not_called()
    mock_background_tasks.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_if_allowed_disabled_specific_flag(
    mock_db, mock_background_tasks, sample_user_id, sample_prefs, logger
):
    """Test that a disabled category preference (a JSONB key) skips notification."""
    sample_prefs.set_preference("ws_invite_received", False)

    await _schedule(mock_db, mock_background_tasks, sample_user_id, "ws_invite_received")

    logger.debug.assert_any_call(
        "User %s has preference %s=False – skipping notification.",
        sample_user_id,
        "ws_invite_received",
    )
    mock_db.add.assert_not_called()
    mock_background_tasks.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_if_allowed_virtual_flag(
    mock_db, mock_background_tasks, sample_user_id, logger
):
    """Virtual flags (avatar_uploaded) follow the in-app switch and are stored and sent."""
    await _schedule(
        mock_db, mock_background_tasks, sample_user_id, "avatar_uploaded", "Avatar updated"
    )

    mock_db.add.assert_called_once()
    assert mock_db.add.call_args[0][0].category == "avatar_uploaded"
    mock_background_tasks.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_schedule_if_allowed_success(mock_db, mock_background_tasks, sample_user_id, logger):
    """Test successful notification scheduling and record creation."""
    await _schedule(
        mock_db,
        mock_background_tasks,
        sample_user_id,
        "ws_invite_received",
        "Welcome!",
        {"key": "value"},
    )

    config = NOTIFICATION_CONFIG["ws_invite_received"]
    mock_db.add.assert_called_once()
    notification = mock_db.add.call_args[0][0]
    assert notification.title == config["title"]
    assert notification.type == config["type"]
    assert notification.category == "ws_invite_received"
    mock_background_tasks.add_task.assert_called_once()
