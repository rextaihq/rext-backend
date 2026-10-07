"""Unit tests for BrandVoiceService."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from src.api.middleware.exceptions import RextAuthenticationException
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.schema.brand_voice_schema import BrandSchema
from src.services.brand_voice_service import BrandVoiceService


class FakeScalarSequence:
    """Helper to mimic SQLAlchemy scalar sequence results."""

    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


class FakeResult:
    """Helper to mimic SQLAlchemy Result objects."""

    def __init__(self, *, scalar=None, scalars=None, rows=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return FakeScalarSequence(self._scalars)

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_get_brand_voice_returns_record():
    """get_brand_voice should return existing brand voice after membership check."""
    mock_db = AsyncMock()
    mock_db.add = Mock()
    service = BrandVoiceService(mock_db)
    workspace_id = uuid4()
    user_id = uuid4()

    brand_voice = BrandVoice(
        workspace_id=workspace_id,
        about="Company description",
        customer_profile="Target customers",
        selling_position="Unique value prop",
        target_audience=["SaaS founders"],
        brand_voice=["Friendly", "Conversational"],
        competitors=["Competitor 1"],
        content_pillar=["Thought leadership"],
    )

    service._verify_workspace_membership = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=brand_voice)

    result = await service.get_brand_voice(workspace_id, user_id)

    assert result is brand_voice
    service._verify_workspace_membership.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_brand_voice_requires_membership():
    """Should raise authentication exception when membership check fails."""
    service = BrandVoiceService(db=AsyncMock())
    service._verify_workspace_membership = AsyncMock(
        side_effect=RextAuthenticationException("no access")
    )

    with pytest.raises(RextAuthenticationException):
        await service.get_brand_voice(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_upsert_brand_voice_creates_new_record():
    """upsert_brand_voice should create a new brand voice when none exists."""
    mock_db = AsyncMock()
    mock_db.add = Mock()
    service = BrandVoiceService(mock_db)
    workspace_id = uuid4()
    user_id = uuid4()

    service._verify_workspace_membership = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)

    payload = BrandSchema(
        about="Brand overview",
        customer_profile="Innovative marketers",
        selling_position="We deliver fast insights",
        target_audience=["Startups", "SMBs"],
        brand_voice=["Warm", "Storytelling"],
        competitors=["Competitor A"],
        content_pillar=["Education", "Enablement"],
    )

    brand_voice = await service.upsert_brand_voice(
        workspace_id=workspace_id,
        user_id=user_id,
        brand_data=payload,
    )

    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()
    assert brand_voice.workspace_id == workspace_id
    assert brand_voice.about == payload.about
    assert brand_voice.brand_voice == payload.brand_voice
    assert brand_voice.content_pillar == payload.content_pillar


@pytest.mark.asyncio
async def test_upsert_brand_voice_updates_existing_record():
    """Should update existing brand voice fields when record exists."""
    mock_db = AsyncMock()
    service = BrandVoiceService(mock_db)
    workspace_id = uuid4()
    user_id = uuid4()

    existing = BrandVoice(
        workspace_id=workspace_id,
        about="Existing about",
        customer_profile="Existing profile",
        selling_position="Legacy position",
        target_audience=["Agencies"],
        brand_voice=["Formal", "Precise"],
        competitors=["Incumbent"],
        content_pillar=["Case studies"],
    )

    service._verify_workspace_membership = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=existing)

    payload = BrandSchema(
        about="Updated about",
        customer_profile="Updated profile",
        selling_position="Updated position",
        target_audience=["Marketing teams"],
        brand_voice=["Friendly", "Conversational"],
        competitors=["New competitor"],
        content_pillar=["How-to", "Guides"],
    )

    updated = await service.upsert_brand_voice(
        workspace_id=workspace_id,
        user_id=user_id,
        brand_data=payload,
    )

    assert updated.about == payload.about
    assert updated.brand_voice == payload.brand_voice
    assert updated.content_pillar == payload.content_pillar
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_workspace_membership_raises_when_not_member():
    """_verify_workspace_membership should raise when membership missing."""
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)

    service = BrandVoiceService(mock_db)

    with pytest.raises(RextAuthenticationException):
        await service._verify_workspace_membership(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_delete_brand_voice_success():
    """delete_brand_voice should return True when record is deleted."""
    mock_db = AsyncMock()
    service = BrandVoiceService(mock_db)
    workspace_id = uuid4()
    user_id = uuid4()

    service._verify_workspace_membership = AsyncMock()

    # Mock delete result
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_db.execute.return_value = mock_result

    result = await service.delete_brand_voice(workspace_id, user_id)

    assert result is True
    service._verify_workspace_membership.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_brand_voice_not_found():
    """delete_brand_voice should return False when no record exists."""
    mock_db = AsyncMock()
    service = BrandVoiceService(mock_db)
    workspace_id = uuid4()
    user_id = uuid4()

    service._verify_workspace_membership = AsyncMock()

    # Mock delete result
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute.return_value = mock_result

    result = await service.delete_brand_voice(workspace_id, user_id)

    assert result is False
