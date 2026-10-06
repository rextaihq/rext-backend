import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.api.tool.tools import broken_link_checker
from src.utils import url_validator


class _Sent(list):
    """The URLs of the requests that reached the network; `answers` maps a URL to a reply."""

    def __init__(self):
        super().__init__()
        self.answers = {}


@pytest.fixture
def sent(monkeypatch):
    requests = _Sent()

    async def handle(self, request):
        requests.append(str(request.url))
        status, headers = requests.answers.get(str(request.url), (200, {}))
        return httpx.Response(status, headers=headers, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    return requests


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:2024/ok",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5:8080/",
        "http://[::1]/",
    ],
)
async def test_a_private_address_is_never_fetched(sent, url):
    assert await broken_link_checker(url) is False
    assert sent == []


async def test_a_name_that_resolves_to_a_private_address_is_never_fetched(sent, monkeypatch):
    monkeypatch.setattr(url_validator, "_resolve_hostname", lambda host: ["10.1.2.3"])
    assert await broken_link_checker("https://internal.example.com/") is False
    assert sent == []


async def test_a_redirect_to_a_private_address_is_not_followed(sent):
    sent.answers["http://8.8.8.8/"] = (302, {"location": "http://127.0.0.1/admin"})
    assert await broken_link_checker("http://8.8.8.8/") is False
    assert sent == ["http://8.8.8.8/"]


async def test_a_public_address_is_checked(sent):
    assert await broken_link_checker("http://8.8.8.8/") is True
    sent.answers["http://8.8.4.4/"] = (404, {})
    assert await broken_link_checker("http://8.8.4.4/") is False
    assert sent == ["http://8.8.8.8/", "http://8.8.4.4/"]


def test_the_route_reports_a_private_address_as_not_working(sent):
    response = TestClient(app).post(
        "/api/v1/tools/link-checker", json={"url": "http://127.0.0.1:2024/ok"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["working"] is False
    assert sent == []
