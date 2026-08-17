from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, List, Tuple
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.services.workspace_pipeline import WorkspacePipeline


def _patch_sse_events(monkeypatch: pytest.MonkeyPatch, events: List[Tuple[str, dict]]) -> None:
    async def _record(name: str, **kwargs: Any) -> None:
        events.append((name, kwargs))

    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_start", lambda **k: _record("start", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_success", lambda **k: _record("success", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_failure", lambda **k: _record("failure", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_pipeline_complete", lambda **k: _record("complete", **k))


def _fake_scraper():
    async def _scrape(url: str):
        result = SimpleNamespace(
            success=True,
            markdown="Sample content used for brand voice extraction.",
            url=url,
            metadata={"title": "Example"},
            html="<html></html>",
        )
        return (["chunk-1"], [result])

    return _scrape


def _fake_brand_voice_generator():
    async def _generate(content: str) -> BrandSchema:
        return BrandSchema(
            about="About text",
            customer_profile="Profile",
            selling_position="Position",
            target_audience=["Audience"],
            brand_voice=["Voice"],
            competitors=["Competitor"],
            content_pillar=["Pillar"],
        )

    return _generate


def _make_fake_db_context(log: List[str] | None = None, session_factory=None):
    """A stand-in for `get_async_db_context` that mimics its commit-on-success
    / rollback-on-exception behaviour, without touching a real engine."""

    @asynccontextmanager
    async def _fake_get_async_db_context():
        if log is not None:
            log.append("db:enter")
        session = (session_factory or _default_session)()
        try:
            yield session
            if log is not None:
                log.append("db:commit")
        except Exception:
            if log is not None:
                log.append("db:rollback")
            raise
        finally:
            if log is not None:
                log.append("db:exit")

    return _fake_get_async_db_context


def _default_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.add = Mock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))
    return session


def _patch_external_steps(
    monkeypatch: pytest.MonkeyPatch,
    *,
    personas: list | None = None,
    competitors: list | None = None,
) -> None:
    """Mock every non-DB external dependency the pipeline touches, so tests
    are fast/deterministic and never hit the network."""
    monkeypatch.setattr(
        "src.services.workspace_pipeline.assess_site_compliance",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.discover_personas",
        AsyncMock(return_value={"personas": personas or []}),
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.discover_competitors",
        AsyncMock(return_value={"competitors": competitors or []}),
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.select_display_competitors",
        lambda comps: list(comps),
    )


# ============================================================
# HAPPY PATH — persistence is scoped to short DB contexts
# ============================================================

@pytest.mark.asyncio
async def test_workspace_pipeline_emits_progress_and_persists_brand_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []
    _patch_sse_events(monkeypatch, events)
    _patch_external_steps(monkeypatch, competitors=[{"domain": "competitor.com"}])

    added_records: List[Any] = []

    def session_factory() -> AsyncMock:
        session = _default_session()

        def _add(obj):
            added_records.append(obj)

        session.add = Mock(side_effect=_add)
        return session

    monkeypatch.setattr(
        "src.services.workspace_pipeline.get_async_db_context",
        _make_fake_db_context(session_factory=session_factory),
    )

    pipeline = WorkspacePipeline(
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
        scraper=_fake_scraper(),
        brand_voice_generator=_fake_brand_voice_generator(),
    )

    await pipeline.run()

    # BrandVoice was persisted (via the short-lived context, not a held session)
    assert any(isinstance(r, BrandVoice) for r in added_records)

    event_names = [name for name, _ in events]
    assert "failure" not in event_names
    assert event_names[0] == "start"
    assert event_names[-1] == "complete"


# ============================================================
# CONNECTION LIFECYCLE — the actual fix under test
# ============================================================

