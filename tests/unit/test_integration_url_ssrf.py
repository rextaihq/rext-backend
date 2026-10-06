"""Integration addresses never lead the API to a private or reserved network."""

import httpx
import pytest

from src.api.middleware.exceptions import RextExternalServiceException, RextValidationException
from src.services.integration_services import IntegrationService
from src.utils.integration_urls import (
    INVALID_ADDRESS_MESSAGE,
    PRIVATE_ADDRESS_MESSAGE,
    UNKNOWN_HOST_MESSAGE,
    ensure_public_site_urls,
)
from src.utils.url_validator import (
    SSRFValidationError,
    refuse_private_addresses,
    validate_url_for_ssrf,
)
from src.web.shopify import ShopifyConnector
from src.web.shopify_bridge import ShopifyAppBridge
from src.web.wordpress import WordPressPublisher

PRIVATE = [
    "http://127.0.0.1:8791/wp-json/rext-ai/v1",
    "http://localhost/",
    "http://10.0.0.5/",
    "http://169.254.169.254/latest/meta-data/",
    "https://[::1]/",
    "http://100.64.0.1/",
]
PUBLIC = "http://93.184.216.34/"


def _client(sent: list[str], handler=None) -> httpx.AsyncClient:
    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        return handler(request) if handler else httpx.Response(200, json={})

    return httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        event_hooks={"request": [refuse_private_addresses()]},
    )


@pytest.mark.parametrize("url", PRIVATE)
async def test_the_hook_refuses_a_private_address_before_sending(url):
    sent: list[str] = []
    async with _client(sent) as client:
        with pytest.raises(SSRFValidationError):
            await client.get(url)

    assert sent == []


async def test_the_hook_lets_a_public_address_through():
    sent: list[str] = []
    async with _client(sent) as client:
        response = await client.get(PUBLIC)

    assert response.status_code == 200
    assert sent == [PUBLIC]


async def test_the_hook_refuses_a_redirect_to_a_private_address():
    sent: list[str] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/"})

    async with _client(sent, redirect) as client:
        with pytest.raises(SSRFValidationError):
            await client.get(PUBLIC, follow_redirects=True)

    assert sent == [PUBLIC]


@pytest.mark.parametrize("url", PRIVATE)
async def test_connect_and_update_refuse_a_private_site_url(url):
    with pytest.raises(RextValidationException) as exc:
        await ensure_public_site_urls(url)

    assert exc.value.message == PRIVATE_ADDRESS_MESSAGE


async def test_connect_and_update_accept_public_and_empty_values():
    await ensure_public_site_urls(PUBLIC, None, "")


async def test_blank_values_are_skipped():
    await ensure_public_site_urls("   ", "\t")


@pytest.mark.parametrize("value", [123, ["http://10.0.0.5/"], {"url": "x"}])
async def test_a_value_that_is_not_a_string_is_a_validation_error(value):
    with pytest.raises(RextValidationException) as exc:
        await ensure_public_site_urls(value)

    assert exc.value.message == INVALID_ADDRESS_MESSAGE


@pytest.mark.parametrize("url", ["example.com", "ftp://example.com", "http:///missing-host"])
async def test_an_address_without_a_usable_scheme_or_host_is_reported_as_invalid(url):
    with pytest.raises(RextValidationException) as exc:
        await ensure_public_site_urls(url)

    assert exc.value.message == INVALID_ADDRESS_MESSAGE


async def test_a_host_that_does_not_resolve_is_reported_as_not_found(monkeypatch):
    monkeypatch.setattr("src.utils.url_validator._resolve_hostname", lambda hostname: [])

    with pytest.raises(RextValidationException) as exc:
        await ensure_public_site_urls("https://no-such-site.example/")

    assert exc.value.message == UNKNOWN_HOST_MESSAGE


async def test_a_malformed_site_url_is_a_validation_error():
    with pytest.raises(RextValidationException) as exc:
        await ensure_public_site_urls("http://[invalid")

    assert exc.value.message == INVALID_ADDRESS_MESSAGE


