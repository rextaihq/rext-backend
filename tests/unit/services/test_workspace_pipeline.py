from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Tuple
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.services.workspace_pipeline import WorkspacePipeline


class _FakeExecuteResult:
    """Mimics the SQLAlchemy result object for a single scalar_one_or_none() row."""

    def __init__(self, row: Any) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row

    def scalars(self) -> Any:
        return SimpleNamespace(all=lambda: [])


# ============================================================
# HAPPY PATH TEST
# ============================================================


@pytest.mark.asyncio
async def test_workspace_pipeline_emits_progress_and_persists_brand_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []

    async def _record(name: str, **kwargs: Any) -> None:
        events.append((name, kwargs))

    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_start", lambda **k: _record("start", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_success", lambda **k: _record("success", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_failure", lambda **k: _record("failure", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_pipeline_complete",
        lambda **k: _record("complete", **k),
    )

    db_session = AsyncMock(spec=AsyncSession)
    db_session.add = Mock()
    db_session.flush = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()

    mock_exec = Mock()
    mock_exec.scalar_one_or_none.return_value = None
    mock_exec.scalars.return_value.all.return_value = []
    db_session.execute = AsyncMock(return_value=mock_exec)

    async def fake_scraper(url: str):
        result = SimpleNamespace(
            success=True,
            markdown="Sample content used for brand voice extraction.",
            url=url,
            metadata={"title": "Example"},
        )
        return (["chunk-1"], [result])

    async def fake_vector_uploader(chunks: list[str], workspace_id: str) -> bool:
        return True

    async def fake_brand_voice_generator(content: str) -> BrandSchema:
        return BrandSchema(
            about="About text",
            customer_profile="Profile",
            selling_position="Position",
            target_audience=["Audience"],
            brand_voice=["Voice"],
            competitors=["Competitor"],
            content_pillar=["Pillar"],
        )

    pipeline = WorkspacePipeline(
        db=db_session,
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
        scraper=fake_scraper,
        vector_uploader=fake_vector_uploader,
        brand_voice_generator=fake_brand_voice_generator,
    )
    pipeline._discover_competitors = AsyncMock(return_value=None)

    await pipeline.run()

    # DB assertions
    assert db_session.add.call_count == 1
    assert isinstance(db_session.add.call_args[0][0], BrandVoice)
    db_session.commit.assert_awaited()

    # Event assertions
    event_names = [name for name, _ in events]
    assert "failure" not in event_names
    assert event_names[0] == "start"
    assert event_names[-1] == "complete"


@pytest.mark.asyncio
async def test_workspace_pipeline_discovers_and_persists_competitors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []

    async def _record(name: str, **kwargs: Any) -> None:
        events.append((name, kwargs))

    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_start", lambda **k: _record("start", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_success", lambda **k: _record("success", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_failure", lambda **k: _record("failure", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_pipeline_complete",
        lambda **k: _record("complete", **k),
    )

    ws_id = uuid4()
    existing_brand_voice = BrandVoice(workspace_id=ws_id, brand_name="TestBrand")
    db_session = AsyncMock(spec=AsyncSession)
    db_session.add = Mock()
    db_session.flush = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()

    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = existing_brand_voice
    mock_result.scalars.return_value.all.return_value = []
    db_session.execute = AsyncMock(return_value=mock_result)

    async def fake_scraper(url: str):
        result = SimpleNamespace(
            success=True,
            markdown="Sample content",
            url=url,
            metadata={"title": "Example"},
        )
        return (["chunk-1"], [result])

    async def fake_vector_uploader(chunks: list[str], workspace_id: str) -> bool:
        return True

    async def fake_brand_voice_generator(content: str) -> BrandSchema:
        return BrandSchema(brand_name="TestBrand")

    pipeline = WorkspacePipeline(
        db=db_session,
        operation_id="op-123",
        workspace_id=ws_id,
        user_id=uuid4(),
        url="https://example.com",
        scraper=fake_scraper,
        vector_uploader=fake_vector_uploader,
        brand_voice_generator=fake_brand_voice_generator,
    )
    mock_competitors = [
        {"domain": "competitor1.com", "confidence": 0.9, "is_competitor": True},
        {"domain": "competitor2.com", "confidence": 0.85, "is_competitor": True},
    ]
    pipeline._discover_competitors = AsyncMock(return_value=mock_competitors)

    await pipeline.run()

    # Competitors should be assigned to existing BrandVoice
    assert existing_brand_voice.competitors == ["competitor1.com", "competitor2.com"]
    db_session.commit.assert_awaited()

    # Pipeline complete payload should contain the competitors
    complete_events = [data for name, data in events if name == "complete"]
    assert len(complete_events) == 1
    complete_payload = complete_events[0]["payload"]
    assert complete_payload["brand_voice"]["competitors"] == ["competitor1.com", "competitor2.com"]
    assert complete_payload["top_competitors"] == mock_competitors


