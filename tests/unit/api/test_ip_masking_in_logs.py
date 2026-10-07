"""Log lines carry a visitor's network, never the address (AGENTS.md: no personal data in a log line).

Once ProxyHeadersMiddleware runs before them, the request tracker and the rate limiter see each
visitor's own IP; they still count and decide by it, and log only its /24 (IPv4) or /48 (IPv6).
"""

from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

import src.api.middleware.rate_limiter as rate_limiter
from src.api.middleware.rate_limiter import RateLimiterMiddleware, key_for_logs
from src.api.middleware.request_tracker import RequestTrackerMiddleware
from src.utils.ip_allowlist import mask_ip

VISITOR = "203.0.113.57"


def _scope(client=(VISITOR, 4321)) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/tools/headline-analyzer",
        "query_string": b"",
        "headers": [],
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
    }


@pytest.mark.parametrize(
    ("host", "masked"),
    [
        (VISITOR, "203.0.113.0/24"),
        ("2001:db8:abcd:12:1:2:3:4", "2001:db8:abcd::/48"),
        ("unknown", "unknown"),
        ("testclient", "testclient"),
        (None, "unknown"),
    ],
)
def test_an_address_becomes_its_network(host, masked) -> None:
    assert mask_ip(host) == masked


@pytest.mark.parametrize(
    ("key", "logged"),
    [
        (f"ip:{VISITOR}", "ip:203.0.113.0/24"),
        (f"email:0a1b2c3d4e5f:ip:{VISITOR}", "email:0a1b2c3d4e5f:ip:203.0.113.0/24"),
        ("ip:2001:db8:abcd:12::1", "ip:2001:db8:abcd::/48"),
        ("user:6f1c2d", "user:6f1c2d"),
    ],
)
def test_a_rate_limit_key_logs_the_network(key, logged) -> None:
    assert key_for_logs(key) == logged


def test_the_request_log_shows_the_network() -> None:
    request = Request(_scope())

    assert RequestTrackerMiddleware(app=None)._client_network_for_logs(request) == "203.0.113.0/24"


@pytest.mark.asyncio
async def test_a_refused_request_logs_the_network_and_counts_the_address(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(
        rate_limiter, "log_with_level", lambda _logger, _level, message: messages.append(message)
    )
    middleware = RateLimiterMiddleware(app=None)
    check = AsyncMock(return_value=(False, 30, "minute"))
    monkeypatch.setattr(middleware.limiter, "check_rate_limit", check)
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    async def send(message: dict) -> None:
        sent.append(message)

    await middleware(_scope(), receive, send)

    check.assert_awaited_once_with(f"ip:{VISITOR}")
    assert sent[0]["status"] == 429
    assert len(messages) == 1
    assert "ip:203.0.113.0/24" in messages[0]
    assert VISITOR not in messages[0]
