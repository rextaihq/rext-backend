"""The remaining fetches of third-party addresses take the public-only rule (G88,
revnix/rext-control#661): listicle mining, the free link checker and the competitor-site
check go through public_client(), and the headless browser aborts every request whose
address isn't public."""

import asyncio
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import httpx
import pytest

from src.api.tool.tools import broken_link_checker
from src.flow.engines.competitors import listicle
from src.services.brand_voice_service import BrandVoiceService
from src.utils import browser_guard, fast_scraper, helper, url_validator

_open_connection = asyncio.open_connection

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


# -- The headless browser: every connection goes through PublicOnlyProxy -------------


class _Hits(BaseHTTPRequestHandler):
    """A local HTTP server that records every request it gets."""

    hits: list[tuple[str, str]] = []
    redirect_to: str | None = None

    def do_GET(self):  # noqa: N802 (the http.server name)
        _Hits.hits.append((self.server.server_address[0], self.path))
        if self.path.startswith("/redirect") and _Hits.redirect_to:
            self.send_response(302)
            self.send_header("Location", _Hits.redirect_to)
            self.end_headers()
            return
        body = f"ok {self.path} connection={self.headers.get('Connection')}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _serve(host: str) -> int:
    """Start a recording server on ``host`` and return its port (skips where the host can't
    be bound, e.g. 127.0.0.2 outside Linux)."""
    try:
        server = HTTPServer((host, 0), _Hits)
    except OSError as exc:
        pytest.skip(f"can't listen on {host}: {exc}")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


@pytest.fixture
def servers(monkeypatch):
    """127.0.0.2 plays a public site (the check is told so); 127.0.0.1 is private."""
    original = url_validator._check_ip_blocked

    def check(ip):
        if str(ip) != "127.0.0.2":
            original(ip)

    monkeypatch.setattr(url_validator, "_check_ip_blocked", check)
    _Hits.hits.clear()
    _Hits.redirect_to = None
    return SimpleNamespace(public=_serve("127.0.0.2"), private=_serve("127.0.0.1"))


def _private_hits() -> list[str]:
    return [path for host, path in _Hits.hits if host == "127.0.0.1"]


async def _through(proxy, url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(proxy=proxy.url, trust_env=False) as client:
        return await client.get(url, **kwargs)


async def test_the_proxy_forwards_a_request_to_a_public_address(servers):
    async with browser_guard.PublicOnlyProxy() as proxy:
        response = await _through(proxy, f"http://127.0.0.2:{servers.public}/page?q=1")

    assert response.status_code == 200
    # Forwarded in origin form, on a connection of its own.
    assert response.text == "ok /page?q=1 connection=close"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:{private}/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
    ],
)
async def test_the_proxy_refuses_a_private_address(servers, url):
    async with browser_guard.PublicOnlyProxy() as proxy:
        response = await _through(proxy, url.format(private=servers.private))

    assert response.status_code == 403
    assert _private_hits() == []


async def test_the_proxy_refuses_a_name_that_resolves_privately(servers, monkeypatch):
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: ["10.1.2.3"])
    async with browser_guard.PublicOnlyProxy() as proxy:
        response = await _through(proxy, "http://internal.example.com/")

    assert response.status_code == 403


async def test_each_hop_of_a_redirect_is_checked(servers):
    """A redirect is a new request through the proxy: the private hop is refused there."""
    _Hits.redirect_to = f"http://127.0.0.1:{servers.private}/secret"
    async with browser_guard.PublicOnlyProxy() as proxy:
        response = await _through(
            proxy, f"http://127.0.0.2:{servers.public}/redirect", follow_redirects=True
        )

    assert response.status_code == 403
    assert _private_hits() == []