@pytest.mark.parametrize("url", PRIVATE)
async def test_a_stored_wordpress_connection_at_a_private_address_sends_nothing(url):
    # validate_plugin is the first call of connect; publish, scheduled publish and
    # the status sync use the same client, so the same hook refuses them.
    async with WordPressPublisher(site_url=url, api_key="key") as publisher:
        with pytest.raises(RextExternalServiceException) as exc:
            await publisher.validate_plugin()

    # Refused by the check, not by a failed connection.
    assert "blocked" in exc.value.message


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1/", "http://localhost/", "http://169.254.169.254/"]
)
def test_a_blocked_address_is_reported_as_blocked(url):
    with pytest.raises(SSRFValidationError, match="blocked"):
        validate_url_for_ssrf(url)


async def test_the_shopify_client_refuses_a_private_store_address():
    async with ShopifyConnector(store_url="127.0.0.1:8443", access_token="token") as connector:
        with pytest.raises(RextExternalServiceException):
            await connector.test_connection()


async def test_a_shopify_connection_test_refuses_a_private_store_with_a_validation_error():
    with pytest.raises(RextValidationException) as exc:
        await IntegrationService(db=None).test_shopify_connection("10.0.0.5", "token")

    assert exc.value.message == PRIVATE_ADDRESS_MESSAGE


def _bridge_publish(bridge, config_json):
    return bridge.publish_blog_post(
        store_url="demo-store.myshopify.com",
        title="T",
        body="<p>B</p>",
        published=False,
        tags=None,
        handle=None,
        feature_image_url=None,
        content_id="c1",
        workspace_id="w1",
        config_json=config_json,
    )


async def test_a_private_bridge_publish_override_is_refused_before_sending(monkeypatch):
    sent: list[str] = []

    async def post(self, url, **kwargs):
        sent.append(str(url))
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    bridge = ShopifyAppBridge(shared_secret="secret")

    with pytest.raises(RextValidationException) as exc:
        await _bridge_publish(bridge, {"bridge_publish_url": "http://169.254.169.254/latest"})

    assert exc.value.message == PRIVATE_ADDRESS_MESSAGE
    assert sent == []


async def test_the_operators_bridge_address_is_not_checked(monkeypatch):
    # The configured bridge base URL may be an internal service by design.
    sent: list[str] = []

    async def post(self, url, **kwargs):
        sent.append(str(url))
        return httpx.Response(200, json={"article": {"id": 1}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    bridge = ShopifyAppBridge(shared_secret="secret", base_url="http://rext-shopify-app:3000")

    await _bridge_publish(bridge, {})

    assert sent == ["http://rext-shopify-app:3000/app/api/rext/publish"]


async def test_a_blank_bridge_override_leaves_the_operators_address_unchecked(monkeypatch):
    sent: list[str] = []

    async def post(self, url, **kwargs):
        sent.append(str(url))
        return httpx.Response(200, json={"article": {"id": 1}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    bridge = ShopifyAppBridge(shared_secret="secret", base_url="http://rext-shopify-app:3000")

    await _bridge_publish(bridge, {"bridge_publish_url": "   "})

    assert sent == ["http://rext-shopify-app:3000/app/api/rext/publish"]


async def test_a_private_app_launch_url_is_refused_before_sending(monkeypatch):
    # With no configured bridge base, the publish URL is derived from the
    # connection's stored app launch URL, which the customer can set.
    sent: list[str] = []

    async def post(self, url, **kwargs):
        sent.append(str(url))
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    bridge = ShopifyAppBridge(shared_secret="secret")

    with pytest.raises(RextValidationException) as exc:
        await _bridge_publish(bridge, {"app_launch_url": "http://10.0.0.5/app/blogpost"})

    assert exc.value.message == PRIVATE_ADDRESS_MESSAGE
    assert sent == []


async def test_a_public_app_launch_url_still_publishes(monkeypatch):
    sent: list[str] = []

    async def post(self, url, **kwargs):
        sent.append(str(url))
        return httpx.Response(200, json={"article": {"id": 1}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    bridge = ShopifyAppBridge(shared_secret="secret")

    await _bridge_publish(bridge, {"app_launch_url": "http://93.184.216.34/app/blogpost"})

    assert sent == ["http://93.184.216.34/app/api/rext/publish"]
