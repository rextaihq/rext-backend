"""The ranking pages' headings reach the outline gate's Sources view (rext-control#476).

The node reads the top five ranking pages once per run, side by side, through the same SSRF
check as the site scraper, and keeps their H2 and H3 text in order. A page that times out,
answers an error, isn't HTML or redirects to a refused address is left out, and nothing here
fails the run. The pages are served by httpx's MockTransport; no network is used.
"""

import httpx
import pytest

import src.flow.engines.content.generation.competitor_headings as headings_module
import src.flow.engines.content.review.outline as review_module
from src.flow.engines.content.content_engine import create_content_engine
from src.flow.engines.content.generation.competitor_headings import (
    MAX_PAGES,
    extract_headings,
    fetch_competitor_headings,
    read_competitor_headings,
)
from src.utils.url_validator import SSRFValidationError

# A ranking article as such pages come: navigation, a script, an H1, the sections, a footer.
ARTICLE = """<!doctype html><html><head><title>Content calendar guide</title>
<script>var h2 = "<h2>not a heading</h2>";</script></head>
<body><nav><h2>Menu</h2></nav>
<h1>The content calendar guide</h1>
<h2>What is a content calendar?</h2>
<p>…</p>
<h3>Why   teams use one</h3>
<h2>How to build one in five steps</h2>
<h3>Step 1: audit what you have</h3>
<h3>Step 2: pick your channels</h3>
<h2>What is a content calendar?</h2>
<h2>   </h2>
<footer><h2>Subscribe</h2></footer>
</body></html>"""

OTHER = "<html><body><h2>Free templates</h2><h3>Spreadsheet</h3></body></html>"


def test_a_page_gives_its_h2_and_h3_in_order_without_navigation_scripts_or_repeats():
    assert extract_headings(ARTICLE) == [
        {"level": 2, "text": "What is a content calendar?"},
        {"level": 3, "text": "Why teams use one"},
        {"level": 2, "text": "How to build one in five steps"},
        {"level": 3, "text": "Step 1: audit what you have"},
        {"level": 3, "text": "Step 2: pick your channels"},
    ]


@pytest.fixture
def ssrf(monkeypatch):
    """The SSRF check, refusing the internal address only (no DNS in tests)."""
    checked = []

    def check(url):
        checked.append(url)
        if "169.254" in url:
            raise SSRFValidationError("private address")

    monkeypatch.setattr(headings_module, "validate_url_for_ssrf", check)
    return checked


def _serve(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        answer = routes.get(str(request.url))
        if answer is None:
            return httpx.Response(404)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.MockTransport(handler)


def _html(body):
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=body)


async def test_the_top_five_pages_are_read_and_the_unreadable_ones_left_out(ssrf):
    results = [
        {"position": 1, "url": "https://a.example/guide", "title": "A guide"},
        {"position": 2, "url": "https://b.example/missing", "title": "Gone"},
        {"position": 3, "url": "https://c.example/pdf", "title": "A PDF"},
        {"position": 4, "url": "https://d.example/slow", "title": "Slow"},
        {"position": 5, "url": "https://e.example/old", "title": "Moved"},
        {"position": 6, "url": "https://f.example/sixth", "title": "Sixth"},
    ]
    routes = {
        "https://a.example/guide": _html(ARTICLE),
        "https://c.example/pdf": httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF"
        ),
        "https://d.example/slow": httpx.ReadTimeout("slow"),
        # A redirect to an internal address is refused at its own check.
        "https://e.example/old": httpx.Response(
            301, headers={"location": "http://169.254.169.254/latest"}
        ),
        "https://f.example/sixth": _html(OTHER),
    }

    pages = await fetch_competitor_headings(results, transport=_serve(routes))

    assert [page["url"] for page in pages] == ["https://a.example/guide"]
    assert pages[0]["title"] == "A guide"
    assert pages[0]["headings"][0] == {"level": 2, "text": "What is a content calendar?"}
    # Only the top five were asked for, and the redirect's target was checked too.
    assert MAX_PAGES == 5
    assert "https://f.example/sixth" not in ssrf
    assert "http://169.254.169.254/latest" in ssrf


async def test_a_redirect_is_followed_and_the_ranking_order_kept(ssrf):
    results = [
        {"position": 2, "url": "https://b.example/templates", "title": "Templates"},
        {"position": 1, "url": "https://a.example/old", "title": "Guide"},
    ]
    routes = {
        "https://a.example/old": httpx.Response(301, headers={"location": "/new"}),
        "https://a.example/new": _html(ARTICLE),
        "https://b.example/templates": _html(OTHER),
    }

    pages = await fetch_competitor_headings(results, transport=_serve(routes))

    assert [page["title"] for page in pages] == ["Guide", "Templates"]


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("OUTLINE_COMPETITOR_HEADINGS", "true")


async def test_off_by_default_the_run_reads_no_pages(monkeypatch):
    monkeypatch.delenv("OUTLINE_COMPETITOR_HEADINGS", raising=False)
    calls = []

    async def fetch(results, **kwargs):
        calls.append(results)
        return []

    monkeypatch.setattr(headings_module, "fetch_competitor_headings", fetch)
    state = {"serp_normalized": {"normalize_results": [{"url": "https://a.example"}]}}

    assert await read_competitor_headings(state) == {"content": {"competitor_headings": []}}
    assert calls == []


async def test_the_node_reads_the_pages_once_per_run(monkeypatch, enabled):
    calls = []

    async def fetch(results, **kwargs):
        calls.append(results)
        return [{"url": "https://a.example", "title": "A", "headings": []}]

    monkeypatch.setattr(headings_module, "fetch_competitor_headings", fetch)
    state = {"serp_normalized": {"normalize_results": [{"url": "https://a.example"}]}}

    update = await read_competitor_headings(state)
    assert update == {
        "content": {
            "competitor_headings": [{"url": "https://a.example", "title": "A", "headings": []}]
        }
    }
    # Already read on this run (a resumed run): not again.
    assert await read_competitor_headings({**state, "content": update["content"]}) == {}
    assert len(calls) == 1


async def test_a_failure_leaves_the_sources_without_headings_and_the_run_going(
    monkeypatch, enabled
):
    async def fetch(results, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(headings_module, "fetch_competitor_headings", fetch)

    update = await read_competitor_headings({"serp_normalized": {"normalize_results": []}})

    assert update == {"content": {"competitor_headings": []}}


def test_the_outline_gate_sends_the_headings_for_sources(monkeypatch):
    payloads = []
    monkeypatch.setattr(
        review_module, "interrupt", lambda payload: payloads.append(payload) or "approve"
    )
    page = {"url": "https://a.example", "title": "A", "headings": [{"level": 2, "text": "Why"}]}

    review_module.review_outline(
        {"content": {"outline": {}, "content_type": "blog", "competitor_headings": [page]}}
    )
    review_module.review_outline({"content": {"outline": {}, "content_type": "blog"}})

    assert payloads[0]["competitor_headings"] == [page]
    # An older run's state has none: an empty list, never a missing field.
    assert payloads[1]["competitor_headings"] == []


def test_the_headings_are_read_after_the_keyword_groups_and_before_the_outline():
    edges = {(e.source, e.target) for e in create_content_engine().get_graph().edges}

    assert ("map_keyword_clusters", "read_competitor_headings") in edges
    assert ("read_competitor_headings", "generate_outline") in edges
    assert ("map_keyword_clusters", "generate_outline") not in edges
