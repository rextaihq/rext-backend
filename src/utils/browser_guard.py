"""The public-only rule for the headless browser (G88, revnix/rext-control#661).

The browser fallback renders a customer's page in Chromium, which fetches whatever the page
names: the page itself, its frames, scripts and the redirects of each. public_client() checks
every hop of an httpx fetch and connects only to the address it checked; here every request the
browser makes is fetched through public_client() instead of by Chromium, and the browser is
handed the answer. A route sees only the first address of a redirect chain, so letting Chromium
fetch a checked address would let a redirect go unchecked; public_client() follows the
redirects itself, checking each one, and the browser gets the final response.

What a scrape doesn't need is not fetched at all: images, media and fonts, WebSockets, and
service workers (whose requests bypass the route).
"""

import asyncio
from urllib.parse import urlparse

import httpx

from src.api.lib.logger import auto_logger
from src.utils.url_validator import SSRFValidationError, public_client

logger = auto_logger()

# Schemes that never reach the network.
_IN_PAGE_SCHEMES = {"data", "blob", "about"}
_NETWORK_SCHEMES = {"http", "https"}
# The text and the markup are what a scrape reads.
_SKIPPED_RESOURCES = {"image", "media", "font"}
# httpx has already decoded the body and set its own framing.
_DROPPED_RESPONSE_HEADERS = {
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
}
_DROPPED_REQUEST_HEADERS = {"host", "content-length", "connection", "accept-encoding"}
_REQUEST_TIMEOUT_SECONDS = 15.0
_GUARDED = "_rext_public_only"
# Registering a service worker is refused in every frame before the page's own scripts run.
_NO_SERVICE_WORKERS = (
    "Object.defineProperty(Navigator.prototype, 'serviceWorker', {get: () => undefined});"
)


def _response_headers(response: httpx.Response) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in response.headers.multi_items():
        name = name.lower()
        if name in _DROPPED_RESPONSE_HEADERS:
            continue
        # The browser reads several Set-Cookie values from one header split on newlines.
        headers[name] = f"{headers[name]}\n{value}" if name in headers else value
    return headers


async def _public_only_route(route, request, client: httpx.AsyncClient) -> None:
    """Fetch a request through the public-only client and hand the browser the answer; abort
    it when its address, or an address it redirects to, isn't public."""
    parsed = urlparse(request.url)
    scheme = parsed.scheme.lower()
    if scheme in _IN_PAGE_SCHEMES:
        await route.continue_()
        return
    if scheme not in _NETWORK_SCHEMES or not parsed.hostname:
        logger.warning("Browser request refused", extra={"scheme": scheme or "(none)"})
        await route.abort("blockedbyclient")
        return
    if request.resource_type in _SKIPPED_RESOURCES:
        await route.abort("blockedbyclient")
        return
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _DROPPED_REQUEST_HEADERS
    }
    try:
        response = await client.request(
            request.method, request.url, headers=headers, content=request.post_data_buffer
        )
    except SSRFValidationError as exc:
        logger.warning(
            "Browser request refused",
            extra={"host": parsed.hostname, "reason": type(exc).__name__},
        )
        await route.abort("blockedbyclient")
        return
    except httpx.HTTPError:
        await route.abort("failed")
        return
    await route.fulfill(
        status=response.status_code, headers=_response_headers(response), body=response.content
    )


async def _no_websocket(websocket) -> None:
    await websocket.close()


async def refuse_private_requests(page, context=None, **kwargs):
    """crawl4ai's on_page_context_created hook: every request of the page's browser context goes
    through the public-only client. It runs before the first navigation, and once per context;
    the context's client is closed with the context."""
    target = context if context is not None else page.context
    if getattr(target, _GUARDED, False):
        return page
    client = public_client(follow_redirects=True, timeout=_REQUEST_TIMEOUT_SECONDS)

    async def handler(route, request):
        await _public_only_route(route, request, client)

    await target.add_init_script(_NO_SERVICE_WORKERS)
    await target.route_web_socket("**/*", _no_websocket)
    await target.route("**/*", handler)
    target.on("close", lambda _: asyncio.ensure_future(client.aclose()))
    setattr(target, _GUARDED, True)
    return page


def guard_crawler(crawler) -> None:
    """Install the public-only route on an AsyncWebCrawler before its first arun()."""
    crawler.crawler_strategy.set_hook("on_page_context_created", refuse_private_requests)
