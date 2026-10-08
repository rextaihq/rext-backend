"""A session check that cannot read the database answers 503, never 401 (rext-control#874).

The token's blacklist row and the session's row are read on every request. On staging on
8 October 2026 a stopping process answered four signed-in requests 401 "Token validation failed"
while its database connections were going away, and the dashboard signs a person out on a 401.
The caller's token had not been found wanting: the server could not look.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import InvalidRequestError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from src.api.middleware.exceptions import DatabaseConnectionException, RextAuthenticationException
from src.api.security import dependencies

PAYLOAD = {
    "id": "11111111-1111-1111-1111-111111111111",
    "jti": "jti-1",
    "session_kind": "user",
    "session_id": "22222222-2222-2222-2222-222222222222",
}

AWAY = [
    OperationalError("select 1", {}, ConnectionResetError("connection was closed")),
    InvalidRequestError("This connection is closed"),
    PoolTimeout("QueuePool limit of size 20 overflow 10 reached"),
    ConnectionResetError("connection reset by peer"),
    TimeoutError("timed out"),
]
VARIANTS = [dependencies.get_current_user, dependencies.get_current_user_sse]


class _Session:
    """As much of a database session as the checks use; every read does what the test says."""

    def __init__(self, read):
        self._read = read
        self.rolled_back = 0

    async def execute(self, *args, **kwargs):
        return self._read()

    async def rollback(self):
        self.rolled_back += 1


def _raises(error):
    def read():
        raise error

    return read


@pytest.fixture
def token(monkeypatch):
    """A token that decodes; the blacklist read passes unless a test says otherwise."""

    async def not_blacklisted(jti, db):
        return False

    monkeypatch.setattr(dependencies, "decode_and_verify_token", lambda token: dict(PAYLOAD))
    monkeypatch.setattr(dependencies, "is_token_blacklisted", not_blacklisted)


@pytest.mark.asyncio
@pytest.mark.parametrize("check", VARIANTS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("error", AWAY, ids=lambda e: type(e).__name__)
async def test_a_session_read_that_fails_is_a_503(token, check, error):
    with pytest.raises(DatabaseConnectionException) as refused:
        await check(authorization="Bearer token", db=_Session(_raises(error)))

    assert refused.value.status_code == 503
    assert refused.value.message == "We could not check your session just now. Please try again."
    # Nothing of the failure goes to the caller: not the query, not an address.
    assert "select" not in str(refused.value.to_dict()).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("check", VARIANTS, ids=lambda f: f.__name__)
async def test_a_blacklist_read_that_fails_is_a_503_too(token, check, monkeypatch):
    async def blacklist_read_fails(jti, db):
        raise OperationalError("select 1", {}, ConnectionResetError("connection was closed"))

    monkeypatch.setattr(dependencies, "is_token_blacklisted", blacklist_read_fails)

    with pytest.raises(DatabaseConnectionException) as refused:
        await check(authorization="Bearer token", db=_Session(lambda: None))

    assert refused.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("check", VARIANTS, ids=lambda f: f.__name__)
async def test_a_token_that_does_not_decode_is_still_a_401(check, monkeypatch):
    def bad_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr(dependencies, "decode_and_verify_token", bad_token)

    with pytest.raises(RextAuthenticationException) as refused:
        await check(authorization="Bearer token", db=_Session(lambda: None))

    assert refused.value.status_code == 401
    assert refused.value.message == "Invalid authentication token"


@pytest.mark.asyncio
@pytest.mark.parametrize("check", VARIANTS, ids=lambda f: f.__name__)
async def test_a_blacklisted_token_is_still_a_401(token, check, monkeypatch):
    async def blacklisted(jti, db):
        return True

    monkeypatch.setattr(dependencies, "is_token_blacklisted", blacklisted)

    with pytest.raises(RextAuthenticationException) as refused:
        await check(authorization="Bearer token", db=_Session(lambda: None))

    assert refused.value.status_code == 401
    assert refused.value.message == "Token has been revoked"


@pytest.mark.asyncio
@pytest.mark.parametrize("check", VARIANTS, ids=lambda f: f.__name__)
async def test_a_session_that_was_ended_is_still_its_own_401(token, check):
    class _NoRow:
        def scalar_one_or_none(self):
            return None

        def first(self):
            return None

        def one_or_none(self):
            return None

    with pytest.raises(RextAuthenticationException) as refused:
        await check(authorization="Bearer token", db=_Session(lambda: _NoRow()))

    assert refused.value.status_code == 401
    assert refused.value.message == "Authentication session has been revoked"


@pytest.mark.asyncio
async def test_a_stream_still_ends_its_transaction_when_the_read_fails(token):
    session = _Session(_raises(ConnectionResetError("connection reset by peer")))

    with pytest.raises(DatabaseConnectionException):
        await dependencies.get_current_user_sse(authorization="Bearer token", db=session)

    assert session.rolled_back == 1