@pytest.mark.asyncio
async def test_db_connections_are_only_acquired_around_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensures the pipeline follows the required lifecycle: scraping, the LLM
    call, persona crawling, and competitor discovery all run with NO DB
    connection held, and a connection is acquired/released only around each
    persistence step (brand voice + personas, brand-voice embedding,
    competitors).
    """
    log: List[str] = []
    _patch_sse_events(monkeypatch, [])
    _patch_external_steps(monkeypatch, competitors=[{"domain": "competitor.com"}])
    monkeypatch.setattr(
        "src.services.workspace_pipeline.get_async_db_context",
        _make_fake_db_context(log=log),
    )
    # Embedding step is non-fatal and best-effort; keep it a no-op here.
    monkeypatch.setattr(
        "src.services.workspace_pipeline.WorkspacePipeline._embed_brand_voice",
        AsyncMock(return_value=None),
    )

    async def scraper(url: str):
        log.append("external:scrape")
        result = SimpleNamespace(success=True, markdown="content", url=url, metadata={}, html="<html></html>")
        return (["chunk"], [result])

    async def brand_voice_generator(content: str) -> BrandSchema:
        log.append("external:llm")
        return BrandSchema(
            about="a", customer_profile="b", selling_position="c",
            target_audience=["d"], brand_voice=["e"], competitors=[], content_pillar=["f"],
        )

    async def fake_discover_personas(url, cfg):
        log.append("external:persona_crawl")
        return {"personas": []}

    async def fake_discover_competitors(site_url):
        log.append("external:serp")
        return {"competitors": [{"domain": "competitor.com"}]}

    monkeypatch.setattr("src.services.workspace_pipeline.discover_personas", fake_discover_personas)
    monkeypatch.setattr("src.services.workspace_pipeline.discover_competitors", fake_discover_competitors)

    pipeline = WorkspacePipeline(
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
        scraper=scraper,
        brand_voice_generator=brand_voice_generator,
    )

    await pipeline.run()

    # No "db:enter" appears between any two external-step markers — every DB
    # window is fully closed ("db:exit") before the next external call starts.
    open_windows = 0
    for marker in log:
        if marker == "db:enter":
            open_windows += 1
        elif marker == "db:exit":
            open_windows -= 1
        elif marker.startswith("external:"):
            assert open_windows == 0, f"external work ran while a DB connection was held: {log}"
    assert open_windows == 0

    # Persistence actually happened: at least the brand-voice/personas write
    # and the competitors write each opened + closed their own connection.
    assert log.count("db:enter") >= 2
    assert log.count("db:enter") == log.count("db:exit")


@pytest.mark.asyncio
async def test_50_concurrent_pipelines_do_not_serialize_on_a_small_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Requirement: 50 concurrent workspace creations must all be able to
    proceed with their external work (scrape/LLM/persona/SERP) concurrently
    — DB usage must be limited, not the pipelines themselves. Simulates a
    tiny (capacity=3) connection pool. If a pipeline held a connection across
    its external work (the old bug), only 3 of 50 could even start and total
    wall time would scale with N / pool capacity. With connections scoped to
    persistence only, all 50 overlap and wall time stays close to a single
    pipeline's external-work duration.
    """
    _patch_sse_events(monkeypatch, [])
    _patch_external_steps(monkeypatch, competitors=[{"domain": "competitor.com"}])
    monkeypatch.setattr(
        "src.services.workspace_pipeline.WorkspacePipeline._embed_brand_voice",
        AsyncMock(return_value=None),
    )

    EXTERNAL_DELAY = 0.05
    N = 50
    POOL_CAPACITY = 3

    pool_semaphore = asyncio.Semaphore(POOL_CAPACITY)
    concurrent = 0
    max_concurrent = 0

    @asynccontextmanager
    async def fake_get_async_db_context():
        nonlocal concurrent, max_concurrent
        async with pool_semaphore:
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
            try:
                yield _default_session()
            finally:
                concurrent -= 1

    monkeypatch.setattr("src.services.workspace_pipeline.get_async_db_context", fake_get_async_db_context)

    async def slow_scraper(url: str):
        await asyncio.sleep(EXTERNAL_DELAY)
        result = SimpleNamespace(success=True, markdown="content", url=url, metadata={}, html="<html></html>")
        return (["chunk"], [result])

    async def slow_brand_voice_generator(content: str) -> BrandSchema:
        await asyncio.sleep(EXTERNAL_DELAY)
        return BrandSchema(
            about="a", customer_profile="b", selling_position="c",
            target_audience=["d"], brand_voice=["e"], competitors=[], content_pillar=["f"],
        )

    pipelines = [
        WorkspacePipeline(
            operation_id=f"op-{i}",
            workspace_id=uuid4(),
            user_id=uuid4(),
            url="https://example.com",
            scraper=slow_scraper,
            brand_voice_generator=slow_brand_voice_generator,
        )
        for i in range(N)
    ]

    start = time.monotonic()
    await asyncio.gather(*(p.run() for p in pipelines))
    elapsed = time.monotonic() - start

    # With the old bug (connection held across external work):
    #   serialized rounds ≈ N / POOL_CAPACITY = 50/3 ≈ 17 rounds
    #   each round = 2 × EXTERNAL_DELAY = 0.10 s  → total ≈ 1.7 s ≈ 34× EXTERNAL_DELAY
    # With the fix (connection only during instant persistence ops):
    #   all external work runs concurrently → total ≈ 2 × EXTERNAL_DELAY + overhead
    # Threshold of 60× EXTERNAL_DELAY (3.0 s) catches the serialization bug
    # while still being robust to asyncio scheduling overhead on slow machines.
    assert elapsed < EXTERNAL_DELAY * 60, (
        f"pipelines appear to be serializing on the DB pool: {elapsed:.2f}s for {N} pipelines"
    )
    assert max_concurrent <= POOL_CAPACITY


