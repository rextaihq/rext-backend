"""Unit tests for SecurityService."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.user_models.users import Users
from src.services.security_service import SecurityService


class FakeScalarSequence:
    """Helper to mimic SQLAlchemy scalar sequence results."""

    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


class FakeResult:
    """Helper to mimic SQLAlchemy Result objects."""

    def __init__(self, *, scalar=None, scalars=None, rows=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return FakeScalarSequence(self._scalars)

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_get_failed_logins_returns_paginated_data():
    """Should return formatted failed login data with pagination metadata."""
    # Arrange
    mock_db = AsyncMock()
    now = datetime.now(timezone.utc)
    user_one = Users(
        id=uuid4(),
        email="one@example.com",
        password_hash="hash",
        failed_login_attempts=4,
    )
    user_one.locked_until = now + timedelta(minutes=30)
    user_one.updated_at = now - timedelta(minutes=5)

    user_two = Users(
        id=uuid4(),
        email="two@example.com",
        password_hash="hash",
        failed_login_attempts=2,
    )
    user_two.locked_until = None
    user_two.updated_at = now - timedelta(minutes=10)

    mock_db.execute.side_effect = [
        FakeResult(scalar=2),
        FakeResult(scalars=[user_one, user_two]),
    ]

    service = SecurityService(mock_db)

    # Act
    response = await service.get_failed_logins(limit=2, offset=0)

    # Assert
    assert response["total"] == 2
    assert len(response["users"]) == 2
    first_user = response["users"][0]
    assert first_user["email"] == "one@example.com"
    assert first_user["is_locked"] is True
    assert response["has_more"] is False


@pytest.mark.asyncio
async def test_unlock_account_resets_lock_state():
    """unlock_account should clear locked_until and failed attempts."""
    mock_db = AsyncMock()
    locked_user = Users(
        id=uuid4(),
        email="locked@example.com",
        password_hash="hash",
        failed_login_attempts=5,
    )
    locked_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)

    mock_db.execute.return_value = FakeResult(scalar=locked_user)

    service = SecurityService(mock_db)

    # Act
    result = await service.unlock_account(locked_user.id)

    # Assert
    assert result.locked_until is None
    assert result.failed_login_attempts == 0
    mock_db.flush.assert_awaited_once()
    mock_db.refresh.assert_awaited_once_with(locked_user)


@pytest.mark.asyncio
async def test_unlock_account_raises_when_not_locked():
    """unlock_account should raise when account is not currently locked."""
    mock_db = AsyncMock()
    unlocked_user = Users(
        id=uuid4(),
        email="active@example.com",
        password_hash="hash",
        failed_login_attempts=0,
    )
    unlocked_user.locked_until = None

    mock_db.execute.return_value = FakeResult(scalar=unlocked_user)

    service = SecurityService(mock_db)

    # Act & Assert
    with pytest.raises(RextValidationException):
        await service.unlock_account(unlocked_user.id)


@pytest.mark.asyncio
async def test_reset_failed_attempts_returns_previous_count():
    """reset_failed_attempts should return previous attempt count metadata."""
    mock_db = AsyncMock()
    user = Users(
        id=uuid4(),
        email="reset@example.com",
        password_hash="hash",
        failed_login_attempts=7,
    )
    user.locked_until = None

    mock_db.execute.return_value = FakeResult(scalar=user)

    service = SecurityService(mock_db)

    # Act
    payload = await service.reset_failed_attempts(user.id)

    # Assert
    assert payload["previous_attempts"] == 7
    assert payload["failed_attempts"] == 0
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_security_stats_aggregates_helper_results():
    """get_security_stats should compose values from helper methods."""
    mock_db = AsyncMock()
    service = SecurityService(mock_db)

    service._count_audit_logs = AsyncMock(side_effect=[3, 7, 12, 2, 5, 4, 6])
    service._count_currently_locked = AsyncMock(return_value=4)
    service._count_new_users = AsyncMock(return_value=9)
    service._get_top_failed_login_ips = AsyncMock(return_value=[{"ip": "1.1.1.1", "count": 5}])
    service._get_top_failed_login_users = AsyncMock(
        return_value=[{"email": "one@example.com", "count": 4}]
    )

    # Act
    stats = await service.get_security_stats()

    # Assert
    assert stats["failed_logins_last_24h"] == 3
    assert stats["failed_logins_last_7d"] == 7
    assert stats["failed_logins_last_30d"] == 12
    assert stats["currently_locked_accounts"] == 4
    assert stats["locked_accounts_last_24h"] == 2
    assert stats["password_resets_last_24h"] == 5
    assert stats["password_changes_last_24h"] == 4
    assert stats["new_registrations_last_24h"] == 9
    assert stats["email_verifications_last_24h"] == 6
    assert stats["top_failed_login_ips"][0]["ip"] == "1.1.1.1"


@pytest.mark.asyncio
async def test_get_user_login_history_returns_events():
    """Should return formatted login history from audit logs."""
    mock_db = AsyncMock()
    service = SecurityService(mock_db)

    user = Users(
        id=uuid4(),
        email="history@example.com",
        password_hash="hash",
    )
    audit_event = AuditLog(
        user_id=user.id,
        action="auth.login",
        status="success",
    )
    audit_event.created_at = datetime.now(timezone.utc)
    audit_event.ip_address = "127.0.0.1"
    audit_event.user_agent = "pytest"

    service._get_user_or_404 = AsyncMock(return_value=user)
    mock_db.execute.return_value = FakeResult(scalars=[audit_event])

    # Act
    history = await service.get_user_login_history(user.id, limit=1)

    # Assert
    assert history["email"] == "history@example.com"
    assert history["login_history"][0]["status"] == "success"
    assert history["login_history"][0]["ip_address"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_get_user_or_404_raises_for_missing_user():
    """_get_user_or_404 should raise ResourceNotFoundException when missing."""
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)

    service = SecurityService(mock_db)

    with pytest.raises(ResourceNotFoundException):
        await service._get_user_or_404(uuid4())
