"""
Unit tests for src/utils/route_decorators.py

Covers:
  - db_transaction_handler: successful commit path
  - db_transaction_handler: RextAPIException branch (rollback + re-raise)
  - db_transaction_handler: unexpected Exception branch (rollback + error response)
  - db_transaction_handler: HTTPException branch (rollback + re-raise)
  - db_transaction_handler: auto_commit=False skips commit
"""

import pytest
from fastapi import HTTPException

from src.api.middleware.exceptions import RextAPIException
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.route_decorators import db_transaction_handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeDB:
    """Minimal async session stub that tracks rollback/commit calls."""

    def __init__(self):
        self.rolled_back = False
        self.committed = False

    async def rollback(self):
        self.rolled_back = True

    async def commit(self):
        self.committed = True


def _make_rext_exception(message: str = "business error") -> RextAPIException:
    return RextAPIException(
        message=message,
        error_code=ErrorCode.VALIDATION_FAILED,
        status_code=400,
        severity=ErrorSeverity.MEDIUM,
    )


# ---------------------------------------------------------------------------
# Tests: RextAPIException branch (rollback + re-raise)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rext_exception_triggers_rollback_and_reraise():
    """Business exceptions must roll back the transaction and be re-raised."""
    db = FakeDB()

    @db_transaction_handler("test operation", auto_commit=False)
    async def handler(request=None, db=None):
        raise _make_rext_exception()

    with pytest.raises(RextAPIException):
        await handler(request=None, db=db)

    assert db.rolled_back is True, "Transaction must be rolled back on RextAPIException"


@pytest.mark.asyncio
async def test_rext_exception_preserves_original_exception():
    """The re-raised exception must be the original instance (message intact)."""
    db = FakeDB()
    original = _make_rext_exception("specific business error")

    @db_transaction_handler("test operation", auto_commit=False)
    async def handler(request=None, db=None):
        raise original

    with pytest.raises(RextAPIException) as exc_info:
        await handler(request=None, db=db)

    assert exc_info.value is original


# ---------------------------------------------------------------------------
# Tests: Successful path (commit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_path_commits_transaction():
    """On success with auto_commit=True the session must be committed."""
    db = FakeDB()

    @db_transaction_handler("test operation", auto_commit=True)
    async def handler(request=None, db=None):
        return {"result": "ok"}

    await handler(request=None, db=db)

    assert db.committed is True
    assert db.rolled_back is False


@pytest.mark.asyncio
async def test_auto_commit_false_skips_commit():
    """When auto_commit=False the decorator must not call db.commit()."""
    db = FakeDB()

    @db_transaction_handler("test operation", auto_commit=False)
    async def handler(request=None, db=None):
        return {"result": "ok"}

    await handler(request=None, db=db)

    assert db.committed is False


@pytest.mark.asyncio
async def test_a_handler_built_response_passes_through_unchanged():
    """A download (a plain Response, as the audit-log export returns) is not wrapped."""
    from fastapi.responses import Response, StreamingResponse

    db = FakeDB()
    csv = Response(content="id,action\n1,login\n", media_type="text/csv")

    @db_transaction_handler("export", auto_commit=False)
    async def export(request=None, db=None):
        return csv

    assert await export(request=None, db=db) is csv

    stream = StreamingResponse(iter([b"a"]), media_type="application/octet-stream")

    @db_transaction_handler("stream", auto_commit=False)
    async def download(request=None, db=None):
        return stream

    assert await download(request=None, db=db) is stream


@pytest.mark.asyncio
async def test_raw_data_is_still_wrapped_in_a_success_response():
    from fastapi.responses import JSONResponse

    @db_transaction_handler("test operation", auto_commit=False)
    async def handler(request=None, db=None):
        return {"result": "ok"}

    response = await handler(request=None, db=FakeDB())
    assert isinstance(response, JSONResponse)
    assert b'"result":"ok"' in response.body.replace(b" ", b"")


# ---------------------------------------------------------------------------
# Tests: Unexpected Exception branch (rollback + error response)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unexpected_exception_triggers_rollback_and_returns_error():
    """Unexpected exceptions must roll back and return a structured error response."""
    from fastapi.responses import JSONResponse

    db = FakeDB()

    @db_transaction_handler("test operation", auto_commit=False)
    async def handler(request=None, db=None):
        raise RuntimeError("something went wrong")

    response = await handler(request=None, db=db)

    assert db.rolled_back is True
    # Decorator returns a JSONResponse (not raises) for unexpected errors
    assert isinstance(response, JSONResponse)
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Tests: HTTPException branch (rollback + re-raise)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_exception_triggers_rollback_and_reraise():
    """HTTPExceptions must roll back the transaction and be re-raised."""
    db = FakeDB()

    @db_transaction_handler("test operation", auto_commit=False)
    async def handler(request=None, db=None):
        raise HTTPException(status_code=404, detail="not found")

    with pytest.raises(HTTPException) as exc_info:
        await handler(request=None, db=db)

    assert db.rolled_back is True
    assert exc_info.value.status_code == 404