async def test_a_tunnel_opens_only_to_a_public_address(servers):
    async with browser_guard.PublicOnlyProxy() as proxy:
        port = int(proxy.url.rsplit(":", 1)[1])
        answers = []
        for target in (f"127.0.0.2:{servers.public}", f"127.0.0.1:{servers.private}"):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
            await writer.drain()
            answers.append((await reader.readuntil(b"\r\n\r\n")).decode().split("\r\n")[0])
            if answers[-1].startswith("HTTP/1.1 200"):
                writer.write(b"GET /tunnelled HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
                await writer.drain()
                answers.append((await reader.read()).decode().split("\r\n")[0])
            writer.close()

    assert answers == [
        "HTTP/1.1 200 Connection Established",
        "HTTP/1.0 200 OK",
        "HTTP/1.1 403 Forbidden",
    ]
    assert _private_hits() == []


async def test_the_proxy_refuses_an_ipv6_loopback_address(servers):
    """As Chromium writes it: the address in brackets."""
    async with browser_guard.PublicOnlyProxy() as proxy:
        port = int(proxy.url.rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET http://[::1]:8080/ HTTP/1.1\r\nHost: [::1]:8080\r\n\r\n")
        await writer.drain()
        status = (await reader.readline()).decode().strip()
        writer.close()

    assert status == "HTTP/1.1 403 Forbidden"


async def test_a_request_that_is_not_an_absolute_http_address_is_refused(servers):
    async with browser_guard.PublicOnlyProxy() as proxy:
        port = int(proxy.url.rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /relative HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        await writer.drain()
        status = (await reader.readline()).decode().strip()
        writer.close()

    assert status == "HTTP/1.1 400 Bad Request"


async def test_the_lookup_and_every_address_share_one_deadline(monkeypatch):
    """Three addresses that never answer take the connect timeout once, not three times."""
    monkeypatch.setattr(browser_guard, "_CONNECT_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(
        url_validator, "_checked_addresses", lambda host: ["192.0.2.1", "192.0.2.2", "192.0.2.3"]
    )

    async def never_answers(host, port):
        await asyncio.sleep(60)

    monkeypatch.setattr(browser_guard.asyncio, "open_connection", never_answers)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await browser_guard._connect_checked("slow.example.com", 443)

    assert time.monotonic() - started < 0.6


async def test_closing_the_proxy_ends_a_handler_that_is_still_connecting(monkeypatch):
    monkeypatch.setattr(url_validator, "_checked_addresses", lambda host: ["192.0.2.1"])

    async def never_answers(host, port):
        await asyncio.sleep(60)

    monkeypatch.setattr(browser_guard.asyncio, "open_connection", never_answers)
    proxy = browser_guard.PublicOnlyProxy()
    await proxy.__aenter__()
    port = int(proxy.url.rsplit(":", 1)[1])
    reader, writer = await _open_connection("127.0.0.1", port)
    writer.write(b"CONNECT slow.example.com:443 HTTP/1.1\r\n\r\n")
    await writer.drain()
    await asyncio.sleep(0.1)

    started = time.monotonic()
    await proxy.__aexit__(None, None, None)

    assert time.monotonic() - started < 1
    assert proxy._handlers == set()
    writer.close()


def test_the_browser_sends_no_webrtc_udp_outside_the_proxy():
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in (
        browser_guard.PROXY_BROWSER_ARGS
    )


class _Crawler:
    """AsyncWebCrawler's shape: the config it was built with."""

    made: list["_Crawler"] = []

    def __init__(self, config=None) -> None:
        self.config = config
        _Crawler.made.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def arun(self, url, config=None):
        # The proxy is up while the browser runs.
        port = int(self.config.proxy_config.server.rsplit(":", 1)[1])
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
        return [
            SimpleNamespace(
                url=url, success=False, html="", markdown="", status_code=None, error_message="x"
            )
        ]


@pytest.mark.parametrize("render", ["render_pages", "web_page_scraper"])
async def test_both_browser_renders_go_through_the_proxy_and_check_certificates(
    monkeypatch, render
):
    _Crawler.made.clear()
    monkeypatch.setattr(helper, "AsyncWebCrawler", _Crawler)
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: [PUBLIC_IP])

    if render == "render_pages":
        await helper.render_pages(["https://example.com/"], budget_seconds=5)
    else:
        await helper.web_page_scraper(["https://example.com/"])

    (crawler,) = _Crawler.made
    assert crawler.config.proxy_config.server.startswith("http://127.0.0.1:")
    assert "--proxy-bypass-list=<-loopback>" in crawler.config.extra_args
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in crawler.config.extra_args
    assert crawler.config.ignore_https_errors is False


async def test_chromium_reaches_no_private_address_through_the_proxy(servers):
    """A page that names a frame, a script, an image, a fetch and a WebRTC server on 127.0.0.1,
    and a redirect there: none of them reaches it. Skipped where no browser is installed."""
    playwright_api = pytest.importorskip("playwright.async_api")
    private = f"http://127.0.0.1:{servers.private}"
    _Hits.redirect_to = f"{private}/secret"
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", 0))
    udp.setblocking(False)
    async with browser_guard.PublicOnlyProxy() as proxy, playwright_api.async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                proxy={"server": proxy.url}, args=browser_guard.PROXY_BROWSER_ARGS
            )
        except Exception as exc:
            pytest.skip(f"Chromium is not available: {type(exc).__name__}")
        page = await browser.new_page()
        await page.goto(f"http://127.0.0.2:{servers.public}/redirect")
        await page.set_content(
            f'<iframe src="{private}/frame"></iframe><script src="{private}/app.js"></script>'
            f'<img src="{private}/img.png"><script>fetch("{private}/data").catch(() => {{}});'
            "const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:127.0.0.1:%d'}]});"
            "pc.createDataChannel('x'); pc.createOffer().then(o => pc.setLocalDescription(o));"
            "</script>" % udp.getsockname()[1]
        )
        await asyncio.sleep(1)
        await browser.close()

    try:
        udp_packets = len(udp.recv(2048))
    except BlockingIOError:
        udp_packets = 0
    udp.close()

    assert _private_hits() == []
    assert udp_packets == 0  # WebRTC sent nothing to the private address
    assert ("127.0.0.2", "/redirect") in _Hits.hits
