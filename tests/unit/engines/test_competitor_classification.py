from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.flow.engines.competitors.classification import classify_batch
from src.flow.engines.competitors.constants import (
    DIRECT_CONFIDENCE_THRESHOLD,
    MAX_DISPLAY_COMPETITORS,
    MIN_DISPLAY_COMPETITORS,
    OPENAI_MODEL,
)
from src.flow.engines.competitors.llm_client import call_openai_json, call_openai_json_array
from src.flow.engines.competitors.pipeline import select_display_competitors


def test_openai_model_is_gpt_4o_mini():
    """Verify that competitor discovery uses gpt-4o-mini for cost-effective extraction."""
    assert OPENAI_MODEL == "gpt-4o-mini"


def test_select_display_competitors_high_confidence_prioritized():
    """Confirms high-confidence competitors (>= 0.75) are returned when >= min_count exist."""
    competitors = [
        {"domain": "wp101.com", "confidence": 0.90, "is_competitor": True},
        {"domain": "wpshout.com", "confidence": 0.85, "is_competitor": True},
        {"domain": "wpexplorer.com", "confidence": 0.80, "is_competitor": True},
        {"domain": "sitepoint.com", "confidence": 0.78, "is_competitor": True},
        {"domain": "codeinwp.com", "confidence": 0.76, "is_competitor": True},
        {"domain": "lowconf1.com", "confidence": 0.60, "is_competitor": True},
        {"domain": "lowconf2.com", "confidence": 0.50, "is_competitor": True},
    ]

    result = select_display_competitors(competitors)
    domains = [c["domain"] for c in result]

    # Exactly 5 high-confidence items exist (>= MIN_DISPLAY_COMPETITORS=5); low confidence excluded
    assert domains == [
        "wp101.com",
        "wpshout.com",
        "wpexplorer.com",
        "sitepoint.com",
        "codeinwp.com",
    ]
    assert all(c["confidence"] >= DIRECT_CONFIDENCE_THRESHOLD for c in result)


def test_select_display_competitors_caps_at_max_display():
    """Confirms results are capped at MAX_DISPLAY_COMPETITORS (9)."""
    competitors = [
        {"domain": f"comp{i}.com", "confidence": 0.85, "is_competitor": True} for i in range(15)
    ]

    result = select_display_competitors(competitors)
    assert len(result) == MAX_DISPLAY_COMPETITORS


def test_select_display_competitors_pads_when_fewer_than_min():
    """Confirms padding with lower confidence entries up to MIN_DISPLAY_COMPETITORS (5)."""
    competitors = [
        {"domain": "high1.com", "confidence": 0.85, "is_competitor": True},
        {"domain": "low1.com", "confidence": 0.65, "is_competitor": True},
        {"domain": "low2.com", "confidence": 0.55, "is_competitor": True},
        {"domain": "low3.com", "confidence": 0.50, "is_competitor": True},
        {"domain": "low4.com", "confidence": 0.45, "is_competitor": True},
        {"domain": "low5.com", "confidence": 0.40, "is_competitor": True},
    ]

    result = select_display_competitors(competitors)
    # 1 high + 4 padded to reach min_count of 5
    assert len(result) == MIN_DISPLAY_COMPETITORS
    domains = [c["domain"] for c in result]
    assert domains == ["high1.com", "low1.com", "low2.com", "low3.com", "low4.com"]


