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

    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_start", lambda **k: _record("start", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_success", lambda **k: _record("success", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_failure", lambda **k: _record("failure", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_pipeline_complete", lambda **k: _record("complete", **k))

    db_session = AsyncMock(spec=AsyncSession)
    db_session.add = Mock()
    db_session.flush = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()

    scalar_none = Mock(return_value=None)
    db_session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=scalar_none))

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
            content_strategy=["Pillar"],
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

    await pipeline.run()

    # DB assertions
    assert db_session.add.call_count == 1
    assert isinstance(db_session.add.call_args[0][0], BrandVoice)
    db_session.commit.assert_awaited_once()

    # Event assertions
    event_names = [name for name, _ in events]
    assert "failure" not in event_names
    assert event_names[0] == "start"
    assert event_names[-1] == "complete"


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

    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_start", lambda **k: _record("start", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_success", lambda **k: _record("success", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_step_failure", lambda **k: _record("failure", **k))
    monkeypatch.setattr("src.services.workspace_pipeline.emit_pipeline_complete", lambda **k: _record("complete", **k))

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
