"""The fetches of customer-given addresses never reach a private or reserved network:
the image download, the site's security-header check and the site scan refuse a
redirect there before sending, and a connection goes only to the address that was
checked, so a name that answers differently the second time (DNS rebinding) is refused."""

import logging
import threading
import time
from unittest.mock import AsyncMock

import httpcore
import httpx
import pytest

from src.api.middleware.exceptions import RextExternalServiceException
from src.utils import url_validator
from src.utils.site_compliance import get_security_headers
from src.utils.site_security_scan import analyze_site_security
from src.utils.url_validator import SSRFValidationError, _PublicOnlyNetworkBackend
from src.web.wordpress import WordPressPublisher

PUBLIC = "http://93.184.216.34"
PRIVATE_REDIRECTS = [
    "http://127.0.0.1:8000/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
]


class _Sent(list):
    """The URLs a mock transport was asked to send, and where it redirects the public host."""

    def __init__(self) -> None:
        super().__init__()
        self.target: dict[str, str] = {}


@pytest.fixture
def sent(monkeypatch) -> _Sent:
    """Every public client gets a mock transport that redirects the public host to the
    test's `redirect_to`, and records what it was asked to send."""
    requests = _Sent()

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if "redirect_to" in requests.target and request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": requests.target["redirect_to"]})
        return httpx.Response(
            200, content=b"\x89PNG\r\n\x1a\n", headers={"content-type": "image/png"}
        )

    monkeypatch.setattr(
        url_validator, "PublicOnlyTransport", lambda verify=True: httpx.MockTransport(respond)
    )
    return requests


@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_an_image_url_that_redirects_to_a_private_address_is_refused(sent, private):
    sent.target["redirect_to"] = private
    async with WordPressPublisher(site_url=PUBLIC, api_key="key") as wp:
        with pytest.raises(SSRFValidationError):
            await wp._download_image(f"{PUBLIC}/image.png")

    assert sent == [f"{PUBLIC}/image.png"]


async def test_a_public_image_still_downloads(sent):
    async with WordPressPublisher(site_url=PUBLIC, api_key="key") as wp:
        response = await wp._download_image(f"{PUBLIC}/image.png")

    assert response.status_code == 200
    assert sent == [f"{PUBLIC}/image.png"]


async def test_a_refused_image_logs_its_host_not_its_credentials(sent, caplog):
    sent.target["redirect_to"] = PRIVATE_REDIRECTS[0]

    with caplog.at_level(logging.WARNING, logger="src.web.wordpress"):
        async with WordPressPublisher(site_url=PUBLIC, api_key="key") as wp:
            with pytest.raises(RextExternalServiceException):
                await wp._upload_featured_image("http://user:s3cret@93.184.216.34/image.png")

    (refused,) = [r.getMessage() for r in caplog.records if "refused host" in r.getMessage()]
    assert "93.184.216.34" in refused
    assert "s3cret" not in refused and "user" not in refused


@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_the_header_check_reports_a_private_redirect_without_following_it(sent, private):
    sent.target["redirect_to"] = private

    result = await get_security_headers(f"{PUBLIC}/")

    assert result["checked"] is False
    assert sent == [f"{PUBLIC}/"]


@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_the_site_scan_reports_a_private_redirect_without_following_it(sent, private):
    sent.target["redirect_to"] = private

    result = await analyze_site_security(f"{PUBLIC}/")

    assert result["checked"] is False
    assert result["error"]
    assert sent == [f"{PUBLIC}/"]


class _Recorder:
    """Stands in for the real network backend: records where it was asked to connect,
    and fails to connect to the addresses in `unreachable`."""

    def __init__(self, unreachable: tuple[str, ...] = (), silent: tuple[str, ...] = ()) -> None:
        self.connected: list[tuple[str, int]] = []
        self.timeouts: list[float | None] = []
        self.unreachable = unreachable
        self.silent = silent

    async def connect_tcp(self, host, port, timeout=None, **_):
        self.connected.append((host, port))
        self.timeouts.append(timeout)
        if host in self.unreachable:
            raise httpcore.ConnectError(f"{host} unreachable")
        if host in self.silent:  # never answers: the attempt runs out its time
            raise httpcore.ConnectTimeout(f"{host} did not answer")
        return object()


