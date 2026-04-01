import pytest
from unittest.mock import AsyncMock, patch
from src.flow.engines.seo.seo_engine import create_seo_engine
from src.flow.engines.seo.keyword_clustering import keyword_clustering_node

# ============================================================================
# INTEGRATION TESTS: SEO Engine Clustering Flow
# ============================================================================

@pytest.mark.asyncio
async def test_seo_engine_clustering_node_integration():
    """
    Test the keyword_clustering_node specifically within the REXT state context.
    Ensures input from KeywordExtractor is correctly handled by ClusteringService 
    and results are merged into the state.
    """
    # 🧩 Mock keywords to be returned by Extractor
    mock_keywords = [
        {"keyword": "seo tool", "score": 90, "intent": "commercial"},
        {"keyword": "best seo software", "score": 85, "intent": "commercial"},
        {"keyword": "cheap backlinks", "score": 60, "intent": "transactional"},
        {"keyword": "buy high da backlinks", "score": 65, "intent": "transactional"},
    ]
    
    # 📝 Mock embeddings: 2 clearly distinct groups
    mock_embeddings = [
        [1.0, 0.0, 0.0], [0.99, 0.0, 0.0],  # group 1 (tools)
        [0.0, 1.0, 0.0], [0.0, 0.99, 0.0]   # group 2 (backlinks)
    ]
    
    from unittest.mock import MagicMock
    mock_extractor = MagicMock()
    mock_extractor.extract_keywords.return_value = mock_keywords
    
    mock_emb_model = AsyncMock()
    mock_emb_model.aembed_documents.return_value = mock_embeddings
    
    # Patch everything together
    with patch("src.flow.engines.seo.keyword_clustering.KeywordExtractor", return_value=mock_extractor), \
         patch("src.services.keyword_clustering_service.get_embedding", return_value=mock_emb_model):
        
        # 🚀 Initial state
        state = {
            "original_query": "SaaS SEO",
            "serp_normalized": {
                "results": [{"title": "Competitor 1", "snippet": "Keyword analysis"}]
            },
            "seo_result": {"existing_data": "preserved"}
        }
        
        # 🏃 Execute node
        result = await keyword_clustering_node(state)
        
        # 🔍 Assertions:
        assert "seo_result" in result
        seo_data = result["seo_result"]
        
        # 1. Check data preservation (merging)
        assert seo_data["existing_data"] == "preserved"
        
        # 2. Check cluster presence
        assert "keyword_clusters" in seo_data
        clusters = seo_data["keyword_clusters"]
        
        # 3. Check clustering logic (expected 2 semantic groups)
        assert len(clusters) == 2
        
        # 4. Check sorting (total score 175 vs 125)
        # 175 (tools) should be first
        assert clusters[0]["cluster_name"] == "seo tool"
        assert clusters[0]["total_score"] == 175.0
        assert len(clusters[0]["keywords"]) == 2
        
        # 125 (backlinks) should be second
        assert clusters[1]["cluster_name"] == "buy high da backlinks"
        assert clusters[1]["total_score"] == 125.0
        assert len(clusters[1]["keywords"]) == 2

@pytest.mark.asyncio
async def test_seo_engine_graph_compilation():
    """
    Lightweight test to ensure the SEO engine can be compiled without syntax 
    errors after the node was added.
    """
    try:
        engine = create_seo_engine()
        assert engine is not None
        # Check if the node is in the graph
        assert "keyword_clustering" in engine.nodes
    except Exception as e:
        pytest.fail(f"Failed to compile SEO engine: {e}")
