"""A live-progress stream doesn't hold a database connection (G79, rext-control#643).

`get_current_user_sse` runs its token checks on the request's session, and an SSE response
keeps that session for the stream's whole life. Before, the checks' transaction stayed open,
so every open stream held a connection idle in transaction (staging: 96 of 100 connections
with 5 testers). The dependency now ends that transaction, whether the checks pass or not.
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.middleware.exceptions import RextAuthenticationException
from src.api.security import dependencies
from tests.conftest import TEST_DATABASE_URL

PAYLOAD = {"id": "11111111-1111-1111-1111-111111111111", "jti": "jti-1", "session_id": "s-1"}


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        yield db
    await engine.dispose()


@pytest.fixture
def checks(monkeypatch):
    """The token checks, each reading through the session as the real ones do."""
    state = {"blacklisted": False}

    async def is_token_blacklisted(jti, db):
        await db.execute(text("SELECT 1"))
        return state["blacklisted"]

    async def ensure_active_user_session(payload, db):
        await db.execute(text("SELECT 1"))

    monkeypatch.setattr(dependencies, "decode_and_verify_token", lambda token: dict(PAYLOAD))
    monkeypatch.setattr(dependencies, "is_token_blacklisted", is_token_blacklisted)
    monkeypatch.setattr(dependencies, "_ensure_active_user_session", ensure_active_user_session)
    return state


@pytest.mark.asyncio
async def test_a_stream_keeps_no_transaction_open_after_its_checks(session, checks):
    user = await dependencies.get_current_user_sse(authorization="Bearer token", db=session)

    assert user["identity"] == PAYLOAD["id"]
    # The connection went back to the pool: nothing is held while the stream runs.
    assert not session.in_transaction()


@pytest.mark.asyncio
async def test_a_refused_token_leaves_no_transaction_open_either(session, checks):
    checks["blacklisted"] = True

    with pytest.raises(RextAuthenticationException):
        await dependencies.get_current_user_sse(authorization="Bearer token", db=session)

    assert not session.in_transaction()