# ============================================================
# BRAND NAME PERSISTENCE REGRESSION
#
# A brand-voice refresh replaces the stored brand name with the one scraped
# from the site. The stored name is kept only when extraction found none.
# ============================================================


@pytest.mark.asyncio
async def test_refresh_replaces_an_existing_brand_name() -> None:
    workspace_id = uuid4()
    existing = BrandVoice(
        id=uuid4(),
        workspace_id=workspace_id,
        brand_name="Manually Renamed Brand",
    )

    db_session = AsyncMock(spec=AsyncSession)
    db_session.execute = AsyncMock(return_value=_FakeExecuteResult(existing))
    db_session.flush = AsyncMock()

    pipeline = WorkspacePipeline(
        db=db_session,
        operation_id="op-brand-name",
        workspace_id=workspace_id,
        user_id=uuid4(),
        url="https://example.com",
    )

    scraped = BrandSchema(
        brand_name="Scraped Site Title",
        about="About text",
        customer_profile="Profile",
        selling_position="Position",
    )

    result = await pipeline._persist_brand_voice(scraped)

    assert result.brand_name == "Scraped Site Title"
    assert result.about == "About text"


@pytest.mark.asyncio
async def test_refresh_fills_in_a_blank_brand_name() -> None:
    workspace_id = uuid4()
    existing = BrandVoice(id=uuid4(), workspace_id=workspace_id, brand_name=None)

    db_session = AsyncMock(spec=AsyncSession)
    db_session.execute = AsyncMock(return_value=_FakeExecuteResult(existing))
    db_session.flush = AsyncMock()

    pipeline = WorkspacePipeline(
        db=db_session,
        operation_id="op-brand-name-blank",
        workspace_id=workspace_id,
        user_id=uuid4(),
        url="https://example.com",
    )

    scraped = BrandSchema(brand_name="Scraped Site Title")

    result = await pipeline._persist_brand_voice(scraped)

    assert result.brand_name == "Scraped Site Title"


# ============================================================
# SCRAPER FAILURE TEST
# ============================================================


@pytest.mark.asyncio
async def test_workspace_pipeline_propagates_scraper_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []

    async def _record(name: str, **kwargs: Any) -> None:
        events.append((name, kwargs))

    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_start", lambda **k: _record("start", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_success", lambda **k: _record("success", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_step_failure", lambda **k: _record("failure", **k)
    )
    monkeypatch.setattr(
        "src.services.workspace_pipeline.emit_pipeline_complete",
        lambda **k: _record("complete", **k),
    )

    db_session = AsyncMock(spec=AsyncSession)
    db_session.add = Mock()
    db_session.flush = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()

    async def failing_scraper(url: str):
        raise RuntimeError("scrape error")

    pipeline = WorkspacePipeline(
        db=db_session,
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
        scraper=failing_scraper,
    )

    async def failing_fast_scrape(*args, **kwargs):
        raise RuntimeError("scrape error")

    pipeline._fast_or_fallback_scrape = failing_fast_scrape
    pipeline._feed_attempt = AsyncMock(return_value={})

    with pytest.raises(RuntimeError, match="scrape error"):
        await pipeline.run()

    db_session.add.assert_not_called()
    db_session.commit.assert_not_awaited()
    db_session.rollback.assert_awaited()


# ============================================================
# ⭐ NEW REQUIRED TEST — SAVEPOINT ROLLBACK
# ============================================================


@pytest.mark.asyncio
async def test_workspace_pipeline_persona_partial_insertion_rolls_back() -> None:
    """
    Ensures that if persona insertion fails inside begin_nested(),
    the deletion is rolled back and commit is NOT executed.
    """
    from sqlalchemy import delete

    from src.api.models.knowledge_models.persona_model import Persona

    db_session = AsyncMock(spec=AsyncSession)
    db_session.add = Mock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()

    # simulate flush failing for one persona
    async def failing_flush():
        raise Exception("constraint violation")

    db_session.flush = AsyncMock(side_effect=failing_flush)

    # simulate execute to return existing personas
    db_session.execute = AsyncMock(return_value=Mock(scalars=Mock(return_value=[])))

    async def fake_scraper(url: str):
        result = SimpleNamespace(
            success=True,
            markdown="content",
            url=url,
            metadata={},
        )
        return (["chunk"], [result])

    pipeline = WorkspacePipeline(
        db=db_session,
        operation_id="op-123",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://example.com",
        scraper=fake_scraper,
    )

    # Inject fake personas to trigger deletion + insert
    pipeline._persist_personas = AsyncMock(side_effect=Exception("constraint violation"))

    with pytest.raises(Exception, match="constraint violation"):
        await pipeline.run()

    # Flush failed → rollback triggered → commit should NOT be called
    db_session.rollback.assert_awaited()
    db_session.commit.assert_not_awaited()