@pytest.mark.asyncio
async def test_call_openai_json_parameters():
    """Verifies that call_openai_json calls OpenAI API with gpt-4o parameters."""
    with patch(
        "src.flow.engines.competitors.llm_client._client.chat.completions.create",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_resp = AsyncMock()
        mock_choice = AsyncMock()
        mock_choice.message.content = '{"result": "ok"}'
        mock_resp.choices = [mock_choice]
        mock_create.return_value = mock_resp

        res = await call_openai_json("Test prompt", max_tokens=512)
        assert res == {"result": "ok"}

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == OPENAI_MODEL
        assert call_kwargs["max_tokens"] == 512
        assert "reasoning_effort" not in call_kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_call_openai_json_array_parameters():
    """Verifies that call_openai_json_array calls OpenAI API with low-cost model parameters."""
    with patch(
        "src.flow.engines.competitors.llm_client._client.chat.completions.create",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_resp = AsyncMock()
        mock_choice = AsyncMock()
        mock_choice.message.content = '{"items": ["a", "b"]}'
        mock_resp.choices = [mock_choice]
        mock_create.return_value = mock_resp

        res = await call_openai_json_array("Test array prompt", max_tokens=512)
        assert res == ["a", "b"]

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == OPENAI_MODEL
        assert call_kwargs["max_tokens"] == 512
        assert "reasoning_effort" not in call_kwargs


@pytest.mark.asyncio
async def test_classify_batch_uses_max_tokens_1200():
    """Verifies that classify_batch uses max_tokens=1200 matching main branch."""
    with patch(
        "src.flow.engines.competitors.classification.call_openai_json", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = {
            "wp101.com": {
                "is_competitor": True,
                "confidence": 0.9,
                "reason": "Direct tutorial peer",
            },
            "yoast.com": {"is_competitor": False, "confidence": 0.0, "reason": "SEO plugin tool"},
        }

        summary = {"company_name": "WPBeginner", "category": "WordPress Tutorials"}
        result = await classify_batch(summary, ["wp101.com", "yoast.com"])

        mock_call.assert_awaited_once()
        _, kwargs = mock_call.call_args
        assert kwargs.get("max_tokens") == 1200
        assert result["wp101.com"]["is_competitor"] is True
        assert result["yoast.com"]["is_competitor"] is False


def test_is_same_brand_or_domain():
    """Verify that sibling TLDs, subdomains, and company-matching domains are flagged as self/same."""
    from src.flow.engines.competitors.domain_utils import is_same_brand_or_domain

    # Sibling TLDs of same brand
    assert is_same_brand_or_domain("revnix.net", "https://revnix.com") is True
    assert is_same_brand_or_domain("revnix.com", "https://revnix.net") is True
    assert is_same_brand_or_domain("revnix.io", "https://revnix.com") is True
    assert is_same_brand_or_domain("rext.com", "https://rext.ai") is True

    # Exact domain & subdomains
    assert is_same_brand_or_domain("revnix.net", "https://revnix.net") is True
    assert is_same_brand_or_domain("www.revnix.net", "https://revnix.net") is True
    assert is_same_brand_or_domain("app.revnix.net", "https://revnix.net") is True

    # Bare domain / SLD
    assert is_same_brand_or_domain("revnix.net", "revnix") is True

    # Company name match
    assert is_same_brand_or_domain("revnix.net", "", "Revnix") is True

    # Unrelated domains should not match
    assert is_same_brand_or_domain("sanity.io", "https://nextlyhq.com") is False
    assert is_same_brand_or_domain("wpbuffs.com", "https://wpaegis.com") is False
    assert is_same_brand_or_domain("tutsplus.com", "https://wpbeginner.com") is False


def test_select_display_competitors_filters_self_domain():
    """Verify select_display_competitors removes own domain and sibling domains."""
    competitors = [
        {"domain": "revnix.net", "confidence": 0.95, "is_competitor": True},
        {"domain": "fullscale.io", "confidence": 0.85, "is_competitor": True},
        {"domain": "azumo.com", "confidence": 0.80, "is_competitor": True},
        {"domain": "ramotion.com", "confidence": 0.78, "is_competitor": True},
        {"domain": "folderit.net", "confidence": 0.76, "is_competitor": True},
        {"domain": "coherentsolutions.com", "confidence": 0.75, "is_competitor": True},
    ]

    result = select_display_competitors(competitors, self_url="https://revnix.com")
    domains = [c["domain"] for c in result]

    assert "revnix.net" not in domains
    assert domains == [
        "fullscale.io",
        "azumo.com",
        "ramotion.com",
        "folderit.net",
        "coherentsolutions.com",
    ]