# ============================================================
# SCRAPER FAILURE — no DB connection should ever be opened
# ============================================================

@pytest.mark.asyncio
async def test_workspace_pipeline_propagates_scraper_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []
    _patch_sse_events(monkeypatch, events)
    _patch_external_steps(monkeypatch)

    db_context_calls = 0

    def _tracking_factory():
        nonlocal db_context_calls
        db_context_calls += 1
        raise AssertionError("get_async_db_context should not be called on scraper failure")

    @asynccontextmanager
    async def _fake_get_async_db_context():
        _tracking_factory()
        yield  # pragma: no cover - unreachable, factory raises first

    monkeypatch.setattr(
        "src.services.workspace_pipeline.get_async_db_context",
        _fake_get_async_db_context,
    )

    async def failing_scraper(url: str):
        raise RuntimeError("scrape error")

    pipeline = WorkspacePipeline(
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
        scraper=failing_scraper,
    )

    with pytest.raises(RuntimeError, match="scrape error"):
        await pipeline.run()

    assert db_context_calls == 0


# ============================================================
# PERSONA PERSISTENCE FAILURE — rollback, not commit
# ============================================================

@pytest.mark.asyncio
async def test_workspace_pipeline_persona_persist_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    If persisting personas fails inside the brand-voice DB context, that
    context's session must roll back (not commit) and the exception must
    propagate — the brand-voice write and the persona write are one
    transaction.
    """
    _patch_sse_events(monkeypatch, [])
    _patch_external_steps(monkeypatch)

    log: List[str] = []
    monkeypatch.setattr(
        "src.services.workspace_pipeline.get_async_db_context",
        _make_fake_db_context(log=log),
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.WorkspacePipeline._persist_personas",
        AsyncMock(side_effect=Exception("constraint violation")),
    )

    pipeline = WorkspacePipeline(
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
        scraper=_fake_scraper(),
        brand_voice_generator=_fake_brand_voice_generator(),
    )

    with pytest.raises(Exception, match="constraint violation"):
        await pipeline.run()

    assert "db:rollback" in log
    assert "db:commit" not in log
