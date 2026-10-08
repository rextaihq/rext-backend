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


class _Rows:
    """The second read's answer: one row, or none."""

    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _RefusingDB:
    """An active user, no active session found, then what the second read of the row says."""

    def __init__(self, second_read):
        self._answers = [_Result("active"), _Result(None), second_read]

    async def execute(self, _statement):
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.mark.parametrize(
    "second_read, said",
    [
        (_Rows(None), "no row with that id"),
        # The case being hunted (rext-control#858): refused, and the row is there and active.
        ("active row", "a row that is active, this user's, made 1.5 s ago (backend 4242)"),
        ("revoked row", "a row that is revoked, this user's, made 90.0 s ago (backend 4242)"),
        (RuntimeError("the database went away"), "it could not be read (RuntimeError)"),
    ],
)
async def test_a_refused_session_says_which_one_and_what_its_row_says(second_read, said, caplog):
    user_id, session_id = uuid4(), uuid4()
    if second_read == "active row":
        second_read = _Rows((True, None, user_id, 1.5, 4242))
    elif second_read == "revoked row":
        second_read = _Rows((False, "2026-10-08T08:24:10Z", user_id, 90, 4242))
    payload = {"id": str(user_id), "session_id": str(session_id), "session_kind": "user"}

    with caplog.at_level("WARNING"):
        with pytest.raises(RextAuthenticationException, match="revoked"):
            await _ensure_active_user_session(payload, _RefusingDB(second_read))

    (line,) = [r.getMessage() for r in caplog.records if "Session refused" in r.getMessage()]
    # The logger renders the line with its time and level around it.
    assert (
        f"Session refused: session ..{str(session_id)[-4:]} of user ..{str(user_id)[-4:]}; "
        f"read again: {said}"
    ) in line
    # Four characters of each id: enough to match a sign-in's own line, not enough to be the id.
    assert str(session_id) not in line and str(user_id) not in line
