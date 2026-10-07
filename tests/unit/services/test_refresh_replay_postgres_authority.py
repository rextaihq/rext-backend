"""Focused tests for PostgreSQL-authoritative refresh-token replay."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.api.config import get_settings
from src.api.middleware.exceptions import RextAuthenticationException
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.routes.users import auth as auth_routes
from src.api.schema.user_schema import RefreshTokenRequest
from src.api.security import token_utils
from src.api.security.dependencies import _ensure_active_user_session
from src.api.security.token_utils import (
    create_access_token,
    create_refresh_token,
    decode_and_verify_token,
    verify_refresh_token,
)
from src.services.auth_service import (
    AuthService,
    _derive_successor_refresh_jti,
    _parse_rotation_reason,
    _refresh_advisory_lock_key,
)
from src.services.session_service import SessionService


class _MemoryDatabase:
    def __init__(self) -> None:
        self.blacklist: dict[str, TokenBlacklist] = {}
        self.session = None
        self.statements = []
        self.user_exists = True

    def add(self, value) -> None:
        if isinstance(value, TokenBlacklist):
            self.blacklist[value.jti] = value

    async def flush(self) -> None:
        return None

    async def execute(self, statement):
        self.statements.append(statement)
        return _ScalarResult(self.session)

    async def scalar(self, statement):
        """The refresh's check that the token's user still exists."""
        self.statements.append(statement)
        return uuid4() if self.user_exists else None


class _ConflictDatabase(_MemoryDatabase):
    """Emulate a winner followed by a duplicate-key loser."""

    def __init__(self) -> None:
        super().__init__()
        self.insert_results = ["access-jti", None]

    async def execute(self, statement):
        self.statements.append(statement)
        return _ScalarResult(self.insert_results.pop(0))


class _ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _RefreshHarness(AuthService):
    """Runs the real lineage algorithm with deterministic in-memory I/O."""

    def __init__(self, db: _MemoryDatabase, now: datetime, user_id) -> None:
        super().__init__(db)
        self.now = now
        self.user_id = user_id
        self.roles = ["user"]
        self.permissions = ["user.read"]
        self.events: list[tuple[str, str]] = []
        self.access_payloads: list[dict] = []

    async def _acquire_refresh_lock(self, jti: str) -> None:
        self.events.append(("lock", jti))

    async def _get_blacklist_entry(self, jti: str):
        self.events.append(("read", jti))
        return self.db.blacklist.get(jti)

    async def _database_clock(self) -> datetime:
        return self.now

    async def _blacklist_access_token_if_absent(
        self, *, jti: str, user_id, revoked_at: datetime, expires_at: int
    ) -> bool:
        if jti in self.db.blacklist:
            return False
        self.db.add(
            TokenBlacklist(
                jti=jti,
                token_type="access",
                user_id=user_id,
                revoked_at=revoked_at,
                expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
                reason="logout",
            )
        )
        return True

    async def _load_current_refresh_authorization(self, user_id):
        user = SimpleNamespace(
            id=self.user_id,
            email="current@example.com",
            status="active",
        )
        return user, list(self.roles), list(self.permissions)

    async def _update_session_after_refresh(
        self,
        *,
        db_user,
        access_token: str,
        session_id,
        strict_user_session: bool,
        refresh_exp: int,
    ) -> None:
        self.access_payloads.append(decode_and_verify_token(access_token, expected_type="access"))


def _original_refresh_token(user_id, old_jti: str, now: datetime) -> str:
    return create_refresh_token(
        {
            "id": str(user_id),
            "session_id": str(uuid4()),
            "session_kind": "user",
        },
        jti=old_jti,
        expires_at=now + timedelta(days=1),
    )


def test_successor_derivation_and_explicit_token_are_deterministic() -> None:
    revoked_at = datetime(2026, 7, 22, 10, 11, 12, 345678, tzinfo=timezone.utc)
    old_jti = "original-jti"

    first_jti = _derive_successor_refresh_jti(old_jti, revoked_at)
    second_jti = _derive_successor_refresh_jti(old_jti, revoked_at)
    assert first_jti == second_jti
    assert first_jti != _derive_successor_refresh_jti("another-jti", revoked_at)
    assert -(2**63) <= _refresh_advisory_lock_key(old_jti) < 2**63

    expires_at = revoked_at + timedelta(days=7)
    claims = {"id": str(uuid4()), "session_id": str(uuid4())}
    first_token = create_refresh_token(claims, jti=first_jti, expires_at=expires_at)
    second_token = create_refresh_token(claims, jti=first_jti, expires_at=expires_at)
    assert first_token == second_token


@pytest.mark.asyncio
async def test_a_deleted_users_refresh_token_is_refused() -> None:
    """A token whose account no longer exists gets a 401, and nothing is written."""
    now = datetime.now(timezone.utc)
    user_id = uuid4()
    db = _MemoryDatabase()
    db.user_exists = False
    service = _RefreshHarness(db, now, user_id)

    with pytest.raises(RextAuthenticationException, match="no longer exists"):
        await service.refresh_token(_original_refresh_token(user_id, str(uuid4()), now))

    assert db.blacklist == {}
    assert service.access_payloads == []


@pytest.mark.asyncio
async def test_replay_uses_db_row_without_redis_and_reloads_authorization() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=123456)
    user_id = uuid4()
    old_jti = str(uuid4())
    original = _original_refresh_token(user_id, old_jti, now)
    db = _MemoryDatabase()
    service = _RefreshHarness(db, now, user_id)

    first_tokens, _, _ = await service.refresh_token(original)
    first_refresh_payload = verify_refresh_token(first_tokens["refresh_token"])
    assert list(db.blacklist) == [old_jti]
    assert db.blacklist[old_jti].reason.startswith("refresh:v1:")
    assert service.events[:2] == [("lock", old_jti), ("read", old_jti)]

    service.events.clear()
    service.now = now + timedelta(seconds=1)
    service.roles = ["admin"]
    service.permissions = ["user.read", "user.update"]
    replay_tokens, _, _ = await service.refresh_token(original)

    # The durable successor refresh token converges, while the access token is
    # freshly authorized from the database on every successful replay.
    assert replay_tokens["refresh_token"] == first_tokens["refresh_token"]
    replay_access = decode_and_verify_token(replay_tokens["access_token"], expected_type="access")
    assert replay_access["roles"] == ["admin"]
    assert replay_access["permissions"] == ["user.read", "user.update"]
    assert replay_tokens["access_token"] != first_tokens["access_token"]
    assert service.events[:4] == [
        ("lock", old_jti),
        ("read", old_jti),
        ("lock", first_refresh_payload["jti"]),
        ("read", first_refresh_payload["jti"]),
    ]


@pytest.mark.asyncio
async def test_replay_walks_to_first_unrevoked_successor() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=654321)
    user_id = uuid4()
    old_jti = str(uuid4())
    original = _original_refresh_token(user_id, old_jti, now)
    db = _MemoryDatabase()
    service = _RefreshHarness(db, now, user_id)

    first_tokens, _, _ = await service.refresh_token(original)
    first_successor = verify_refresh_token(first_tokens["refresh_token"])["jti"]
    service.now = now + timedelta(seconds=10)
    second_tokens, _, _ = await service.refresh_token(first_tokens["refresh_token"])
    second_successor = verify_refresh_token(second_tokens["refresh_token"])["jti"]

    service.now = now + timedelta(seconds=20)
    service.events.clear()
    replay_tokens, _, _ = await service.refresh_token(original)

    assert replay_tokens["refresh_token"] == second_tokens["refresh_token"]
    assert [event for event in service.events if event[0] == "lock"] == [
        ("lock", old_jti),
        ("lock", first_successor),
        ("lock", second_successor),
    ]
    assert set(db.blacklist) == {old_jti, first_successor}


@pytest.mark.asyncio
async def test_replay_is_rejected_after_configured_grace() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=222222)
    user_id = uuid4()
    old_jti = str(uuid4())
    original = _original_refresh_token(user_id, old_jti, now)
    db = _MemoryDatabase()
    service = _RefreshHarness(db, now, user_id)
    await service.refresh_token(original)

    service.now = now + timedelta(seconds=get_settings().REFRESH_REPLAY_GRACE_SECONDS + 1)
    with pytest.raises(RextAuthenticationException, match="revoked"):
        await service.refresh_token(original)


@pytest.mark.asyncio
async def test_logout_follows_rotation_and_revokes_current_tip() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=333333)
    user_id = uuid4()
    old_jti = str(uuid4())
    original = _original_refresh_token(user_id, old_jti, now)
    original_exp = verify_refresh_token(original)["exp"]
    db = _MemoryDatabase()
    service = _RefreshHarness(db, now, user_id)
    first_tokens, _, _ = await service.refresh_token(original)
    successor_jti = verify_refresh_token(first_tokens["refresh_token"])["jti"]

    service.now = now + timedelta(seconds=1)
    (
        revoked_jti,
        revoked_exp,
        changed,
    ) = await service._blacklist_refresh_lineage_tip(
        user_id=user_id, refresh_jti=old_jti, refresh_exp=original_exp
    )
    assert revoked_jti == successor_jti
    assert revoked_exp == verify_refresh_token(first_tokens["refresh_token"])["exp"]
    assert changed is True
    assert db.blacklist[successor_jti].reason == "logout"

    with pytest.raises(RextAuthenticationException, match="revoked"):
        await service.refresh_token(original)


@pytest.mark.asyncio
async def test_logout_losing_refresh_race_revokes_winner_access_token() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=555555)
    user_id = uuid4()
    old_refresh_jti = str(uuid4())
    original = _original_refresh_token(user_id, old_refresh_jti, now)
    original_payload = verify_refresh_token(original)
    db = _MemoryDatabase()
    service = _RefreshHarness(db, now, user_id)

    winner_tokens, _, _ = await service.refresh_token(original)
    winner_access = decode_and_verify_token(winner_tokens["access_token"], expected_type="access")
    db.session = SimpleNamespace(
        id=original_payload["session_id"],
        user_id=user_id,
        jti=winner_access["jti"],
        expires_at=datetime.fromtimestamp(winner_access["exp"], tz=timezone.utc),
        is_active=True,
        revoked_at=None,
        session_metadata={"access_expires_at": winner_access["exp"]},
    )

    result = await service.logout_user(
        user_id=user_id,
        jti="presented-old-access-jti",
        exp=int((now + timedelta(minutes=10)).timestamp()),
        refresh_jti=old_refresh_jti,
        refresh_exp=original_payload["exp"],
        session_id=original_payload["session_id"],
        strict_user_session=True,
    )

    assert result.revoked_access_jti == winner_access["jti"]
    assert db.blacklist[winner_access["jti"]].reason == "logout"
    assert db.session.is_active is False


@pytest.mark.asyncio
async def test_strict_session_refresh_never_falls_back_or_recreates() -> None:
    user_id = uuid4()
    inactive_session = SimpleNamespace(is_active=False)
    db = _MemoryDatabase()
    db.session = inactive_session
    service = AuthService(db)
    access_token = create_access_token({"id": str(user_id)})

    with pytest.raises(RextAuthenticationException, match="revoked"):
        await service._update_session_after_refresh(
            db_user=SimpleNamespace(id=user_id),
            access_token=access_token,
            session_id=str(uuid4()),
            strict_user_session=True,
            refresh_exp=int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp()),
        )

    assert db.session is inactive_session


@pytest.mark.asyncio
async def test_session_lifetime_tracks_refresh_not_access_expiry() -> None:
    now = datetime.now(timezone.utc)
    user_id = uuid4()
    active_session = SimpleNamespace(
        is_active=True,
        jti="old-access",
        expires_at=now + timedelta(minutes=10),
        session_metadata={},
        last_activity_at=now,
    )
    db = _MemoryDatabase()
    db.session = active_session
    service = AuthService(db)
    access_token = create_access_token({"id": str(user_id)})
    access_payload = decode_and_verify_token(access_token)
    refresh_exp = int((now + timedelta(days=7)).timestamp())

    await service._update_session_after_refresh(
        db_user=SimpleNamespace(id=user_id),
        access_token=access_token,
        session_id=str(uuid4()),
        strict_user_session=True,
        refresh_exp=refresh_exp,
    )

    assert int(active_session.expires_at.timestamp()) == refresh_exp
    assert active_session.session_metadata["access_expires_at"] == access_payload["exp"]
    assert any("FOR UPDATE" in str(statement) for statement in db.statements)


@pytest.mark.asyncio
async def test_remote_session_revocation_locks_row_and_uses_postgres_only() -> None:
    now = datetime.now(timezone.utc)
    user_id = uuid4()
    session_id = uuid4()
    db = _MemoryDatabase()
    db.session = SimpleNamespace(
        id=session_id,
        user_id=user_id,
        jti=str(uuid4()),
        expires_at=now + timedelta(days=7),
        session_metadata={"access_expires_at": int((now + timedelta(minutes=10)).timestamp())},
        is_active=True,
        revoked_at=None,
    )

    result = await SessionService(db).revoke_session(user_id, session_id)

    assert result["revoked"] is True
    assert db.session.is_active is False
    assert any("FOR UPDATE" in str(statement) for statement in db.statements)


@pytest.mark.asyncio
async def test_duplicate_access_blacklist_insert_is_an_idempotent_race() -> None:
    now = datetime.now(timezone.utc)
    user_id = uuid4()
    db = _ConflictDatabase()
    service = AuthService(db)

    first_changed = await service._blacklist_access_token_if_absent(
        jti="access-jti",
        user_id=user_id,
        revoked_at=now,
        expires_at=int((now + timedelta(minutes=10)).timestamp()),
    )
    duplicate_changed = await service._blacklist_access_token_if_absent(
        jti="access-jti",
        user_id=user_id,
        revoked_at=now,
        expires_at=int((now + timedelta(minutes=10)).timestamp()),
    )

    assert first_changed is True
    assert duplicate_changed is False
    for statement in db.statements:
        sql = str(statement)
        assert "ON CONFLICT (jti) DO NOTHING" in sql
        assert "RETURNING token_blacklist.jti" in sql


@pytest.mark.asyncio
async def test_revoked_session_denies_every_replay_issued_access_token() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=666666)
    user_id = uuid4()
    original = _original_refresh_token(user_id, str(uuid4()), now)
    db = _MemoryDatabase()
    service = _RefreshHarness(db, now, user_id)
    issued_access_tokens = []

    for offset in range(3):
        service.now = now + timedelta(seconds=offset)
        tokens, _, _ = await service.refresh_token(original)
        issued_access_tokens.append(tokens["access_token"])

    assert len({decode_and_verify_token(token)["jti"] for token in issued_access_tokens}) == 3

    # The stable session has been remotely revoked/deleted. Per-session auth
    # rejects every sibling access JTI, not only the one stored most recently.
    db.session = None
    for token in issued_access_tokens:
        with pytest.raises(RextAuthenticationException, match="revoked"):
            await _ensure_active_user_session(decode_and_verify_token(token), db)


@pytest.mark.asyncio
async def test_impersonation_refresh_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    user_id = uuid4()
    token = create_refresh_token(
        {
            "id": str(user_id),
            "session_id": str(uuid4()),
            "session_kind": "impersonation",
        },
        expires_at=now + timedelta(days=1),
    )
    service = _RefreshHarness(_MemoryDatabase(), now, user_id)

    with pytest.raises(RextAuthenticationException, match="Impersonation"):
        await service.refresh_token(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["refresh", "logout", "refresh:v1:not-a-number"])
async def test_legacy_or_nonrotation_blacklist_rows_never_replay(reason: str) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=111111)
    user_id = uuid4()
    old_jti = str(uuid4())
    original = _original_refresh_token(user_id, old_jti, now)
    old_exp = verify_refresh_token(original)["exp"]
    db = _MemoryDatabase()
    db.blacklist[old_jti] = TokenBlacklist(
        jti=old_jti,
        token_type="refresh",
        user_id=user_id,
        revoked_at=now,
        expires_at=datetime.fromtimestamp(old_exp, tz=timezone.utc),
        reason=reason,
    )
    service = _RefreshHarness(db, now + timedelta(seconds=1), user_id)

    with pytest.raises(RextAuthenticationException, match="revoked"):
        await service.refresh_token(original)


@pytest.mark.asyncio
async def test_rotation_chain_has_a_hard_safety_bound() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=444444)
    user_id = uuid4()
    old_jti = str(uuid4())
    original = _original_refresh_token(user_id, old_jti, now)
    db = _MemoryDatabase()
    service = _RefreshHarness(db, now, user_id)
    current = original

    # Build the maximum supported number of consumed generations. Replaying
    # the oldest token must fail rather than scan an unbounded/cyclic lineage.
    for offset in range(32):
        service.now = now + timedelta(seconds=offset)
        tokens, _, _ = await service.refresh_token(current)
        current = tokens["refresh_token"]

    service.now = now + timedelta(seconds=32)
    with pytest.raises(RextAuthenticationException, match="too long"):
        await service.refresh_token(original)


def test_only_exact_versioned_rotation_reason_is_parsed() -> None:
    assert _parse_rotation_reason("refresh:v1:123") == 123
    assert _parse_rotation_reason("refresh") is None
    assert _parse_rotation_reason("refresh:v2:123") is None
    assert _parse_rotation_reason("refresh:v1:123x") is None


@pytest.mark.asyncio
async def test_refresh_route_commits_before_optional_cache_write(monkeypatch) -> None:
    events: list[str] = []
    tokens = {
        "access_token": "access",
        "refresh_token": "refresh",
        "token_type": "bearer",
        "expires_in": 600,
    }

    class _FakeAuthService:
        def __init__(self, db) -> None:
            pass

        async def refresh_token(self, raw_token: str):
            return tokens, "old-jti", 2_000_000_000

    class _FakeRouteDatabase:
        async def commit(self) -> None:
            events.append("commit")

    async def _cache_after_commit(jti: str, expires_at: int) -> None:
        events.append("cache")

    monkeypatch.setattr(auth_routes, "AuthService", _FakeAuthService)
    monkeypatch.setattr(token_utils, "blacklist_token_in_cache", _cache_after_commit)

    response = await auth_routes.refresh_access_token.__wrapped__(
        request=None,
        token_data=RefreshTokenRequest(refresh_token="raw-refresh"),
        db=_FakeRouteDatabase(),
    )

    assert response.status_code == 200
    assert events == ["commit", "cache"]
