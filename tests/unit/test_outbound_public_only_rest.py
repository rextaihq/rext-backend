"""The remaining fetches of third-party addresses take the public-only rule (G88,
revnix/rext-control#661): listicle mining, the free link checker and the competitor-site
check go through public_client(), and the headless browser aborts every request whose
address isn't public."""

import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import httpx
import pytest

from src.api.tool.tools import broken_link_checker
from src.flow.engines.competitors import listicle
from src.services.brand_voice_service import BrandVoiceService
from src.utils import browser_guard, fast_scraper, helper, url_validator

PUBLIC_IP = "93.184.216.34"
PRIVATE_REDIRECTS = [
    "http://127.0.0.1:8000/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
]


class _Sent(list):
    """The URLs the public transport was asked to send, the verify each transport got, and
    where the public host redirects."""

    def __init__(self) -> None:
        super().__init__()
        self.redirect_to: str | None = None
        self.verify: list[object] = []


@pytest.fixture
def sent(monkeypatch) -> _Sent:
    requests = _Sent()

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if requests.redirect_to and request.url.host != "127.0.0.1":
            return httpx.Response(302, headers={"location": requests.redirect_to})
        return httpx.Response(200, html="<html><body>ok</body></html>")

    def transport(verify=True):
        requests.verify.append(verify)
        return httpx.MockTransport(respond)

    monkeypatch.setattr(url_validator, "PublicOnlyTransport", transport)
    # Any name in these tests resolves to the public address, without a real lookup.
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: [PUBLIC_IP])
    monkeypatch.setattr(fast_scraper, "RETRY_BACKOFF_SECONDS", 0)
    return requests


@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_a_listicle_that_redirects_to_a_private_address_is_not_followed(
    sent, monkeypatch, private
):
    sent.redirect_to = private

    async def no_model(prompt):
        raise AssertionError("a refused page never reaches the model")

    monkeypatch.setattr(listicle, "call_openai_json_array", no_model)
    result = {"link": f"http://{PUBLIC_IP}/best-tools", "title": "Best tools for teams"}

    assert await listicle.mine_all_listicles([result]) == []
    assert sent and set(sent) == {f"http://{PUBLIC_IP}/best-tools"}
    assert sent.verify == [True]  # certificates are checked


async def test_the_link_checker_uses_the_public_only_client(sent):
    assert await broken_link_checker(f"http://{PUBLIC_IP}/") is True
    assert sent == [f"http://{PUBLIC_IP}/"]


@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_the_link_checker_does_not_follow_a_private_redirect(sent, private):
    sent.redirect_to = private
    assert await broken_link_checker(f"http://{PUBLIC_IP}/") is False
    assert sent == [f"http://{PUBLIC_IP}/"]


@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_a_competitor_site_that_redirects_to_a_private_address_is_not_available(
    sent, private
):
    sent.redirect_to = private
    assert await BrandVoiceService._competitor_site_is_available("Acme") is False
    assert sent == ["https://acme.com"]


async def test_a_competitor_site_that_answers_is_available(sent):
    assert await BrandVoiceService._competitor_site_is_available("Acme") is True
    assert sent == ["https://acme.com"]


# -- The headless browser -----------------------------------------------------------


class _Route:
    def __init__(self) -> None:
        self.outcome: str | None = None
        self.fulfilled: dict = {}

    async def continue_(self) -> None:
        self.outcome = "continued"

    async def abort(self, reason: str = "failed") -> None:
        self.outcome = f"aborted:{reason}"

    async def fulfill(self, **kwargs) -> None:
        self.outcome = "fulfilled"
        self.fulfilled = kwargs


def _request(url: str, resource_type: str = "document") -> SimpleNamespace:
    return SimpleNamespace(
        url=url,
        method="GET",
        headers={"user-agent": "test", "host": "ignored", "accept-encoding": "br"},
        post_data_buffer=None,
        resource_type=resource_type,
    )


async def _route(url: str, resource_type: str = "document") -> _Route:
    route = _Route()
    async with url_validator.public_client(follow_redirects=True) as client:
        await browser_guard._public_only_route(route, _request(url, resource_type), client)
    return route


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:2024/ok",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://[::1]/",
    ],
)
async def test_the_browser_never_sends_a_request_to_a_private_address(sent, url):
    route = await _route(url)

    assert route.outcome == "aborted:blockedbyclient"
    assert sent == []


@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_the_browser_never_follows_a_redirect_to_a_private_address(sent, private):
    """A route sees only the first address of a redirect chain: the redirect is followed by
    the public-only client, never by the browser."""
    sent.redirect_to = private

    route = await _route(f"http://{PUBLIC_IP}/page")

    assert route.outcome == "aborted:blockedbyclient"
    assert sent == [f"http://{PUBLIC_IP}/page"]


async def test_a_public_page_is_fetched_by_the_public_client_and_handed_to_the_browser(sent):
    route = await _route(f"http://{PUBLIC_IP}/page")

    assert route.outcome == "fulfilled"
    assert route.fulfilled["status"] == 200
    assert b"ok" in route.fulfilled["body"]
    assert sent == [f"http://{PUBLIC_IP}/page"]


