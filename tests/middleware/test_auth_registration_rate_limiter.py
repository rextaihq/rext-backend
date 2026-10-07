from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request

from src.api.middleware.rate_limiter import (
    REGISTRATION_LIMIT,
    EndpointLimitProfile,
    registration_rate_limit,
)


@pytest.fixture
def mock_registration_request() -> Request:
    request = Mock(spec=Request)
    request.client = Mock()
    request.client.host = "203.0.113.10"
    request.state = Mock()
    request.state.user_id = None
    return request


def test_registration_limit_matches_policy() -> None:
    """10 sign-ups an hour per address: enough for an office or an event behind one network
    (raised from 3 in 9dcbd6f3; the breach check and email verification still apply)."""
    assert REGISTRATION_LIMIT == EndpointLimitProfile(10, 60, "registration")


def test_registration_rate_limiter_initialization() -> None:
    limiter = registration_rate_limit()
    assert limiter.requests == 10
    assert limiter.window_seconds == 3600
    assert limiter.description == "registration"


@pytest.mark.asyncio
async def test_registration_rate_limiter_blocks_the_request_after_the_limit(
    mock_registration_request: Request,
) -> None:
    limiter = registration_rate_limit()

    for _ in range(REGISTRATION_LIMIT.requests):
        await limiter(mock_registration_request)

    with pytest.raises(HTTPException) as exc_info:
        await limiter(mock_registration_request)

    assert exc_info.value.status_code == 429
    assert "registration" in exc_info.value.detail.lower()
