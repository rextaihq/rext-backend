from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.api.tool.schema.schema import HreflangRequest
from src.api.tool.tools import generate_canonical_tag, generate_hreflang_tags

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_model_at_all():
    """Both tools are built in code: any model call fails the test."""
    with patch("src.api.tool.tools.load_model", side_effect=AssertionError("no model call")):
        yield


@pytest.mark.asyncio
async def test_the_canonical_tag_is_the_normalized_url():
    result = await generate_canonical_tag(
        "http://Example.COM/Blog/Post/?utm_source=x&id=2&fbclid=y&b=1"
    )
    assert result["normalized_url"] == "https://example.com/Blog/Post?id=2&b=1"
    assert (
        result["canonical_tag"]
        == '<link rel="canonical" href="https://example.com/Blog/Post?id=2&amp;b=1" />'
    )


def test_the_canonical_route_answers_without_a_model():
    res = client.post("/api/v1/tools/canonical-tag-generator", json={"url": "https://example.com/"})
    assert res.status_code == 200
    assert (
        res.json()["data"]["canonical_tag"]
        == '<link rel="canonical" href="https://example.com/" />'
    )


def hreflang(entries, **kw):
    return HreflangRequest(
        language_region_urls=entries,
        default_url=kw.pop("default_url", "https://example.com/"),
        **kw,
    )


@pytest.mark.asyncio
async def test_hreflang_tags_follow_googles_format():
    result = await generate_hreflang_tags(
        hreflang(
            [
                {"url": "https://example.com/en", "language": "en", "region": "us"},
                {"url": "https://example.com/es", "language": "ES", "region": "es"},
                {"url": "https://example.com/en-gb", "language": "EN_gb", "region": ""},
                {"url": "https://example.com/fr", "language": "fr"},
                {"url": "https://example.com/tw", "language": "zh-hant", "region": "tw"},
            ]
        )
    )
    assert result["hreflang_tags"].splitlines() == [
        '<link rel="alternate" hreflang="en-US" href="https://example.com/en" />',
        '<link rel="alternate" hreflang="es-ES" href="https://example.com/es" />',
        '<link rel="alternate" hreflang="en-GB" href="https://example.com/en-gb" />',
        '<link rel="alternate" hreflang="fr" href="https://example.com/fr" />',
        '<link rel="alternate" hreflang="zh-Hant-TW" href="https://example.com/tw" />',
        '<link rel="alternate" hreflang="x-default" href="https://example.com/" />',
    ]
    assert result["warnings"] is None


@pytest.mark.asyncio
async def test_hreflang_for_a_sitemap_and_without_x_default():
    result = await generate_hreflang_tags(
        hreflang(
            [{"url": "https://example.com/de?a=1&b=2", "language": "de", "region": "de"}],
            include_x_default=False,
            output_format="sitemap",
        )
    )
    assert result["hreflang_tags"] == (
        '<xhtml:link rel="alternate" hreflang="de-DE" href="https://example.com/de?a=1&amp;b=2" />'
    )


@pytest.mark.asyncio
async def test_hreflang_warns_and_leaves_out_what_is_not_a_code():
    result = await generate_hreflang_tags(
        hreflang(
            [
                {"url": "https://example.com/en", "language": "English", "region": "us"},
                {"url": "https://example.com/uk", "language": "en", "region": "uk"},
                {"url": "https://example.com/x", "language": "en", "region": "usa"},
                {"url": "https://example.com/gb", "language": "en", "region": "GB"},
            ],
            include_x_default=False,
        )
    )
    assert (
        result["hreflang_tags"]
        == '<link rel="alternate" hreflang="en-GB" href="https://example.com/uk" />'
    )
    warnings = " | ".join(result["warnings"])
    assert "'English' is not a language code" in warnings
    assert "UK is not a region code; GB" in warnings
    assert "'usa' is not a region code" in warnings
    assert "'en-GB' is given twice; the first URL is kept: https://example.com/uk" in warnings


@pytest.mark.asyncio
async def test_an_address_without_a_scheme_gets_https():
    result = await generate_canonical_tag("Example.com/page/")
    assert result["canonical_tag"] == '<link rel="canonical" href="https://example.com/page" />'


def test_an_address_without_a_host_is_refused():
    res = client.post("/api/v1/tools/canonical-tag-generator", json={"url": "https:///page"})
    assert res.status_code == 400
    assert "full address" in res.json()["message"]


@pytest.mark.asyncio
async def test_hreflang_takes_only_the_iso_codes_google_supports():
    result = await generate_hreflang_tags(
        hreflang(
            [
                {"url": "https://example.com/a", "language": "eng", "region": "us"},
                {"url": "https://example.com/b", "language": "xx"},
                {"url": "https://example.com/c", "language": "en", "region": "zz"},
                {"url": "https://example.com/d", "language": "sr", "region": "Latn"},
            ],
            include_x_default=False,
        )
    )
    assert result["hreflang_tags"] == (
        '<link rel="alternate" hreflang="sr-Latn" href="https://example.com/d" />'
    )
    warnings = " | ".join(result["warnings"])
    assert "'eng' is not a language code" in warnings
    assert "'xx' is not a language code" in warnings
    assert "'zz' is not a region code" in warnings


@pytest.mark.parametrize(
    "url",
    [
        "not a url",
        "https://exa mple.com/x",
        "https://exa_mple.com/",
        "https://example.com:abc/",
        "https://example.com:99999/",
    ],
)
def test_a_canonical_address_must_be_a_full_web_address(url):
    res = client.post("/api/v1/tools/canonical-tag-generator", json={"url": url})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_hreflang_leaves_out_what_is_not_a_full_address():
    result = await generate_hreflang_tags(
        hreflang(
            [
                {"url": "not a url", "language": "en", "region": "us"},
                {"url": "https://example.com/es", "language": "es"},
            ],
            default_url="also not a url",
        )
    )
    assert result["hreflang_tags"] == (
        '<link rel="alternate" hreflang="es" href="https://example.com/es" />'
    )
    warnings = " | ".join(result["warnings"])
    assert "'not a url' is not a full address" in warnings
    assert "'also not a url' is not a full address (https://...): no x-default." in warnings


def test_an_address_with_a_valid_port_is_kept():
    res = client.post(
        "/api/v1/tools/canonical-tag-generator", json={"url": "http://localhost:3000/a/"}
    )
    assert (
        res.json()["data"]["canonical_tag"]
        == '<link rel="canonical" href="https://localhost:3000/a" />'
    )
