"""The SSE streams authenticate with the Authorization header only, never a token in the URL."""

import inspect

import pytest

import src.api.security.dependencies as dependencies
from src.api.middleware.exceptions import RextAuthenticationException


def test_the_query_token_parameter_is_gone():
    assert "token" not in inspect.signature(dependencies.get_current_user_sse).parameters


@pytest.mark.asyncio
async def test_no_header_is_rejected():
    with pytest.raises(RextAuthenticationException) as raised:
        await dependencies.get_current_user_sse(authorization=None, db=None)
    assert raised.value.context["expected_sources"] == ["Authorization header"]


@pytest.mark.asyncio
async def test_a_bearer_header_is_accepted(monkeypatch):
    seen = {}

    def fake_decode(token):
        seen["token"] = token
        return {"id": "user-1", "email": "user@example.com", "jti": "jti-1"}

    async def not_blacklisted(_jti, _db):
        return False

    async def session_ok(_payload, _db):
        return None

    monkeypatch.setattr(dependencies, "decode_and_verify_token", fake_decode)
    monkeypatch.setattr(dependencies, "is_token_blacklisted", not_blacklisted)
    monkeypatch.setattr(dependencies, "_ensure_active_user_session", session_ok)

    user = await dependencies.get_current_user_sse(authorization="Bearer abc.def.ghi", db=None)

    assert seen["token"] == "abc.def.ghi"
    assert user["identity"] == "user-1"
