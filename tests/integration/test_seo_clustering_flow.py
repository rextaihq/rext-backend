from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.flow.engines.content.content_engine import create_content_engine
from src.flow.engines.seo.keyword_clustering import keyword_clustering_node
from src.flow.model.structure.keyword_clustering import (
    ClusterKeywordItem,
    KeywordClusterGroup,
    KeywordClusteringLLMOutput,
)


@pytest.mark.asyncio
async def test_seo_engine_clustering_node_integration():
    mock_keywords = [
        {"keyword": "seo tool", "score": 90},
        {"keyword": "best seo software", "score": 85},
        {"keyword": "cheap backlinks", "score": 60},
        {"keyword": "buy high da backlinks", "score": 65},
    ]

    llm_output = KeywordClusteringLLMOutput(
        clusters=[
            KeywordClusterGroup(
                cluster_name="seo tool",
                topic_theme="tools",
                intent="COMMERCIAL",
                keywords=[
                    ClusterKeywordItem(keyword="seo tool", relevance_score=90),
                    ClusterKeywordItem(keyword="best seo software", relevance_score=85),
                ],
                rationale="Tool comparison cluster",
            ),
            KeywordClusterGroup(
                cluster_name="buy high da backlinks",
                topic_theme="backlinks",
                intent="COMMERCIAL",
                keywords=[
                    ClusterKeywordItem(keyword="cheap backlinks", relevance_score=60),
                    ClusterKeywordItem(keyword="buy high da backlinks", relevance_score=65),
                ],
                rationale="Link building cluster",
            ),
        ]
    )

    mock_extractor = MagicMock()
    mock_extractor.extract_keywords.return_value = mock_keywords

    mock_model = AsyncMock()
    mock_model.ainvoke.return_value = llm_output

    with patch(
        "src.flow.engines.seo.keyword_clustering.KeywordExtractor",
        return_value=mock_extractor,
    ), patch(
        "src.services.keyword_clustering_service.load_model"
    ) as mock_load:
        mock_load.return_value.with_structured_output.return_value = mock_model

        state = {
            "serp_normalized": {
                "query": "SaaS SEO",
                "normalize_results": [{"title": "Best SEO Tools"}],
                "intent_matched_signals": {
                    "primary_intent": "COMMERCIAL",
                    "titles": ["Best SEO Tools for SaaS"],
                    "questions": ["What is SaaS SEO?"],
                    "related_topics": ["saas seo strategy"],
                },
            },
            "seo_result": {
                "existing_data": "preserved",
                "serp_backlinks": {"main_intent": "commercial"},
                "intent_type": "COMMERCIAL",
            },
        }

        result = await keyword_clustering_node(state)

    seo_data = result["seo_result"]
    assert seo_data["existing_data"] == "preserved"
    assert "keyword_clusters" in seo_data
    clusters = seo_data["keyword_clusters"]
    assert len(clusters) == 1
    assert clusters[0]["cluster_name"] == "seo tool"
    assert len(clusters[0]["keywords"]) == 2
    assert all("backlink" not in item["keyword"] for item in clusters[0]["keywords"])


@pytest.mark.asyncio
async def test_content_engine_graph_compilation_includes_clustering():
    engine = create_content_engine()
    assert engine is not None
    assert "keyword_clustering" in engine.nodes
