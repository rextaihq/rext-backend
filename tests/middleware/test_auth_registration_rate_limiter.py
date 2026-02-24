import pytest
from unittest.mock import Mock
from fastapi import Request, HTTPException

from src.api.middleware.rate_limiter import (
    registration_rate_limit,
    REGISTRATION_REQUESTS_PER_HOUR,
    REGISTRATION_WINDOW_MINUTES,
)


@pytest.fixture
def mock_registration_request() -> Request:
    request = Mock(spec=Request)
    request.client = Mock()
    request.client.host = "203.0.113.10"
    request.state = Mock()
    request.state.user_id = None
    return request


def test_registration_constants_match_policy() -> None:
    """Constants must match the documented security policy (3 req / 60 min)."""
    assert REGISTRATION_REQUESTS_PER_HOUR == 3
    assert REGISTRATION_WINDOW_MINUTES == 60


def test_registration_rate_limiter_initialization() -> None:
    limiter = registration_rate_limit()
    assert limiter.requests == 3
    assert limiter.window_seconds == 3600
    assert limiter.description == "registration"


@pytest.mark.asyncio
async def test_registration_rate_limiter_blocks_fourth_request(
    mock_registration_request: Request,
) -> None:
    limiter = registration_rate_limit()

    for _ in range(3):
        await limiter(mock_registration_request)

    with pytest.raises(HTTPException) as exc_info:
        await limiter(mock_registration_request)

    assert exc_info.value.status_code == 429
    assert "registration" in exc_info.value.detail.lower()