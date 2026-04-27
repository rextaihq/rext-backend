import logging
from typing import Dict, Any
from src.flow.states.rext import REXT
from src.services.keyword_clustering_service import KeywordClusteringService
from src.services.keyword_service import KeywordExtractor

logger = logging.getLogger(__name__)

async def keyword_clustering_node(state: REXT) -> Dict[str, Any]:
    """
    LangGraph node for semantic keyword clustering.
    
    This node extracts a broad list of keyword candidates from the SERP data
    and groups them into semantic clusters using vector embeddings.
    """
    
    serp_normalized = state.get("serp_normalized")
    seo_result = state.get("seo_result", {})
    
    if not serp_normalized:
        logger.warning("No serp_normalized data found for clustering")
        return {"seo_result": seo_result}
    
    logger.info("Starting keyword clustering analysis")
    
    # 1. Extract raw keyword candidates from SERP data
    # Increase top_n to 50/100 to have a rich set to cluster
    extractor = KeywordExtractor()
    extracted = extractor.extract_keywords(serp_normalized, top_n=50)
    
    if not extracted:
        logger.warning("No keywords extracted for clustering")
        return {"seo_result": seo_result}
        
    # 2. Perform Semantic Clustering
    # This uses OpenAI embeddings and Agglomerative Clustering
    service = KeywordClusteringService()
    clusters = await service.cluster_keywords(extracted)
    
    # 3. Update state with clusters
    return {
        "seo_result": {
            **seo_result,
            "keyword_clusters": clusters
        }
    }
