from unittest.mock import AsyncMock, patch

import pytest

from src.services.keyword_clustering_service import KeywordClusteringService

# ============================================================================
# UNIT TESTS: KeywordClusteringService
# ============================================================================

@pytest.mark.asyncio
async def test_cluster_keywords_basic():
    """
    Test basic clustering logic with distinct semantic groups.
    """
    # 📝 Mock embeddings (Normalized unit vectors):
    # Group 1: Tech (Very close to [1, 0, 0])
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.98, 0.2, 0.0]  # Cosine distance ~0.02
    
    # Group 2: Car (Very close to [0, 1, 0])
    v3 = [0.0, 1.0, 0.0]
    v4 = [0.0, 0.98, 0.2]  # Cosine distance ~0.02
    
    # Group 3: Food (Orthogonal [0, 0, 1])
    v5 = [0.0, 0.0, 1.0]

    mock_embeddings = [v1, v2, v3, v4, v5]
    
    mock_model = AsyncMock()
    mock_model.aembed_documents.return_value = mock_embeddings
    
    # Since the service calls get_embedding() in __init__, we MUST instantiate it INSIDE the patch
    with patch("src.services.keyword_clustering_service.get_embedding", return_value=mock_model):
        service = KeywordClusteringService()
        keywords = [
            {"keyword": "apple", "score": 10},
            {"keyword": "iphone", "score": 40},
            {"keyword": "tesla", "score": 50},
            {"keyword": "car", "score": 30},
            {"keyword": "banana", "score": 5}
        ]
        
        clusters = await service.cluster_keywords(keywords)
        
        # 🔍 Assertions:
        # Should result in 3 distinct clusters:
        # 1. tesla (tesla/car) - total 80
        # 2. iphone (apple/iphone) - total 50
        # 3. banana - total 5
        assert len(clusters) == 3
        
        # Sorted by total score
        assert clusters[0]["cluster_name"] == "tesla"
        assert clusters[1]["cluster_name"] == "iphone"
        assert clusters[2]["cluster_name"] == "banana"
        
        # Check membership
        tesla_kws = [kw["keyword"] for kw in clusters[0]["keywords"]]
        assert "tesla" in tesla_kws
        assert "car" in tesla_kws
        assert len(tesla_kws) == 2

@pytest.mark.asyncio
async def test_cluster_keywords_empty():
    """
    Test handling of empty keyword lists.
    """
    service = KeywordClusteringService()
    clusters = await service.cluster_keywords([])
    assert clusters == []

@pytest.mark.asyncio
async def test_cluster_keywords_single():
    """
    Test handling of a single keyword.
    """
    service = KeywordClusteringService()
    keywords = [{"keyword": "standalone", "score": 100}]
    clusters = await service.cluster_keywords(keywords)
    
    assert len(clusters) == 1
    assert clusters[0]["cluster_name"] == "standalone"
    assert len(clusters[0]["keywords"]) == 1


@pytest.mark.asyncio
async def test_cluster_keywords_filters_intent_mismatch():
    """
    If a seed intent is provided, explicit mismatches are filtered out (unknowns are kept).
    """
    mock_model = AsyncMock()
    # Should not be called because filtering yields a single keyword.
    mock_model.aembed_documents.return_value = [[1.0, 0.0, 0.0]]

    with patch("src.services.keyword_clustering_service.get_embedding", return_value=mock_model):
        service = KeywordClusteringService()
        keywords = [
            {"keyword": "best seo tools", "score": 50},   # inferred commercial
            {"keyword": "buy seo tool", "score": 60},     # inferred transactional
        ]
        clusters = await service.cluster_keywords(keywords, seed_intent="transactional")

        assert len(clusters) == 1
        assert clusters[0]["cluster_name"] == "buy seo tool"


@pytest.mark.asyncio
async def test_cluster_keywords_filters_by_seed_similarity():
    """
    When seed_keyword is provided, keywords below min_seed_similarity are dropped.
    """
    mock_model = AsyncMock()

    async def _side_effect(texts):
        # Called once for seed (1 item) and once for docs (N items)
        if len(texts) == 1:
            return [[1.0, 0.0, 0.0]]  # seed
        # Two candidates: one close, one orthogonal
        return [[0.99, 0.0, 0.0], [0.0, 1.0, 0.0]]

    mock_model.aembed_documents.side_effect = _side_effect

    with patch("src.services.keyword_clustering_service.get_embedding", return_value=mock_model):
        service = KeywordClusteringService()
        keywords = [
            {"keyword": "apple iphone", "score": 100},
            {"keyword": "car insurance", "score": 90},
        ]

        clusters = await service.cluster_keywords(
            keywords, seed_keyword="iphone", seed_intent="commercial"
        )

        assert len(clusters) == 1
        assert clusters[0]["cluster_name"] == "apple iphone"
