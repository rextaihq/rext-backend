from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
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


def _patch_scrape(monkeypatch: pytest.MonkeyPatch, *, content: str = "Sample content.", side_effect=None) -> None:
    """`_fast_or_fallback_scrape` is the real scrape seam post-fast_scraper
    refactor — bypass it directly so tests never touch fast_scraper/crawl4ai."""
    if side_effect is not None:
        mock = AsyncMock(side_effect=side_effect)
    else:
        mock = AsyncMock(return_value=(content, "<html></html>", False))
    monkeypatch.setattr(
        "src.services.workspace_pipeline.WorkspacePipeline._fast_or_fallback_scrape",
        mock,
    )


def _patch_external_steps(
    monkeypatch: pytest.MonkeyPatch,
    *,
    competitors: list | None = None,
) -> None:
    """Mock every non-DB external dependency the pipeline touches, so tests
    are fast/deterministic and never hit the network."""
    monkeypatch.setattr(
        "src.services.workspace_pipeline.assess_site_compliance",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.discover_competitors",
        AsyncMock(return_value={"competitors": competitors or []}),
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.select_display_competitors",
        lambda comps: list(comps),
    )


def _fake_brand_voice_generator(personas: list | None = None):
    async def _generate(content: str) -> BrandSchema:
        return BrandSchema(
            about="About text",
            customer_profile="Profile",
            selling_position="Position",
            target_audience=["Audience"],
            brand_voice=["Voice"],
            competitors=[],
            content_pillar=["Pillar"],
            personas=personas or [],
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


# ============================================================
# HAPPY PATH — persistence is scoped to short DB contexts
# ============================================================

@pytest.mark.asyncio
async def test_workspace_pipeline_emits_progress_and_persists_brand_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []
    _patch_sse_events(monkeypatch, events)
    _patch_scrape(monkeypatch)
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
        brand_voice_generator=_fake_brand_voice_generator(
            personas=[{"name": "Jane Founder", "source": "founder"}]
        ),
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
    call, and competitor discovery all run with NO DB connection held, and a
    connection is acquired/released only around each persistence step (brand
    voice + personas, brand-voice embedding, competitors).
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

    async def scrape(self):
        log.append("external:scrape")
        return "content", "<html></html>", False

    monkeypatch.setattr("src.services.workspace_pipeline.WorkspacePipeline._fast_or_fallback_scrape", scrape)

    async def brand_voice_generator(content: str) -> BrandSchema:
        log.append("external:llm")
        return BrandSchema(
            about="a", customer_profile="b", selling_position="c",
            target_audience=["d"], brand_voice=["e"], competitors=[], content_pillar=["f"],
            personas=[{"name": "Jane Founder", "source": "founder"}],
        )

    async def fake_discover_competitors(site_url):
        log.append("external:serp")
        return {"competitors": [{"domain": "competitor.com"}]}

    monkeypatch.setattr("src.services.workspace_pipeline.discover_competitors", fake_discover_competitors)

    pipeline = WorkspacePipeline(
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
        brand_voice_generator=brand_voice_generator,
    )

    await pipeline.run()

    # No "db:enter" appears while external work is in flight — every DB
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
    proceed with their external work (scrape/LLM/SERP) concurrently — DB
    usage must be limited, not the pipelines themselves. Simulates a tiny
    (capacity=3) connection pool.

    Asserted via peak *concurrency counts* rather than wall-clock time — the
    property under test (external work isn't gated by the DB pool) shows up
    directly as "how many pipelines were mid-scrape at once", which is exact
    and immune to machine speed. If a pipeline held a connection across its
    external work (the old bug), at most POOL_CAPACITY pipelines could ever
    be doing external work simultaneously (the rest would be blocked waiting
    on the pool semaphore before they could even reach the scrape step).
    """
    _patch_sse_events(monkeypatch, [])
    _patch_external_steps(monkeypatch, competitors=[{"domain": "competitor.com"}])
    # Embedding hits a real external service when not mocked — not the thing
    # this test is measuring.
    monkeypatch.setattr(
        "src.services.workspace_pipeline.WorkspacePipeline._embed_brand_voice",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("src.services.workspace_pipeline.logger", Mock())

    N = 50
    POOL_CAPACITY = 3

    pool_semaphore = asyncio.Semaphore(POOL_CAPACITY)
    db_concurrent = 0
    max_db_concurrent = 0

    @asynccontextmanager
    async def fake_get_async_db_context():
        nonlocal db_concurrent, max_db_concurrent
        async with pool_semaphore:
            db_concurrent += 1
            max_db_concurrent = max(max_db_concurrent, db_concurrent)
            try:
                yield _default_session()
            finally:
                db_concurrent -= 1

    monkeypatch.setattr("src.services.workspace_pipeline.get_async_db_context", fake_get_async_db_context)

    # A barrier-style gate: every pipeline signals it has started scraping,
    # then waits for all N to arrive before proceeding. This deterministically
    # proves peak external-work concurrency reaches N, without depending on
    # sleep durations or scheduler timing at all.
    arrived = 0
    all_arrived = asyncio.Event()

    async def gated_scrape(self):
        nonlocal arrived
        arrived += 1
        if arrived == N:
            all_arrived.set()
        await asyncio.wait_for(all_arrived.wait(), timeout=5)
        return "content", "<html></html>", False

    monkeypatch.setattr("src.services.workspace_pipeline.WorkspacePipeline._fast_or_fallback_scrape", gated_scrape)

    async def brand_voice_generator(content: str) -> BrandSchema:
        return BrandSchema(
            about="a", customer_profile="b", selling_position="c",
            target_audience=["d"], brand_voice=["e"], competitors=[], content_pillar=["f"],
            personas=[],
        )

    pipelines = [
        WorkspacePipeline(
            operation_id=f"op-{i}",
            workspace_id=uuid4(),
            user_id=uuid4(),
            url="https://example.com",
            brand_voice_generator=brand_voice_generator,
        )
        for i in range(N)
    ]

    await asyncio.gather(*(p.run() for p in pipelines))

    # All N pipelines reached the scrape step and were in flight at once —
    # proves external work isn't gated by (or waiting on) the tiny DB pool.
    assert arrived == N

    # The DB pool itself was still respected for the (brief) persistence bursts.
    assert max_db_concurrent <= POOL_CAPACITY


# ============================================================
# SCRAPER FAILURE — no DB connection should ever be opened
# ============================================================

@pytest.mark.asyncio
async def test_workspace_pipeline_propagates_scraper_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []
    _patch_sse_events(monkeypatch, events)
    _patch_scrape(monkeypatch, side_effect=RuntimeError("scrape error"))
    _patch_external_steps(monkeypatch)

    db_context_calls = 0

    @asynccontextmanager
    async def _fake_get_async_db_context():
        nonlocal db_context_calls
        db_context_calls += 1
        raise AssertionError("get_async_db_context should not be called on scraper failure")
        yield  # pragma: no cover - unreachable

    monkeypatch.setattr(
        "src.services.workspace_pipeline.get_async_db_context",
        _fake_get_async_db_context,
    )

    pipeline = WorkspacePipeline(
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
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
    _patch_scrape(monkeypatch)
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
        brand_voice_generator=_fake_brand_voice_generator(
            personas=[{"name": "Jane Founder", "source": "founder"}]
        ),
    )

    with pytest.raises(Exception, match="constraint violation"):
        await pipeline.run()

    assert "db:rollback" in log
    assert "db:commit" not in log