@pytest.mark.parametrize("url", ["file:///etc/hosts", "ftp://example.com/x", "chrome://settings"])
async def test_the_browser_aborts_a_scheme_that_is_not_http(sent, url):
    assert (await _route(url)).outcome == "aborted:blockedbyclient"
    assert sent == []


@pytest.mark.parametrize("url", ["data:image/png;base64,AAAA", "about:blank", "blob:abc"])
async def test_in_page_schemes_are_left_alone(sent, url):
    assert (await _route(url)).outcome == "continued"
    assert sent == []


@pytest.mark.parametrize("resource_type", ["image", "media", "font"])
async def test_what_a_scrape_does_not_read_is_not_fetched(sent, resource_type):
    route = await _route(f"http://{PUBLIC_IP}/asset", resource_type)

    assert route.outcome == "aborted:blockedbyclient"
    assert sent == []


def test_the_handed_back_response_keeps_every_cookie_and_drops_the_framing():
    response = httpx.Response(
        200,
        headers=[
            ("set-cookie", "a=1"),
            ("set-cookie", "b=2"),
            ("content-encoding", "gzip"),
            ("content-length", "10"),
            ("content-type", "text/html"),
        ],
    )

    headers = browser_guard._response_headers(response)

    assert headers == {"set-cookie": "a=1\nb=2", "content-type": "text/html"}


class _Context:
    def __init__(self) -> None:
        self.routes: list[str] = []
        self.socket_routes: list[str] = []
        self.init_scripts: list[str] = []
        self.listeners: list[str] = []

    async def route(self, pattern, handler) -> None:
        self.routes.append(pattern)

    async def route_web_socket(self, pattern, handler) -> None:
        self.socket_routes.append(pattern)

    async def add_init_script(self, script) -> None:
        self.init_scripts.append(script)

    def on(self, event, callback) -> None:
        self.listeners.append(event)


async def test_the_guard_is_installed_once_per_context():
    context = _Context()
    page = SimpleNamespace(context=context)

    assert await browser_guard.refuse_private_requests(page, context=context) is page
    await browser_guard.refuse_private_requests(page, context=context)

    assert context.routes == ["**/*"]
    assert context.socket_routes == ["**/*"]  # no WebSocket connects
    assert len(context.init_scripts) == 1 and "serviceWorker" in context.init_scripts[0]
    assert context.listeners == ["close"]  # the context's client closes with it


class _Crawler:
    """AsyncWebCrawler's shape: the config it was built with and the hooks set on it."""

    made: list["_Crawler"] = []

    def __init__(self, config=None) -> None:
        self.config = config
        self.hooks: dict[str, object] = {}
        self.crawler_strategy = SimpleNamespace(set_hook=self.hooks.__setitem__)
        _Crawler.made.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def arun(self, url, config=None):
        assert self.hooks.get("on_page_context_created") is browser_guard.refuse_private_requests
        return [
            SimpleNamespace(
                url=url, success=False, html="", markdown="", status_code=None, error_message="x"
            )
        ]


@pytest.mark.parametrize("render", ["render_pages", "web_page_scraper"])
async def test_both_browser_renders_install_the_guard_and_check_certificates(monkeypatch, render):
    _Crawler.made.clear()
    monkeypatch.setattr(helper, "AsyncWebCrawler", _Crawler)
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: [PUBLIC_IP])

    if render == "render_pages":
        await helper.render_pages(["https://example.com/"], budget_seconds=5)
    else:
        await helper.web_page_scraper(["https://example.com/"])

    (crawler,) = _Crawler.made
    assert crawler.hooks["on_page_context_created"] is browser_guard.refuse_private_requests
    assert crawler.config.ignore_https_errors is False


# -- A real Chromium, when one is installed ----------------------------------------


class _Hits(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self):  # noqa: N802 (the http.server name)
        _Hits.hits.append(self.path)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


async def test_chromium_never_sends_a_subrequest_to_a_private_address():
    """A page that names a frame, a script and a fetch on 127.0.0.1: with the guard installed,
    none of them reaches the local server."""
    playwright_api = pytest.importorskip("playwright.async_api")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = HTTPServer(("127.0.0.1", port), _Hits)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _Hits.hits.clear()
    try:
        async with playwright_api.async_playwright() as p:
            try:
                browser = await p.chromium.launch()
            except Exception as exc:  # no browser installed where the tests run
                pytest.skip(f"Chromium is not available: {type(exc).__name__}")
            context = await browser.new_context()
            page = await context.new_page()
            await browser_guard.refuse_private_requests(page, context=context)
            private = f"http://127.0.0.1:{port}"
            await page.set_content(
                f'<iframe src="{private}/frame"></iframe><script src="{private}/app.js"></script>'
                f'<script>fetch("{private}/data").catch(() => {{}})</script>'
            )
            await asyncio.sleep(1)
            await browser.close()
    finally:
        server.shutdown()

    assert _Hits.hits == []
