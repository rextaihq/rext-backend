"""With a catch-all TRUSTED_PROXY_IPS, the limiters key on the connection's own peer
(G82, revnix/rext-control#646).

Under `*`, `0.0.0.0/0` or `::/0`, ProxyHeadersMiddleware hands the app the leftmost
X-Forwarded-For entry, which the caller writes: keyed on it, a caller could pick a
fresh rate-limit key for every request. The requests below go through the real
middleware pair, from the proxy's address, as Traefik's would.
"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.api.config import get_settings
from src.api.middleware import rate_limiter as rate_limiter_module
from src.api.middleware.rate_limiter import EndpointRateLimiter, RateLimiter
from src.api.middleware.request_tracker import RequestTrackerMiddleware
from src.utils.ip_allowlist import (
    DIRECT_PEER_SCOPE_KEY,
    DirectPeerMiddleware,
    limiter_client_host,
    resolve_trusted_proxy_hosts,
)

PROXY = "10.0.1.2"
VISITORS = ("203.0.113.7", "198.51.100.9")
CATCH_ALLS = ["*", "0.0.0.0/0", "::/0"]


@pytest.fixture
def trust(monkeypatch):
    def _set(value: str) -> list:
        monkeypatch.setattr(get_settings(), "TRUSTED_PROXY_IPS", value)
        return resolve_trusted_proxy_hosts(value)

    return _set


def _app(trusted_hosts: list, endpoint_limit: EndpointRateLimiter | None = None) -> FastAPI:
    app = FastAPI()
    limiter = RateLimiter()

    @app.get("/key")
    async def key(request: Request):
        return {"key": limiter.get_client_key(request)}

    if endpoint_limit is not None:

        @app.post("/sensitive", dependencies=[Depends(endpoint_limit)])
        async def sensitive():
            return {"ok": True}

    # As in src/api/server.py: the direct peer is kept first, then the proxy headers apply.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)
    app.add_middleware(DirectPeerMiddleware)
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(PROXY, 51000))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _keys(app: FastAPI) -> list:
    async with _client(app) as client:
        return [
            (await client.get("/key", headers={"X-Forwarded-For": visitor})).json()["key"]
            for visitor in VISITORS
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("catch_all", CATCH_ALLS)
async def test_under_a_catch_all_two_forwarded_addresses_share_one_key(trust, catch_all):
    assert await _keys(_app(trust(catch_all))) == [f"ip:{PROXY}", f"ip:{PROXY}"]


@pytest.mark.asyncio
async def test_behind_a_named_proxy_each_visitor_has_their_own_key(trust):
    assert await _keys(_app(trust(PROXY))) == [f"ip:{visitor}" for visitor in VISITORS]


@pytest.mark.asyncio
@pytest.mark.parametrize(("setting", "second"), [("*", 429), (PROXY, 200)])
async def test_an_endpoint_limit_cant_be_dodged_by_rotating_the_header(
    trust, monkeypatch, setting, second
):
    monkeypatch.setattr(rate_limiter_module, "cache", SimpleNamespace(redis=None))
    app = _app(trust(setting), EndpointRateLimiter(requests=1, description="test"))

    async with _client(app) as client:
        statuses = [
            (await client.post("/sensitive", headers={"X-Forwarded-For": visitor})).status_code
            for visitor in VISITORS
        ]

    assert statuses == [200, second]


@pytest.mark.parametrize("catch_all", CATCH_ALLS)
def test_the_request_log_shows_the_peers_network_under_a_catch_all(trust, catch_all):
    trust(catch_all)
    request = SimpleNamespace(
        scope={DIRECT_PEER_SCOPE_KEY: PROXY}, client=SimpleNamespace(host=VISITORS[0])
    )

    assert RequestTrackerMiddleware._client_network_for_logs(None, request) == "10.0.1.0/24"


def test_a_catch_all_without_a_recorded_peer_shares_one_key(trust):
    trust("*")
    request = SimpleNamespace(scope={}, client=SimpleNamespace(host=VISITORS[0]))

    assert limiter_client_host(request) == "unknown"  # never the caller's header value
