"""The workspace's run says what it finds as it goes (revnix/rext-control#845).

While a new workspace's website is read, the creation screen shows the workspace
taking shape. Each step's end already carried what it found; these are the lines
in between: which pages were read, the people once they are saved, and where the
competitor search is. They are progress events: they end no step, and a failure
to send one never fails the run.
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

import src.flow.engines.competitors.pipeline as discovery
import src.services.workspace_pipeline as pipeline_module
from src.services.workspace_pipeline import (
    MAX_PAGES_REPORTED,
    MAX_PEOPLE_REPORTED,
    WorkspacePipeline,
)


def _pipeline(url="https://acme.example"):
    return WorkspacePipeline(
        db=AsyncMock(),
        operation_id="op-1",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url=url,
        scraper=AsyncMock(),
        brand_voice_generator=AsyncMock(),
    )


@pytest.fixture
def said(monkeypatch):
    """Every progress event the pipeline sends: (step, message, payload)."""
    sent = []

    async def _progress(*, operation_id, scope, step, message, payload=None, **_):
        sent.append((step, message, payload))

    monkeypatch.setattr(pipeline_module, "emit_step_progress", _progress)
    return sent


# --- the competitor search ----------------------------------------------------


@pytest.fixture
def a_search(monkeypatch):
    """The discovery's phases, each a stand-in that answers at once."""
    monkeypatch.setattr(discovery, "scrape_site", AsyncMock(return_value=["page"]))
    monkeypatch.setattr(
        discovery,
        "summarize_business",
        AsyncMock(return_value={"company_name": "Acme", "category": "anvils"}),
    )
    monkeypatch.setattr(
        discovery,
        "generate_queries",
        AsyncMock(
            return_value={"category_queries": ["best anvils", "anvil makers"], "brand_queries": []}
        ),
    )
    monkeypatch.setattr(discovery, "run_all_searches", AsyncMock(return_value=[{"r": 1}]))
    monkeypatch.setattr(discovery, "mine_all_listicles", AsyncMock(return_value=[]))
    candidates = {
        "boltco.com": {"frequency": 2, "mined": False, "sources": {"best anvils"}},
        "notone.com": {"frequency": 1, "mined": False, "sources": set()},
    }
    monkeypatch.setattr(discovery, "aggregate_candidates", Mock(return_value=candidates))
    monkeypatch.setattr(
        discovery,
        "classify_all",
        AsyncMock(
            return_value={
                "boltco.com": {"is_competitor": True, "confidence": 0.9},
                "notone.com": {"is_competitor": False, "confidence": 0.2},
            }
        ),
    )


async def test_the_search_says_where_it_is_before_each_long_part(a_search):
    heard = []

    async def listen(progress):
        heard.append(progress)

    result = await discovery.discover_competitors("https://acme.com", on_progress=listen)

    assert heard == [
        {"stage": "searching", "queries": 2},
        {"stage": "checking", "candidates": 2},
    ]
    assert [row["domain"] for row in result["competitors"]] == ["boltco.com"]


async def test_the_search_is_the_same_without_a_listener_or_with_one_that_fails(a_search):
    async def broken(progress):
        raise RuntimeError("the stream is gone")

    quiet = await discovery.discover_competitors("https://acme.com")
    noisy = await discovery.discover_competitors("https://acme.com", on_progress=broken)

    assert [row["domain"] for row in quiet["competitors"]] == ["boltco.com"]
    assert [row["domain"] for row in noisy["competitors"]] == ["boltco.com"]


async def test_the_run_passes_the_searchs_progress_on_as_events(said, monkeypatch):
    async def fake_discovery(site_url, on_progress=None):
        await on_progress({"stage": "searching", "queries": 8})
        await on_progress({"stage": "checking", "candidates": 34})
        return {"competitors": []}

    monkeypatch.setattr(pipeline_module, "discover_competitors", fake_discovery)
    monkeypatch.setattr(pipeline_module, "emit_step_start", AsyncMock())
    monkeypatch.setattr(pipeline_module, "emit_step_success", AsyncMock())

    await _pipeline()._discover_competitors()

    assert [(step, payload) for step, _, payload in said] == [
        ("competitor_discovery", {"stage": "searching", "queries": 8}),
        ("competitor_discovery", {"stage": "checking", "candidates": 34}),
    ]


# --- the pages and the people -------------------------------------------------


def test_the_pages_read_are_listed_with_what_each_is_the_home_page_first():
    pipeline = _pipeline()
    pipeline._page_text_by_url = {
        "https://acme.example/blog/forging": "Article author: Ana Ruiz\nHow to forge.",
        "https://acme.example/about": "About Acme. We make anvils.",
        "https://acme.example/": "Acme. Anvils that last.",
    }

    pages = pipeline._pages_read()

    assert pages == [
        {"page": "https://acme.example/", "kind": "home"},
        {"page": "https://acme.example/about", "kind": "about"},
        {"page": "https://acme.example/blog/forging", "kind": "article"},
    ]


def test_a_page_is_named_as_a_reader_would_name_it():
    pipeline = _pipeline("https://www.acme.example")

    assert pipeline._page_kind("https://acme.example", "Acme.") == "home"
    assert pipeline._page_kind("https://acme.example/about-us/", "We make anvils.") == "about"
    assert pipeline._page_kind("https://acme.example/team", "Ana Ruiz, founder.") == "team"
    assert pipeline._page_kind("https://acme.example/pricing", "Plans.") == "other"
    # A post about the company is still a post.
    assert (
        pipeline._page_kind("https://acme.example/blog/about-anvils", "Article author: Ana Ruiz\n")
        == "article"
    )


def test_the_list_of_pages_is_bounded():
    pipeline = _pipeline()
    pipeline._page_text_by_url = {
        f"https://acme.example/blog/{number}": "text" for number in range(MAX_PAGES_REPORTED + 9)
    }

    assert len(pipeline._pages_read()) == MAX_PAGES_REPORTED
    assert _pipeline()._pages_read() == []


async def test_a_progress_event_that_cannot_be_sent_never_fails_the_run(monkeypatch):
    async def _down(**_):
        raise ConnectionError("no stream")

    monkeypatch.setattr(pipeline_module, "emit_step_progress", _down)

    await _pipeline()._say("scrape", "Read 3 pages", {"pages": []})


async def test_the_people_are_said_the_moment_they_are_saved(said):
    pipeline = _pipeline()
    pipeline._extracted_personas = [
        {"full_name": f"Person {number}", "professional_title": "Smith" if number == 0 else None}
        for number in range(MAX_PEOPLE_REPORTED + 3)
    ]

    await pipeline._say_people()

    step, _, payload = said[-1]
    assert step == "personas"
    assert payload["count"] == MAX_PEOPLE_REPORTED + 3
    assert len(payload["people"]) == MAX_PEOPLE_REPORTED
    assert payload["people"][0] == {"person": "Person 0", "title": "Smith"}


async def test_no_one_saved_is_said_too(said):
    await _pipeline()._say_people()

    assert said[-1][0] == "personas"
    assert said[-1][2] == {"people": [], "count": 0}


async def test_a_run_that_drafts_no_voice_says_no_one_was_saved(said):
    """No voice means the personas are never reached: the screen is told at once, not left
    to wait for people through the competitor search."""
    assert await _pipeline()._persist_brand_voice(None) is None

    assert [(step, payload) for step, _, payload in said] == [
        ("personas", {"people": [], "count": 0})
    ]