def _backend(
    monkeypatch,
    *answers: list[str],
    unreachable: tuple[str, ...] = (),
    silent: tuple[str, ...] = (),
) -> tuple[_PublicOnlyNetworkBackend, _Recorder]:
    """A checking backend whose name lookups answer `answers`, one per lookup."""
    queue = list(answers)
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: queue.pop(0))
    backend = _PublicOnlyNetworkBackend()
    recorder = _Recorder(unreachable, silent)
    backend._backend = recorder
    return backend, recorder


async def test_the_connection_goes_to_the_checked_address_not_the_name(monkeypatch):
    backend, recorder = _backend(monkeypatch, ["93.184.216.34"])

    await backend.connect_tcp("images.example.com", 443)

    assert recorder.connected == [("93.184.216.34", 443)]


async def test_a_name_that_rebinds_to_a_private_address_is_refused_at_the_connection(monkeypatch):
    # The request hook's lookup sees a public address; the connection's sees a private one.
    backend, recorder = _backend(monkeypatch, ["93.184.216.34"], ["127.0.0.1"])
    url_validator.validate_url_for_ssrf("http://rebind.example/")

    with pytest.raises(SSRFValidationError):
        await backend.connect_tcp("rebind.example", 80)

    assert recorder.connected == []


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "::1", "10.1.2.3"])
async def test_a_private_address_is_never_connected_to(monkeypatch, host):
    backend, recorder = _backend(monkeypatch)

    with pytest.raises(SSRFValidationError):
        await backend.connect_tcp(host, 80)

    assert recorder.connected == []


async def test_a_name_with_one_private_address_among_public_ones_is_refused(monkeypatch):
    backend, recorder = _backend(monkeypatch, ["93.184.216.34", "10.0.0.7"])

    with pytest.raises(SSRFValidationError):
        await backend.connect_tcp("mixed.example", 80)

    assert recorder.connected == []


async def test_an_unreachable_address_falls_through_to_the_next_checked_one(monkeypatch):
    # An IPv6 answer that cannot be reached (an IPv4-only network) does not sink the request.
    backend, recorder = _backend(
        monkeypatch,
        ["2606:2800:220:1::248", "93.184.216.34"],
        unreachable=("2606:2800:220:1::248",),
    )

    await backend.connect_tcp("images.example.com", 443, timeout=5)

    assert recorder.connected == [("2606:2800:220:1::248", 443), ("93.184.216.34", 443)]


async def test_an_address_that_never_answers_leaves_time_for_the_next(monkeypatch):
    backend, recorder = _backend(
        monkeypatch,
        ["2606:2800:220:1::248", "93.184.216.34"],
        silent=("2606:2800:220:1::248",),
    )

    await backend.connect_tcp("images.example.com", 443, timeout=10)

    assert recorder.connected == [("2606:2800:220:1::248", 443), ("93.184.216.34", 443)]
    # The first attempt gets its share (about half), the last what is left.
    assert recorder.timeouts[0] < 5.01
    assert recorder.timeouts[1] > 9


async def test_every_address_unreachable_is_a_connection_error(monkeypatch):
    backend, _ = _backend(monkeypatch, ["93.184.216.34"], unreachable=("93.184.216.34",))

    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("images.example.com", 443)


async def test_a_slow_lookup_counts_against_the_connect_timeout(monkeypatch):
    def slow(host):
        time.sleep(0.5)
        return ["93.184.216.34"]

    monkeypatch.setattr(url_validator, "_resolve_hostname", slow)
    backend = _PublicOnlyNetworkBackend()
    backend._backend = _Recorder()

    with pytest.raises(httpcore.ConnectTimeout):
        await backend.connect_tcp("slow.example", 80, timeout=0.05)

    assert backend._backend.connected == []


async def test_a_name_that_does_not_resolve_is_a_connection_error_not_a_refusal(monkeypatch):
    backend, recorder = _backend(monkeypatch, [])

    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("no-such-host.example", 80)

    assert recorder.connected == []


