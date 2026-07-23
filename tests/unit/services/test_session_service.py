"""Unit tests for PostgreSQL-authoritative session revocation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.user_models.user_sessions import UserSession
from src.services.session_service import SessionService


class ScalarSequence:
    def __init__(self, values=()):
        self._values = list(values)

    def all(self):
        return list(self._values)


class Result:
    def __init__(self, *, scalar=None, scalars=()):
        self._scalar = scalar
        self._scalars = list(scalars)

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return ScalarSequence(self._scalars)


def async_db() -> MagicMock:
    return MagicMock(spec=AsyncSession)


def session_for(user_id, *, access_jti="access-jti", access_exp=None):
    now = datetime.now(timezone.utc)
    if access_exp is None:
        access_exp = int((now + timedelta(minutes=10)).timestamp())
    return UserSession(
        id=uuid4(),
        user_id=user_id,
        jti=access_jti,
        device_name="Chrome",
        device_type="desktop",
        user_agent="Mozilla/5.0",
        ip_address="127.0.0.1",
        is_active=True,
        created_at=now - timedelta(hours=1),
        last_activity_at=now,
        expires_at=now + timedelta(days=7),
        session_metadata={"access_expires_at": access_exp},
    )


def compiled_params(statement):
    return statement.compile(dialect=postgresql.dialect()).params


@pytest.mark.asyncio
async def test_list_user_sessions_serializes_active_session() -> None:
    db = async_db()
    user_id = uuid4()
    session = session_for(user_id)
    db.execute.return_value = Result(scalars=[session])

    sessions = await SessionService(db).list_user_sessions(user_id)

    assert sessions == [
        {
            "id": str(session.id),
            "device_name": "Chrome",
            "device_type": "desktop",
            "ip_address": "127.0.0.1",
            "user_agent": "Mozilla/5.0",
            "city": None,
            "country": None,
            "created_at": session.created_at.isoformat(),
            "last_activity_at": session.last_activity_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "is_current": False,
            "token_id": "access-jti",
        }
    ]
    assert "user_sessions.is_active IS true" in str(db.execute.await_args.args[0])


@pytest.mark.asyncio
async def test_revoke_session_locks_row_and_blacklists_current_access_expiry() -> None:
    db = async_db()
    user_id = uuid4()
    access_exp = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
    session = session_for(user_id, access_exp=access_exp)
    db.execute.side_effect = [Result(scalar=session), Result()]

    result = await SessionService(db).revoke_session(user_id, session.id)

    assert result["session_id"] == str(session.id)
    assert result["revoked"] is True
    assert session.is_active is False
    assert session.revoked_at.tzinfo is timezone.utc
    assert "FOR UPDATE" in str(db.execute.await_args_list[0].args[0])

    blacklist_statement = db.execute.await_args_list[1].args[0]
    params = compiled_params(blacklist_statement)
    assert params["jti"] == "access-jti"
    assert params["token_type"] == "access"
    assert params["user_id"] == user_id
    assert params["reason"] == "session_revoked"
    assert int(params["expires_at"].timestamp()) == access_exp
    assert "ON CONFLICT (jti) DO NOTHING" in str(blacklist_statement)
    db.add.assert_not_called()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_session_missing_session_raises() -> None:
    db = async_db()
    db.execute.return_value = Result(scalar=None)

    with pytest.raises(ResourceNotFoundException):
        await SessionService(db).revoke_session(uuid4(), uuid4())

    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_all_sessions_uses_postgres_for_each_access_jti() -> None:
    db = async_db()
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    first_exp = int((now + timedelta(minutes=5)).timestamp())
    second_exp = int((now + timedelta(minutes=8)).timestamp())
    first = session_for(user_id, access_jti="jti-1", access_exp=first_exp)
    second = session_for(user_id, access_jti="jti-2", access_exp=second_exp)
    db.execute.side_effect = [Result(scalars=[first, second]), Result(), Result()]

    count = await SessionService(db).revoke_all_sessions(
        user_id,
        exclude_session_id=uuid4(),
        exclude_session_jti="keep-current-jti",
    )

    assert count == 2
    assert first.is_active is False
    assert second.is_active is False
    select_statement = db.execute.await_args_list[0].args[0]
    assert "FOR UPDATE" in str(select_statement)
    assert "user_sessions.id !=" in str(select_statement)
    assert "user_sessions.jti !=" in str(select_statement)

    statements = [call.args[0] for call in db.execute.await_args_list[1:]]
    params = [compiled_params(statement) for statement in statements]
    assert [value["jti"] for value in params] == ["jti-1", "jti-2"]
    assert [int(value["expires_at"].timestamp()) for value in params] == [
        first_exp,
        second_exp,
    ]
    assert all(value["reason"] == "all_sessions_revoked" for value in params)
    assert all("ON CONFLICT (jti) DO NOTHING" in str(statement) for statement in statements)
    db.flush.assert_awaited_once()


def test_access_expiry_prefers_metadata_over_refresh_session_lifetime() -> None:
    user_id = uuid4()
    access_exp = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
    session = session_for(user_id, access_exp=access_exp)

    result = SessionService._access_token_expiry(session)

    assert int(result.timestamp()) == access_exp
    assert result < session.expires_at


def test_access_expiry_supports_legacy_session_fallback() -> None:
    user_id = uuid4()
    session = session_for(user_id)
    session.session_metadata = None

    result = SessionService._access_token_expiry(session)

    assert result == session.expires_at
