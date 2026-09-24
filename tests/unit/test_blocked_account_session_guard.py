"""A suspended or banned user's already-issued access token must stop working."""

from uuid import uuid4

import pytest

from src.api.middleware.exceptions import RextAuthenticationException
from src.api.schema.response_schemas import ErrorCode
from src.api.security.dependencies import _ensure_active_user_session


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Returns the queued values in order: user status, then session id."""

    def __init__(self, *values):
        self._values = list(values)

    async def execute(self, _statement):
        return _Result(self._values.pop(0))


@pytest.mark.parametrize(
    "status, expected_code",
    [
        ("suspended", ErrorCode.ACCOUNT_SUSPENDED),
        ("banned", ErrorCode.ACCOUNT_BANNED),
    ],
)
async def test_blocked_status_rejects_live_token(status, expected_code):
    payload = {"id": str(uuid4()), "session_id": str(uuid4()), "session_kind": "user"}

    with pytest.raises(RextAuthenticationException) as exc:
        await _ensure_active_user_session(payload, _FakeDB(status, uuid4()))

    assert exc.value.error_code == expected_code


async def test_active_user_with_live_session_passes():
    payload = {"id": str(uuid4()), "session_id": str(uuid4()), "session_kind": "user"}

    await _ensure_active_user_session(payload, _FakeDB("active", uuid4()))


async def test_revoked_session_still_rejected():
    payload = {"id": str(uuid4()), "session_id": str(uuid4()), "session_kind": "user"}

    with pytest.raises(RextAuthenticationException, match="revoked"):
        await _ensure_active_user_session(payload, _FakeDB("active", None))