async def test_the_hooks_lookup_counts_against_the_connect_timeout(monkeypatch):
    def slow(host):
        time.sleep(0.5)
        return ["93.184.216.34"]

    monkeypatch.setattr(url_validator, "_resolve_hostname", slow)
    hook = url_validator.refuse_private_addresses()
    request = httpx.Request(
        "GET", "http://slow.example/", extensions={"timeout": {"connect": 0.05}}
    )

    with pytest.raises(httpx.ConnectTimeout):
        await hook(request)


def _slow(answer: list[str], seconds: float = 0.3):
    def lookup(host):
        time.sleep(seconds)
        return answer

    return lookup


def _timed_request(spent: float | None = None) -> httpx.Request:
    extensions = {"timeout": {"connect": 2.0, "read": 5.0}}
    if spent is not None:
        extensions["public_lookup_seconds"] = spent
    return httpx.Request("GET", "http://slow.example/", extensions=extensions)


@pytest.mark.parametrize("answer", [["93.184.216.34"], []])
async def test_the_hook_records_how_long_its_lookup_took(monkeypatch, answer):
    # A name that resolves, and one that does not (a slow negative answer counts too).
    monkeypatch.setattr(url_validator, "_resolve_hostname", _slow(answer))
    request = _timed_request()

    await url_validator.refuse_private_addresses()(request)

    assert request.extensions["public_lookup_seconds"] >= 0.3
    assert request.extensions["timeout"] == {"connect": 2.0, "read": 5.0}


async def test_a_host_already_checked_records_no_lookup_time(monkeypatch):
    # A redirect copies the extensions: the stale time must not carry over.
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: ["93.184.216.34"])
    hook = url_validator.refuse_private_addresses()
    await hook(_timed_request())
    request = _timed_request(spent=1.5)

    await hook(request)

    assert request.extensions["public_lookup_seconds"] == 0.0


async def test_the_connection_gets_what_the_lookup_left_for_this_attempt_only(monkeypatch):
    seen = []

    async def send(self, request):
        seen.append(request.extensions["timeout"]["connect"])
        return httpx.Response(200)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", send)
    request = _timed_request(spent=0.5)

    await url_validator.PublicOnlyTransport().handle_async_request(request)

    assert seen == [1.5]
    # Put back: a redirect built from this request starts from the full timeout.
    assert request.extensions["timeout"] == {"connect": 2.0, "read": 5.0}


async def test_a_lookup_that_used_up_the_timeout_is_a_connect_timeout(monkeypatch):
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", AsyncMock(side_effect=AssertionError)
    )

    with pytest.raises(httpx.ConnectTimeout):
        await url_validator.PublicOnlyTransport().handle_async_request(_timed_request(spent=2.5))


async def test_lookups_run_on_threads_of_their_own(monkeypatch):
    # A stalled lookup holds one of these threads, never the event loop's shared executor.
    threads = []

    def record(host):
        threads.append(threading.current_thread().name)
        return ["93.184.216.34"]

    monkeypatch.setattr(url_validator, "_resolve_hostname", record)
    backend = _PublicOnlyNetworkBackend()
    backend._backend = _Recorder()

    await url_validator.refuse_private_addresses()(httpx.Request("GET", "http://a.example/"))
    await backend.connect_tcp("b.example", 80)
    await url_validator.ensure_public_urls("http://c.example/")

    assert len(threads) == 3
    assert all(name.startswith("public-dns") for name in threads)


async def test_the_hook_leaves_an_unresolvable_name_to_the_connection(monkeypatch):
    # Refusing it would turn a passing DNS failure into a security error and skip
    # the image download's retries; the connection reports it as a network error.
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: [])
    hook = url_validator.refuse_private_addresses()

    await hook(httpx.Request("GET", "http://no-such-host.example/image.png"))


async def test_a_local_socket_is_refused():
    with pytest.raises(SSRFValidationError):
        await _PublicOnlyNetworkBackend().connect_unix_socket("/var/run/docker.sock")


def test_the_public_client_uses_the_checking_transport():
    client = url_validator.public_client(verify=False)

    pool = client._transport._pool
    assert isinstance(client._transport, url_validator.PublicOnlyTransport)
    assert isinstance(pool._network_backend, _PublicOnlyNetworkBackend)
    # httpx's client defaults, not httpx.Limits()'s unbounded ones.
    assert (pool._max_connections, pool._max_keepalive_connections) == (100, 20)
