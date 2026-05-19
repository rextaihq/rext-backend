import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.keyword_clustering_service import (
    KeywordClusteringService,
    resolve_primary_intent,
)
from src.flow.model.structure.keyword_clustering import (
    KeywordClusteringLLMOutput,
    KeywordClusterGroup,
    ClusterKeywordItem,
)


@pytest.mark.parametrize(
    "dataforseo_intent,seo_intent,final_intent,expected",
    [
        ("commercial", "informational", "transactional", "transactional"),
        ("commercial", "informational", "", "informational"),
        ("unknown", "unknown", "NAVIGATIONAL", "navigational"),
        ("", "", "", "informational"),
    ],
)
def test_resolve_primary_intent_ignores_dataforseo(
    dataforseo_intent, seo_intent, final_intent, expected
):
    """DataForSEO main_intent must not override competitor LLM intent."""
    result = resolve_primary_intent(
        seo_result={"intent_type": seo_intent},
        serp_backlinks={"main_intent": dataforseo_intent},
        final_intent_type=final_intent,
    )
    assert result == expected


@pytest.mark.asyncio
async def test_cluster_keywords_llm_groups():
    llm_output = KeywordClusteringLLMOutput(
        clusters=[
            KeywordClusterGroup(
                cluster_name="seo tool",
                topic_theme="software tools",
                intent="COMMERCIAL",
                keywords=[
                    ClusterKeywordItem(keyword="seo tool", relevance_score=95),
                    ClusterKeywordItem(keyword="best seo software", relevance_score=88),
                ],
                rationale="Same commercial comparison SERP",
            ),
            KeywordClusterGroup(
                cluster_name="buy backlinks",
                topic_theme="link building",
                intent="COMMERCIAL",
                keywords=[
                    ClusterKeywordItem(keyword="buy high da backlinks", relevance_score=80),
                ],
                rationale="Transactional purchase intent subgroup",
            ),
        ]
    )

    mock_model = AsyncMock()
    mock_model.ainvoke.return_value = llm_output

    keywords = [
        {"keyword": "seo tool", "score": 90},
        {"keyword": "best seo software", "score": 85},
        {"keyword": "buy high da backlinks", "score": 65},
    ]

    with patch("src.services.keyword_clustering_service.load_model") as mock_load:
        mock_load.return_value.with_structured_output.return_value = mock_model
        service = KeywordClusteringService()
        clusters = await service.cluster_keywords(
            keywords,
            query="best seo tools",
            primary_intent="commercial",
            intent_matched_signals={
                "primary_intent": "COMMERCIAL",
                "titles": ["10 Best SEO Tools in 2026"],
                "questions": ["What is the best SEO tool?"],
                "related_topics": [],
            },
        )

    assert len(clusters) == 2
    assert clusters[0]["cluster_name"] == "seo tool"
    assert clusters[0]["main_intent"] == "commercial"
    assert len(clusters[0]["keywords"]) == 2
    assert clusters[0]["topic_theme"] == "software tools"


@pytest.mark.asyncio
async def test_cluster_keywords_empty():
    service = KeywordClusteringService()
    clusters = await service.cluster_keywords([], query="test", primary_intent="informational")
    assert clusters == []


@pytest.mark.asyncio
async def test_cluster_keywords_single():
    service = KeywordClusteringService()
    keywords = [{"keyword": "standalone", "score": 100}]
    clusters = await service.cluster_keywords(
        keywords, query="standalone", primary_intent="informational"
    )
    assert len(clusters) == 1
    assert clusters[0]["cluster_name"] == "standalone"


@pytest.mark.asyncio
async def test_cluster_keywords_llm_fallback():
    mock_model = AsyncMock()
    mock_model.ainvoke.side_effect = RuntimeError("LLM unavailable")

    keywords = [
        {"keyword": "alpha", "score": 50},
        {"keyword": "beta", "score": 30},
    ]

    with patch("src.services.keyword_clustering_service.load_model") as mock_load:
        mock_load.return_value.with_structured_output.return_value = mock_model
        service = KeywordClusteringService()
        clusters = await service.cluster_keywords(
            keywords, query="alpha", primary_intent="informational"
        )

    assert len(clusters) == 1
    assert clusters[0]["cluster_name"] == "alpha"
    assert "Fallback" in clusters[0]["rationale"]
