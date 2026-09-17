from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.server import app
from src.api.tool.schema.schema import TitleTag
from src.api.tool.tools import generate_title_tags

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Pydantic Model Validation Tests
# ---------------------------------------------------------------------------


def test_title_tag_validation_valid_bounds():
    # 50 characters exact
    t50 = "A" * 50
    tag50 = TitleTag(title=t50)
    assert tag50.title == t50
    assert 50 <= len(tag50.title.strip()) <= 60

    # 60 characters exact (hard maximum)
    t60 = "B" * 60
    tag60 = TitleTag(title=t60)
    assert tag60.title == t60
    assert 50 <= len(tag60.title.strip()) <= 60

    # 54 characters with spaces and punctuation
    t54 = "10 Best SEO Title Tag Tips for 2026 | Brand Name Tech!"
    assert len(t54) == 54
    tag54 = TitleTag(title=t54)
    assert tag54.title == t54
    assert 50 <= len(tag54.title.strip()) <= 60


def test_title_tag_validation_invalid_bounds():
    # 49 characters (too short)
    t49 = "C" * 49
    with pytest.raises((ValidationError, ValueError)):
        TitleTag(title=t49)

    # 61 characters (exceeds maximum)
    t61 = "D" * 61
    with pytest.raises((ValidationError, ValueError)):
        TitleTag(title=t61)


def test_title_tag_validation_whitespace_handling():
    raw_title = "   " + ("E" * 52) + "   "
    tag = TitleTag(title=raw_title)
    assert tag.title == "E" * 52
    assert 50 <= len(tag.title) <= 60


# ---------------------------------------------------------------------------
# 2. Generator Function Tests with LLM Mocking & Rejections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_title_tags_normal_keyword():
    mock_llm_response = MagicMock()
    mock_llm_response.content = """
1. 7 Best SEO Tools for 2026 Strategy | BrandName Tech
2. Ultimate SEO Tools Guide for Growth | BrandName Tech
3. How to Choose Top SEO Tools Today | BrandName Tech
4. Latest 2026 SEO Tools Comparison | BrandName Tech!
5. Premier SEO Tools Solutions Hub | BrandName Tech Inc
"""
    with patch("src.api.tool.tools._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_get_model.return_value = mock_model

        titles = await generate_title_tags(
            keyword="SEO Tools",
            topic="Best SEO Software",
            brand="BrandName Tech",
            tone="Professional",
        )

        assert len(titles) == 5
        for t in titles:
            assert 50 <= len(t.strip()) <= 60


@pytest.mark.asyncio
async def test_generate_title_tags_long_keyword():
    keyword = "enterprise cloud data migration strategies"
    mock_llm_response = MagicMock()
    mock_llm_response.content = """
- Enterprise Cloud Data Migration Strategies | Acme Cloud
- Ultimate Enterprise Cloud Data Migration | Acme Cloud
- Best Enterprise Cloud Data Migration Tips | Acme Cloud
- 2026 Enterprise Cloud Data Migration | Acme Cloud Tech
- Key Enterprise Cloud Data Migration Rules | Acme Cloud
"""
    with patch("src.api.tool.tools._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_get_model.return_value = mock_model

        titles = await generate_title_tags(
            keyword=keyword, topic="Cloud Migration", brand="Acme Cloud", tone="Authoritative"
        )

        assert len(titles) == 5
        for t in titles:
            assert 50 <= len(t.strip()) <= 60


@pytest.mark.asyncio
async def test_generate_title_tags_long_brand_name():
    brand = "Global Enterprise Technology Solutions Inc"
    mock_llm_response = MagicMock()
    mock_llm_response.content = """
1. Top SEO Tips | Global Enterprise Technology Solutions Inc
2. Rank #1 Guide | Global Enterprise Technology Solutions Inc
3. Best SEO 2026 | Global Enterprise Technology Solutions Inc
4. Complete SEO | Global Enterprise Technology Solutions Inc
5. Effective SEO | Global Enterprise Technology Solutions Inc
"""
    with patch("src.api.tool.tools._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_get_model.return_value = mock_model

        titles = await generate_title_tags(
            keyword="SEO Tips", topic="SEO Tips", brand=brand, tone="Informative"
        )

        assert len(titles) == 5
        for t in titles:
            assert 50 <= len(t.strip()) <= 60


@pytest.mark.asyncio
async def test_generate_title_tags_revision_flow_on_invalid_length():
    # Initial response contains invalid titles (too short and too long) along with valid ones
    initial_response = MagicMock()
    initial_response.content = """
1. Short Title | Brand
2. 7 Best SEO Tools for 2026 Strategy | BrandName Tech
3. This title is way too long and definitely exceeds the sixty character maximum limit allowed!
4. Ultimate SEO Tools Guide for Growth | BrandName Tech
"""

    revision_response = MagicMock()
    revision_response.content = """
1. How to Choose Top SEO Tools Today | BrandName Tech
2. Latest 2026 SEO Tools Comparison | BrandName Tech!
3. Premier SEO Tools Solutions Hub | BrandName Tech Inc
"""

    with patch("src.api.tool.tools._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=[initial_response, revision_response])
        mock_get_model.return_value = mock_model

        titles = await generate_title_tags(
            keyword="SEO Tools", topic="SEO Tools", brand="BrandName Tech", tone="Professional"
        )

        assert len(titles) == 5
        # Verify invalid titles were NOT included
        assert not any("Short Title" in t for t in titles)
        assert not any("way too long" in t for t in titles)
        # Verify all 5 titles are valid
        for t in titles:
            assert 50 <= len(t.strip()) <= 60


# ---------------------------------------------------------------------------
# 3. API Route Test
# ---------------------------------------------------------------------------


def test_title_tags_route_endpoint():
    mock_llm_response = MagicMock()
    mock_llm_response.content = """
1. 7 Best SEO Tools for 2026 Strategy | BrandName Tech
2. Ultimate SEO Tools Guide for Growth | BrandName Tech
3. How to Choose Top SEO Tools Today | BrandName Tech
4. Latest 2026 SEO Tools Comparison | BrandName Tech!
5. Premier SEO Tools Solutions Hub | BrandName Tech Inc
"""
    with patch("src.api.tool.tools._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_get_model.return_value = mock_model

        response = client.post(
            "/api/v1/tools/title-tags",
            json={
                "keyword": "SEO Tools",
                "topic": "Best SEO Software",
                "brand": "BrandName Tech",
                "tone": "Professional",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        titles = data["data"]["titles"]
        assert len(titles) == 5
        for t in titles:
            assert 50 <= len(t.strip()) <= 60
