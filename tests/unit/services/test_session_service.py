"""Unit tests for SessionService."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock

from src.services.session_service import SessionService
from src.api.models.user_models.user_sessions import UserSession
from src.api.middleware.exceptions import ResourceNotFoundException


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
async def test_list_user_sessions_returns_active_sessions():
    """list_user_sessions should return serialized active sessions."""
    mock_db = AsyncMock()
    service = SessionService(mock_db)
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    session = UserSession(
        user_id=user_id,
        jti="abc123",
        device_name="Chrome",
        device_type="desktop",
        user_agent="Mozilla",
        ip_address="127.0.0.1",
        is_active=True,
        created_at=now - timedelta(hours=1),
        last_activity_at=now,
        expires_at=now + timedelta(hours=1),
    )

    mock_db.execute.return_value = FakeResult(scalars=[session])

    sessions = await service.list_user_sessions(user_id)

    assert len(sessions) == 1
    assert sessions[0]["device_name"] == "Chrome"
    assert sessions[0]["is_current"] is False
    assert sessions[0]["token_id"] == "abc123"


@pytest.mark.asyncio
async def test_revoke_session_deactivates_and_blacklists():
    """revoke_session should deactivate session and add token to blacklist."""
    mock_db = AsyncMock()
    service = SessionService(mock_db)
    user_id = uuid4()
    session_id = uuid4()
    now = datetime.now(timezone.utc)

    session = UserSession(
        id=session_id,
        user_id=user_id,
        jti="abc123",
        device_name="Chrome",
        device_type="desktop",
        user_agent="Mozilla",
        ip_address="127.0.0.1",
        is_active=True,
        created_at=now - timedelta(hours=1),
        last_activity_at=now,
        expires_at=now + timedelta(hours=1),
    )

    mock_db.execute.return_value = FakeResult(scalar=session)

    result = await service.revoke_session(user_id, session_id)

    assert result["session_id"] == str(session_id)
    assert result["revoked"] is True
    assert session.is_active is False
    assert mock_db.add.call_count == 1
    blacklist_entry = mock_db.add.call_args[0][0]
    assert blacklist_entry.jti == "abc123"
    assert blacklist_entry.token_type == "access"
    assert blacklist_entry.user_id == user_id
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_session_missing_session_raises():
    """revoke_session should raise when session cannot be found."""
    mock_db = AsyncMock()
    service = SessionService(mock_db)
    mock_db.execute.return_value = FakeResult(scalar=None)

    with pytest.raises(ResourceNotFoundException):
        await service.revoke_session(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_revoke_all_sessions_revokes_and_blacklists():
    """revoke_all_sessions should deactivate each session except excluded."""
    mock_db = AsyncMock()
    service = SessionService(mock_db)
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    session_one = UserSession(
        id=uuid4(),
        user_id=user_id,
        jti="jti-1",
        device_name="Chrome",
        device_type="desktop",
        user_agent="Mozilla",
        ip_address="127.0.0.1",
        is_active=True,
        created_at=now - timedelta(hours=3),
        last_activity_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=1),
    )
    session_two = UserSession(
        id=uuid4(),
        user_id=user_id,
        jti="jti-2",
        device_name="Safari",
        device_type="mobile",
        user_agent="Mobile",
        ip_address="192.168.1.10",
        is_active=True,
        created_at=now - timedelta(hours=2),
        last_activity_at=now - timedelta(minutes=10),
        expires_at=now + timedelta(hours=2),
    )
    # Mock should only return session_one since session_two is excluded
    mock_db.execute.return_value = FakeResult(scalars=[session_one])

    revoked = await service.revoke_all_sessions(user_id, exclude_session_id=session_two.id)

    assert revoked == 1
    assert session_one.is_active is False
    assert session_two.is_active is True
    assert mock_db.add.call_count == 1
    blacklist_entry = mock_db.add.call_args[0][0]
    assert blacklist_entry.reason == "all_sessions_revoked"
    mock_db.flush.assert_awaited_once()
