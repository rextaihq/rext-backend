from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.api.middleware.rate_limiter import RateLimiterMiddleware
from src.api.middleware.request_tracker import RequestTrackerMiddleware
from src.api.server import app

# Starlette keeps user_middleware outermost first: the last add_middleware call
# is index 0 and sees the request first.
ORDER = [m.cls for m in app.user_middleware]


def test_cors_is_outermost() -> None:
    # Preflight OPTIONS requests get their headers before anything can end them.
    assert ORDER[0] is CORSMiddleware


def test_proxy_headers_run_before_the_middleware_that_reads_the_client_ip() -> None:
    # Behind Traefik, request.client.host is 10.0.1.2 until ProxyHeadersMiddleware
    # applies X-Forwarded-For. Run after them, it left the rate limiter keying every
    # visitor as ip:10.0.1.2, one budget for the whole site.
    proxy = ORDER.index(ProxyHeadersMiddleware)
    assert proxy < ORDER.index(RateLimiterMiddleware)
    assert proxy < ORDER.index(RequestTrackerMiddleware)
