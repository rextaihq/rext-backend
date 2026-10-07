"""The WordPress publisher never logs an image address's credentials or signed token (G47).

A customer-given image URL can carry `user:password@` and a signed URL's token in its query. Every
log line and error of the featured-image upload names the image by scheme, host and path only; the
httpx errors, whose own text names the whole requested URL, are redacted too, and no traceback or
chained cause carries them on.
"""

import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api.middleware.exceptions import (
    ExternalServiceTimeoutException,
    RextExternalServiceException,
)
from src.web.wordpress import WordPressPublisher, _loggable_url, _redact_urls

PASSWORD = "s3cretpass"
TOKEN = "SIGNATURE123"
IMAGE = f"https://alice:{PASSWORD}@cdn.example.org/media/i.png?X-Amz-Signature={TOKEN}#frag"
# Parentheses and a quote are legal in a path, and mustn't end the redaction early.
IMAGES = [
    IMAGE,
    f"https://alice:{PASSWORD}@cdn.example.org/media/i(v1).png?X-Amz-Signature={TOKEN}",
    f"https://alice:{PASSWORD}@cdn.example.org/media/i'v1.png?X-Amz-Signature={TOKEN}",
]


def _publisher() -> WordPressPublisher:
    return WordPressPublisher(site_url="https://example.com", username="user", app_password="pass")


def _leaks(text: str) -> bool:
    return PASSWORD in text or TOKEN in text or "alice" in text


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr("src.web.wordpress.asyncio.sleep", AsyncMock())


@pytest.mark.parametrize(
    ("address", "shown"),
    [
        (IMAGE, "https://cdn.example.org/media/i.png"),
        ("http://cdn.example.org:8080/a.png?x=1", "http://cdn.example.org:8080/a.png"),
        ("data:image/png;base64,iVBORw0KGgo=", "data:..."),
        ("not a url", "(an address without a scheme)"),
        ("http://[::1/", "(an unreadable address)"),
    ],
)
def test_an_address_shows_its_scheme_host_and_path_only(address, shown):
    assert _loggable_url(address) == shown


def test_addresses_inside_a_message_are_redacted():
    message = f"Client error '403 Forbidden' for url '{IMAGE}'"
    redacted = _redact_urls(message)
    assert "https://cdn.example.org/media/i.png" in redacted
    assert not _leaks(redacted)


def test_a_path_with_parentheses_is_redacted_whole():
    address = IMAGES[1]
    # Found by the pattern alone, and replaced whole when the message names a known address.
    assert not _leaks(_redact_urls(f"HTTP 403 for {address}"))
    assert not _leaks(_redact_urls(f"ConnectError('cannot connect to {address}')", address))


def test_a_known_address_with_a_quote_is_redacted_whole():
    address = IMAGES[2]
    assert not _leaks(_redact_urls(f"HTTP 403 for {address} (refused)", address))


@pytest.mark.parametrize("image", IMAGES)
async def test_a_download_that_fails_logs_and_raises_no_credentials(monkeypatch, caplog, image):
    request = httpx.Request("GET", image)
    download = AsyncMock(
        side_effect=httpx.ConnectError(f"cannot connect to {image}", request=request)
    )
    monkeypatch.setattr(httpx.AsyncClient, "get", download)

    with caplog.at_level(logging.DEBUG, logger="src.web.wordpress"):
        with pytest.raises(RextExternalServiceException) as raised:
            await _publisher()._upload_featured_image(image)

    assert download.await_count == 3
    assert "cdn.example.org/media/i" in str(raised.value)
    assert not _leaks(str(raised.value))
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    assert not _leaks(caplog.text)


@pytest.mark.parametrize("image", IMAGES)
async def test_a_refused_status_logs_and_raises_no_credentials(monkeypatch, caplog, image):
    response = httpx.Response(403, text="denied", request=httpx.Request("GET", image))
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=response))

    with caplog.at_level(logging.DEBUG, logger="src.web.wordpress"):
        with pytest.raises(RextExternalServiceException) as raised:
            await _publisher()._upload_featured_image(image)

    assert "403" in str(raised.value)
    assert not _leaks(str(raised.value))
    assert not _leaks(caplog.text)


@pytest.mark.parametrize("image", IMAGES)
async def test_a_timeout_logs_and_raises_no_credentials(monkeypatch, caplog, image):
    request = httpx.Request("GET", image)
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(side_effect=httpx.ReadTimeout(f"timed out reading {image}", request=request)),
    )

    with caplog.at_level(logging.DEBUG, logger="src.web.wordpress"):
        with pytest.raises(ExternalServiceTimeoutException) as raised:
            await _publisher()._upload_featured_image(image)

    assert raised.value.__cause__ is None
    assert not _leaks(caplog.text)


@pytest.mark.parametrize("image", IMAGES)
async def test_a_downloaded_file_that_isnt_an_image_logs_no_credentials(monkeypatch, caplog, image):
    # The download succeeds (its final address is logged), then the bytes aren't an image.
    response = httpx.Response(
        200,
        content=b"<html>not an image</html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", image),
    )
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=response))

    with caplog.at_level(logging.DEBUG, logger="src.web.wordpress"):
        with pytest.raises(RextExternalServiceException):
            await _publisher()._upload_featured_image(image)

    assert "cdn.example.org/media/i" in caplog.text
    assert not _leaks(caplog.text)
