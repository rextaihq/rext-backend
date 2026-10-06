"""The fetches of customer-given addresses never reach a private or reserved network:
the image download, the site's security-header check and the site scan refuse a
redirect there before sending, and a connection goes only to the address that was
checked, so a name that answers differently the second time (DNS rebinding) is refused."""

import httpx
import pytest

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
    async with WordPressPublisher(site_url=PUBLIC, api_key="key", env_fallback=False) as wp:
        with pytest.raises(SSRFValidationError):
            await wp._download_image(f"{PUBLIC}/image.png")

    assert sent == [f"{PUBLIC}/image.png"]


async def test_a_public_image_still_downloads(sent):
    async with WordPressPublisher(site_url=PUBLIC, api_key="key", env_fallback=False) as wp:
        response = await wp._download_image(f"{PUBLIC}/image.png")

    assert response.status_code == 200
    assert sent == [f"{PUBLIC}/image.png"]


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
    """Stands in for the real network backend: records where it was asked to connect."""

    def __init__(self) -> None:
        self.connected: list[tuple[str, int]] = []

    async def connect_tcp(self, host, port, **_):
        self.connected.append((host, port))
        return object()


def _backend(monkeypatch, *answers: list[str]) -> tuple[_PublicOnlyNetworkBackend, _Recorder]:
    """A checking backend whose name lookups answer `answers`, one per lookup."""
    queue = list(answers)
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: queue.pop(0))
    backend = _PublicOnlyNetworkBackend()
    recorder = _Recorder()
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


async def test_a_local_socket_is_refused():
    with pytest.raises(SSRFValidationError):
        await _PublicOnlyNetworkBackend().connect_unix_socket("/var/run/docker.sock")


def test_the_public_client_uses_the_checking_transport():
    client = url_validator.public_client(verify=False)

    assert isinstance(client._transport, url_validator.PublicOnlyTransport)
    assert isinstance(client._transport._pool._network_backend, _PublicOnlyNetworkBackend)
