"""Focused unit tests for the current asynchronous ``AuthService`` API."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextAuthenticationException,
)
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.user_sessions import UserSession
from src.services.auth_service import AuthService


class ScalarSequence:
    """Small stand-in for SQLAlchemy's scalar result wrapper."""

    def __init__(self, values=()):
        self._values = list(values)

    def all(self):
        return list(self._values)


class Result:
    """Small stand-in for the SQLAlchemy result methods used by the service."""

    def __init__(self, *, scalar=None, scalars=()):
        self._scalar = scalar
        self._scalars = list(scalars)

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return ScalarSequence(self._scalars)


def async_db() -> MagicMock:
    """Return a session mock whose sync and async methods match AsyncSession."""

    return MagicMock(spec=AsyncSession)


def settings(**overrides):
    values = {
        "ACCESS_TOKEN_EXPIRE_MINUTES": 10,
        "AUTH_LOCKOUT_DURATION_HOURS": 1,
        "AUTH_MAX_LOGIN_ATTEMPTS": 3,
        "REFRESH_REPLAY_GRACE_SECONDS": 60,
        "REFRESH_SECRET_KEY": "unit-test-refresh-secret",
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
        "REQUIRE_EMAIL_VERIFICATION": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def active_user(**overrides):
    values = {
        "id": uuid4(),
        "email": "test@example.com",
        "full_name": "Test User",
        "password_hash": "hashed-password",
        "failed_login_attempts": 0,
        "locked_until": None,
        "email_verified": True,
        "deleted_at": None,
        "deactivated_at": None,
        "status": "active",
        "last_login_at": None,
        "login_count": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_register_user_uses_current_email_full_name_api() -> None:
    db = async_db()
    db.execute.return_value = Result(scalar=None)
    service = AuthService(db)

    with (
        patch.object(service, "_get_trial_plan", AsyncMock(return_value=None)),
        patch("src.services.auth_service.validate_password_strength") as validate,
        patch(
            "src.services.auth_service.hash_password_async",
            AsyncMock(return_value="hashed-password"),
        ),
        patch(
            "src.services.auth_service.create_verification_token",
            return_value="verification-token",
        ) as create_verification,
    ):
        user, token = await service.register_user(
            email="test@example.com",
            password="Strong-password-123!",
            full_name="Test User",
        )

    assert user.email == "test@example.com"
    assert user.full_name == "Test User"
    assert user.password_hash == "hashed-password"
    assert token == "verification-token"
    validate.assert_called_once_with("Strong-password-123!")
    create_verification.assert_called_once_with({"user_id": str(user.id)})
    # New accounts start with no global role (workspace roles come with membership),
    # so without a trial plan the user is the only row added.
    assert db.add.call_count == 1
    assert db.add.call_args.args[0] is user
    assert db.flush.await_count == 1  # the user; no role, no trial plan here


@pytest.mark.asyncio
async def test_register_user_rejects_duplicate_email() -> None:
    db = async_db()
    db.execute.return_value = Result(scalar=active_user())

    with pytest.raises(DuplicateResourceException) as error:
        await AuthService(db).register_user(
            email="test@example.com",
            password="Strong-password-123!",
            full_name="Test User",
        )

    assert error.value.context["conflicting_field"] == "email"
    assert "email" in error.value.message.lower()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_login_creates_stable_session_claims_and_refresh_lifetime() -> None:
    db = async_db()
    user = active_user()
    db.execute.side_effect = [
        Result(scalar=user),
        Result(scalars=["admin"]),
        Result(scalars=["user.read", "user.update"]),
    ]
    service = AuthService(db)
    access_exp = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
    refresh_exp = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())

    with (
        patch("src.services.auth_service.get_settings", return_value=settings()),
        patch("src.services.auth_service.verify_password_async", AsyncMock(return_value=True)),
        patch(
            "src.services.auth_service.create_access_token",
            return_value="access-token",
        ) as create_access,
        patch(
            "src.services.auth_service.create_refresh_token",
            return_value="refresh-token",
        ) as create_refresh,
        patch(
            "src.services.auth_service.decode_and_verify_token",
            return_value={"jti": "access-jti", "exp": access_exp},
        ),
        patch(
            "src.services.auth_service.verify_refresh_token",
            return_value={"jti": "refresh-jti", "exp": refresh_exp},
        ),
        patch.object(
            service,
            "_auto_accept_pending_invitations",
            AsyncMock(),
        ),
    ):
        returned_user, tokens = await service.login_user(
            email=user.email,
            password="Strong-password-123!",
            device_info={
                "device_name": "Chrome on Linux",
                "device_type": "desktop",
                "user_agent": "Mozilla/5.0",
                "ip_address": "127.0.0.1",
            },
        )

    access_claims = create_access.call_args.kwargs["data"]
    refresh_claims = create_refresh.call_args.kwargs["data"]
    assert access_claims == refresh_claims
    assert access_claims["session_kind"] == "user"
    assert access_claims["roles"] == ["admin"]
    assert access_claims["permissions"] == ["user.read", "user.update"]
    assert returned_user is user
    assert tokens["expires_in"] == 600
    assert tokens["roles"] == ["admin"]
    assert tokens["permissions"] == ["user.read", "user.update"]

    session = next(
        value for call in db.add.call_args_list if isinstance((value := call.args[0]), UserSession)
    )
    assert str(session.id) == access_claims["session_id"]
    assert session.jti == "access-jti"
    assert int(session.expires_at.timestamp()) == refresh_exp
    assert session.session_metadata["access_expires_at"] == access_exp


@pytest.mark.asyncio
async def test_login_rejects_unknown_email() -> None:
    db = async_db()
    db.execute.return_value = Result(scalar=None)

    with pytest.raises(RextAuthenticationException, match="Invalid email or password"):
        await AuthService(db).login_user(
            email="missing@example.com",
            password="password",
            device_info={},
        )


@pytest.mark.asyncio
async def test_failed_login_updates_lockout_state_and_audit() -> None:
    db = async_db()
    user = active_user(failed_login_attempts=2)
    db.execute.return_value = Result(scalar=user)

    with (
        patch(
            "src.services.auth_service.get_settings",
            return_value=settings(),
        ),
        patch(
            "src.api.config.get_settings",
            return_value=settings(),
        ),
        patch("src.services.auth_service.verify_password_async", AsyncMock(return_value=False)),
        pytest.raises(RextAuthenticationException, match="Invalid email or password"),
    ):
        await AuthService(db).login_user(
            email=user.email,
            password="wrong-password",
            device_info={"ip_address": "127.0.0.1"},
        )

    assert user.failed_login_attempts == 3
    assert user.locked_until > datetime.now(timezone.utc)
    assert db.flush.await_count == 2  # failed counter + audit row


@pytest.mark.asyncio
async def test_login_rejects_currently_locked_account() -> None:
    db = async_db()
    user = active_user(locked_until=datetime.now(timezone.utc) + timedelta(hours=1))
    db.execute.return_value = Result(scalar=user)

    with pytest.raises(RextAuthenticationException, match="temporarily locked"):
        await AuthService(db).login_user(user.email, "password", {})


@pytest.mark.asyncio
async def test_verify_email_decodes_current_token_helper() -> None:
    db = async_db()
    user = active_user(email_verified=False, email_verified_at=None)
    db.execute.return_value = Result(scalar=user)

    with patch(
        "src.services.auth_service.decode_and_verify_token",
        return_value={"user_id": str(user.id)},
    ) as decode:
        result = await AuthService(db).verify_email("verification-token")

    assert result is user
    assert user.email_verified is True
    assert user.email_verified_at.tzinfo is timezone.utc
    decode.assert_called_once_with("verification-token")
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_email_rejects_payload_without_user_id() -> None:
    db = async_db()

    with (
        patch(
            "src.services.auth_service.decode_and_verify_token",
            return_value={},
        ),
        pytest.raises(RextAuthenticationException, match="Invalid token payload"),
    ):
        await AuthService(db).verify_email("invalid-token")

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_rotates_into_deterministic_postgres_lineage() -> None:
    db = async_db()
    service = AuthService(db)
    user_id = uuid4()
    session_id = uuid4()
    now = datetime.now(timezone.utc).replace(microsecond=123456)
    old_exp = int((now + timedelta(days=1)).timestamp())
    successor_exp = int(now.timestamp()) + 7 * 24 * 60 * 60
    user = active_user(id=user_id)

    with (
        patch(
            "src.services.auth_service.verify_refresh_token",
            return_value={
                "id": str(user_id),
                "jti": "old-refresh-jti",
                "exp": old_exp,
                "session_id": str(session_id),
                "session_kind": "user",
            },
        ),
        patch("src.services.auth_service.get_settings", return_value=settings()),
        patch(
            "src.services.auth_service._derive_successor_refresh_jti",
            return_value="successor-refresh-jti",
        ),
        patch(
            "src.services.auth_service.create_refresh_token",
            return_value="successor-refresh-token",
        ) as create_refresh,
        patch(
            "src.services.auth_service.create_access_token",
            return_value="new-access-token",
        ),
        patch(
            "src.services.auth_service.decode_and_verify_token",
            return_value={"jti": "new-access-jti", "exp": 123},
        ),
        patch.object(service, "_acquire_refresh_lock", AsyncMock()),
        patch.object(
            service,
            "_get_blacklist_entry",
            AsyncMock(return_value=None),
        ),
        patch.object(
            service,
            "_database_clock",
            AsyncMock(return_value=now),
        ),
        patch.object(
            service,
            "_load_current_refresh_authorization",
            AsyncMock(return_value=(user, ["admin"], ["user.read"])),
        ),
        patch.object(service, "_update_session_after_refresh", AsyncMock()),
    ):
        tokens, consumed_jti, consumed_exp = await service.refresh_token("old-refresh-token")

    assert consumed_jti == "old-refresh-jti"
    assert consumed_exp == old_exp
    assert tokens == {
        "access_token": "new-access-token",
        "refresh_token": "successor-refresh-token",
        "token_type": "bearer",
        "expires_in": 600,
        "roles": ["admin"],
        "permissions": ["user.read"],
    }
    rotation = next(
        value
        for call in db.add.call_args_list
        if isinstance((value := call.args[0]), TokenBlacklist)
    )
    assert rotation.jti == "old-refresh-jti"
    assert rotation.token_type == "refresh"
    assert rotation.reason == f"refresh:v1:{successor_exp}"
    create_refresh.assert_called_once()
    assert create_refresh.call_args.kwargs["jti"] == "successor-refresh-jti"
    assert int(create_refresh.call_args.kwargs["expires_at"].timestamp()) == successor_exp


@pytest.mark.asyncio
async def test_refresh_rejects_legacy_blacklist_row_without_guessing_successor() -> None:
    db = async_db()
    service = AuthService(db)
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    old_exp = int((now + timedelta(days=1)).timestamp())
    legacy_entry = TokenBlacklist(
        jti="legacy-jti",
        token_type="refresh",
        user_id=user_id,
        revoked_at=now,
        expires_at=datetime.fromtimestamp(old_exp, tz=timezone.utc),
        reason="refresh",
    )

    with (
        patch(
            "src.services.auth_service.verify_refresh_token",
            return_value={"id": str(user_id), "jti": "legacy-jti", "exp": old_exp},
        ),
        patch.object(service, "_acquire_refresh_lock", AsyncMock()),
        patch.object(
            service,
            "_get_blacklist_entry",
            AsyncMock(return_value=legacy_entry),
        ),
        patch.object(
            service,
            "_database_clock",
            AsyncMock(return_value=now),
        ),
        pytest.raises(RextAuthenticationException, match="revoked"),
    ):
        await service.refresh_token("legacy-refresh-token")


@pytest.mark.asyncio
async def test_logout_revokes_refresh_winner_and_exact_session_access() -> None:
    db = async_db()
    service = AuthService(db)
    user_id = uuid4()
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    session = SimpleNamespace(
        id=session_id,
        user_id=user_id,
        jti="winner-access-jti",
        session_metadata={"access_expires_at": int((now + timedelta(minutes=10)).timestamp())},
        expires_at=now + timedelta(days=7),
        is_active=True,
        revoked_at=None,
    )
    db.execute.return_value = Result(scalar=session)

    with (
        patch.object(
            service,
            "_database_clock",
            AsyncMock(return_value=now),
        ),
        patch.object(
            service,
            "_blacklist_access_token_if_absent",
            AsyncMock(side_effect=[True, True]),
        ) as blacklist_access,
        patch.object(
            service,
            "_blacklist_refresh_lineage_tip",
            AsyncMock(return_value=("winner-refresh-jti", 999, True)),
        ),
    ):
        result = await service.logout_user(
            user_id=user_id,
            jti="presented-access-jti",
            exp=123,
            refresh_jti="presented-refresh-jti",
            refresh_exp=456,
            session_id=str(session_id),
            strict_user_session=True,
        )

    assert result.changed is True
    assert result.revoked_access_jti == "winner-access-jti"
    assert result.revoked_refresh_jti == "winner-refresh-jti"
    assert session.is_active is False
    assert session.revoked_at == now
    assert blacklist_access.await_count == 2
    assert blacklist_access.await_args_list[1].kwargs["jti"] == "winner-access-jti"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_logout_requires_access_jti() -> None:
    db = async_db()

    with pytest.raises(RextAuthenticationException, match="missing JTI"):
        await AuthService(db).logout_user(uuid4(), "", 123)

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_reset_uses_reset_token_and_current_decoder() -> None:
    db = async_db()
    user = active_user()
    db.execute.side_effect = [Result(scalar=user), Result(scalar=user)]
    service = AuthService(db)

    with patch(
        "src.services.auth_service.create_reset_token",
        return_value="reset-token",
    ) as create_reset:
        returned_user, token = await service.initiate_password_reset(user.email)

    assert returned_user is user
    assert token == "reset-token"
    create_reset.assert_called_once_with({"user_id": str(user.id), "email": user.email})

    with (
        patch(
            "src.services.auth_service.decode_and_verify_token",
            return_value={"user_id": str(user.id)},
        ),
        patch("src.services.auth_service.validate_password_strength") as validate,
        patch("src.services.auth_service.hash_password_async", AsyncMock(return_value="new-hash")),
    ):
        result = await service.complete_password_reset("reset-token", "New-strong-password-123!")

    assert result is user
    assert user.password_hash == "new-hash"
    validate.assert_called_once_with("New-strong-password-123!")
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_password_reset_reports_missing_user() -> None:
    db = async_db()
    db.execute.return_value = Result(scalar=None)

    with pytest.raises(ResourceNotFoundException):
        await AuthService(db).initiate_password_reset("missing@example.com")
