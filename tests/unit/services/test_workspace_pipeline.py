from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Tuple
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.services.workspace_pipeline import WorkspacePipeline


@pytest.mark.asyncio
async def test_workspace_pipeline_emits_progress_and_persists_brand_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []

    async def _record(name: str, **kwargs: Any) -> None:
        events.append((name, kwargs))

    async def emit_start(**kwargs: Any) -> None:
        await _record("start", **kwargs)

    async def emit_success(**kwargs: Any) -> None:
        await _record("success", **kwargs)

    async def emit_failure(**kwargs: Any) -> None:
        await _record("failure", **kwargs)

    async def emit_complete(**kwargs: Any) -> None:
        await _record("complete", **kwargs)

    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_start", emit_start)
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_success", emit_success)
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_failure", emit_failure)
    monkeypatch.setattr("src.services.workspace_pipeline.emit_pipeline_complete", emit_complete)

    db_session = AsyncMock(spec=AsyncSession)
    db_session.add = Mock()
    db_session.flush = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()
    db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))

    async def fake_scraper(url: str) -> Tuple[list[str], list[Any]]:
        result = SimpleNamespace(
            success=True,
            markdown="Sample content used for brand voice extraction.",
            url=url,
            metadata={"title": "Example"},
        )
        return (["chunk-1"], [result])

    async def fake_vector_uploader(chunks: list[str], workspace_id: str) -> bool:
        assert chunks == ["chunk-1"]
        assert workspace_id
        return True

    async def fake_brand_voice_generator(content: str) -> BrandSchema:
        assert "Sample content" in content
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
        url="https://example.com",
        scraper=fake_scraper,
        vector_uploader=fake_vector_uploader,
        brand_voice_generator=fake_brand_voice_generator,
    )

    await pipeline.run()

    assert db_session.add.call_count == 1
    brand_voice_record = db_session.add.call_args[0][0]
    assert isinstance(brand_voice_record, BrandVoice)
    db_session.commit.assert_awaited_once()

    event_names = [name for name, _ in events]
    assert event_names.count("failure") == 0
    assert event_names[0] == "start"
    assert event_names[-1] == "complete"
    assert any(name == "start" and data.get("step") == "scrape" for name, data in events)


@pytest.mark.asyncio
async def test_workspace_pipeline_propagates_scraper_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    events: List[Tuple[str, dict[str, Any]]] = []

    async def _record(name: str, **kwargs: Any) -> None:
        events.append((name, kwargs))

    async def emit_start(**kwargs: Any) -> None:
        await _record("start", **kwargs)

    async def emit_success(**kwargs: Any) -> None:
        await _record("success", **kwargs)

    async def emit_failure(**kwargs: Any) -> None:
        await _record("failure", **kwargs)

    async def emit_complete(**kwargs: Any) -> None:
        await _record("complete", **kwargs)

    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_start", emit_start)
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_success", emit_success)
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_failure", emit_failure)
    monkeypatch.setattr("src.services.workspace_pipeline.emit_pipeline_complete", emit_complete)

    db_session = AsyncMock(spec=AsyncSession)
    db_session.add = Mock()
    db_session.flush = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()

    async def failing_scraper(url: str) -> Tuple[list[str], list[Any]]:
        raise RuntimeError("scrape error")

    pipeline = WorkspacePipeline(
        db=db_session,
        operation_id="op-123",
        workspace_id=uuid4(),
        url="https://example.com",
        scraper=failing_scraper,
    )

    with pytest.raises(RuntimeError, match="scrape error"):
        await pipeline.run()

    # should not attempt to persist data
    db_session.add.assert_not_called()
    db_session.commit.assert_not_awaited()

    event_names = [name for name, _ in events]
    assert event_names.count("failure") >= 1
    assert events[-1][0] == "failure"
