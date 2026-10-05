"""Tests for finding, fetching and keeping a workspace site's favicon."""

import io

import httpx
import pytest
from PIL import Image

from src.services import workspace_favicon
from src.services.workspace_favicon import (
    MAX_FAVICON_BYTES,
    favicon_candidates,
    fetch_favicon,
    find_favicon,
    store_favicon,
)
from src.utils.url_validator import SSRFValidationError

PAGE = "https://shop.example.com/en/home"


def _image(fmt: str = "PNG", size: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (20, 40, 60)).save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """Example hosts pass without DNS; any 127.0.0.1 or 169.254 address is refused, as the real check does."""

    def _check(url: str) -> str:
        if "127.0.0.1" in url or "169.254." in url:
            raise SSRFValidationError("private address")
        return url

    monkeypatch.setattr(workspace_favicon, "validate_url_for_ssrf", _check)


def _transport(routes: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        reply = routes.get(str(request.url))
        if reply is None:
            return httpx.Response(404)
        if isinstance(reply, str):
            return httpx.Response(302, headers={"location": reply})
        return httpx.Response(200, content=reply)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# favicon_candidates
# ---------------------------------------------------------------------------


def test_declared_icons_come_first_best_size_first_then_favicon_ico():
    html = """
      <link rel="icon" href="/tiny.png" sizes="16x16">
      <link rel="apple-touch-icon" href="/apple.png">
      <link rel="icon" type="image/png" href="icons/icon-64.png" sizes="64x64">
      <link rel="stylesheet" href="/site.css">
    """

    assert favicon_candidates(html, PAGE) == [
        "https://shop.example.com/apple.png",
        "https://shop.example.com/en/icons/icon-64.png",
        "https://shop.example.com/tiny.png",
        "https://shop.example.com/favicon.ico",
    ]


def test_svg_and_data_icons_are_skipped():
    html = """
      <link rel="icon" type="image/svg+xml" href="/logo.svg">
      <link rel="icon" href="/mark.svg?v=2">
      <link rel="icon" href="data:image/png;base64,AAAA">
      <link rel="shortcut icon" href="https://cdn.example.net/fav.ico">
    """

    assert favicon_candidates(html, PAGE) == [
        "https://cdn.example.net/fav.ico",
        "https://shop.example.com/favicon.ico",
    ]


def test_without_html_only_the_conventional_address_is_tried():
    assert favicon_candidates(None, PAGE) == ["https://shop.example.com/favicon.ico"]


# ---------------------------------------------------------------------------
# fetch_favicon
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["PNG", "ICO", "GIF", "WEBP", "JPEG"])
@pytest.mark.asyncio
async def test_a_raster_icon_is_kept_with_its_type(fmt):
    url = "https://shop.example.com/favicon.ico"
    data = _image(fmt)

    found = await fetch_favicon(url, transport=_transport({url: data}))

    assert found is not None
    assert found[0] == data
    assert found[1] in workspace_favicon.FAVICON_TYPES


@pytest.mark.parametrize(
    "body",
    [
        b"<html><body>Not found</body></html>",
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,  # a PNG signature over a broken body
    ],
)
@pytest.mark.asyncio
async def test_anything_but_a_readable_raster_image_is_dropped(body):
    url = "https://shop.example.com/favicon.ico"

    assert await fetch_favicon(url, transport=_transport({url: body})) is None


@pytest.mark.asyncio
async def test_an_oversized_body_is_dropped():
    url = "https://shop.example.com/favicon.ico"
    body = _image("PNG") + b"\x00" * (MAX_FAVICON_BYTES + 1)

    assert await fetch_favicon(url, transport=_transport({url: body})) is None


@pytest.mark.asyncio
async def test_redirects_are_followed_and_each_hop_is_checked():
    first, final = "https://shop.example.com/favicon.ico", "https://cdn.example.net/f.png"
    data = _image("PNG")

    found = await fetch_favicon(first, transport=_transport({first: final, final: data}))
    assert found is not None and found[0] == data

    with pytest.raises(SSRFValidationError):
        await fetch_favicon(
            first, transport=_transport({first: "http://169.254.169.254/latest/meta-data"})
        )


@pytest.mark.asyncio
async def test_a_redirect_loop_gives_up():
    a, b = "https://shop.example.com/a.ico", "https://shop.example.com/b.ico"

    assert await fetch_favicon(a, transport=_transport({a: b, b: a})) is None


# ---------------------------------------------------------------------------
# find_favicon and store_favicon
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_first_usable_candidate_wins_and_refusals_are_skipped():
    html = """
      <link rel="icon" href="http://127.0.0.1/internal.png" sizes="64x64">
      <link rel="icon" href="/broken.png" sizes="48x48">
    """
    data = _image("ICO")
    transport = _transport(
        {
            "https://shop.example.com/broken.png": b"<html>oops</html>",
            "https://shop.example.com/favicon.ico": data,
        }
    )

    found = await find_favicon(html, PAGE, transport=transport)

    assert found == {
        "data": data,
        "mime": "image/x-icon",
        "source_url": "https://shop.example.com/favicon.ico",
    }


@pytest.mark.asyncio
async def test_no_usable_icon_is_none_not_an_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    assert await find_favicon(None, PAGE, transport=httpx.MockTransport(handler)) is None


@pytest.mark.asyncio
async def test_the_icon_is_stored_under_the_workspace(monkeypatch):
    calls = []

    class _Storage:
        def upload_file(self, *, file_data, object_name, content_type):
            calls.append((object_name, content_type, len(file_data)))
            return "https://media.example.com/" + object_name

    monkeypatch.setattr("src.utils.storage.storage_service", _Storage())

    object_name = await store_favicon("ws-1", b"\x00\x00\x01\x00", "image/x-icon")

    assert object_name.startswith("workspaces/ws-1/favicon_")
    assert object_name.endswith(".ico")
    assert calls == [(object_name, "image/x-icon", 4)]


@pytest.mark.asyncio
async def test_a_failed_upload_stores_nothing(monkeypatch):
    class _Storage:
        def upload_file(self, **kwargs):
            return None

    monkeypatch.setattr("src.utils.storage.storage_service", _Storage())

    assert await store_favicon("ws-1", b"x", "image/png") is None
