"""A customer's WordPress connection never sends the server's WORDPRESS_* settings.

A publisher is built from a stored connection; an empty stored value must stay
empty, or the server's own site, endpoint or key would be sent to the
customer's site.
"""

import base64

import httpx
import pytest

from src.utils import url_validator
from src.web.wordpress import WordPressPublisher

# The customer's site: a public address written as an IP, so no lookup is needed.
SITE = "http://93.184.216.34"

SERVER_SETTINGS = {
    "WORDPRESS_SITE_URL": "https://wp.server.example",
    "WORDPRESS_API_ENDPOINT": "https://wp.server.example/wp-json/rext-ai/v1",
    "WORDPRESS_USERNAME": "server-user",
    "WORDPRESS_APP_PASSWORD": "server-password",
    "WORDPRESS_API_KEY": "server-key",
}


@pytest.fixture
def server_settings(monkeypatch) -> None:
    for name, value in SERVER_SETTINGS.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def sent(monkeypatch, server_settings) -> list[httpx.Request]:
    """Record what the publisher's client sends, with every server setting set."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401, json={"code": "rest_not_logged_in"})

    # The publisher builds every client through public_client(), whose transport is
    # the seam: the request hook still runs, and nothing leaves the test.
    monkeypatch.setattr(
        url_validator, "PublicOnlyTransport", lambda verify=True: httpx.MockTransport(respond)
    )
    return requests


def _basic(username: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


@pytest.mark.asyncio
async def test_a_connection_without_credentials_sends_none(sent):
    async with WordPressPublisher(
        site_url=SITE, api_endpoint=None, username=None, app_password=None, api_key=None
    ) as publisher:
        await publisher.check_connection()

    (request,) = sent
    assert str(request.url) == f"{SITE}/wp-json/wp/v2/users/me"
    assert "authorization" not in request.headers


@pytest.mark.asyncio
async def test_an_application_password_connection_sends_its_own_password(sent):
    async with WordPressPublisher(
        site_url=SITE, username="editor", app_password="abcd efgh", api_key=""
    ) as publisher:
        await publisher.check_connection()

    (request,) = sent
    assert request.headers["authorization"] == _basic("editor", "abcdefgh")


@pytest.mark.asyncio
async def test_a_key_connection_uses_its_own_site_not_the_servers_endpoint(sent):
    async with WordPressPublisher(
        site_url=SITE, api_endpoint="", api_key="customer-key"
    ) as publisher:
        await publisher.check_connection()

    (request,) = sent
    assert str(request.url) == f"{SITE}/wp-json/rext-ai/v1/verify"
    assert request.headers["authorization"] == "Bearer customer-key"


def test_empty_values_stay_empty(server_settings):
    publisher = WordPressPublisher(site_url="", api_endpoint=None, username=None)

    assert (publisher.site_url, publisher.api_endpoint, publisher.username) == ("", "", "")
    assert (publisher.app_password, publisher.api_key) == ("", "")
