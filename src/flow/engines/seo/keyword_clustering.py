import logging
from typing import Dict, Any

from src.flow.states.rext import REXT
from src.services.keyword_clustering_service import (
    KeywordClusteringService,
    resolve_primary_intent,
)
from src.services.keyword_service import KeywordExtractor

logger = logging.getLogger(__name__)


async def keyword_clustering_node(state: REXT) -> Dict[str, Any]:
    """
    LangGraph node for LLM-based, intent-aligned keyword clustering.

    Uses intent-matched SERP titles, PAA questions, and related topics
    (from competitor/intent analysis) plus TF-IDF keyword candidates to build
    Semrush/Ahrefs-style topic clusters.
    """
    serp_normalized = state.get("serp_normalized")
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})

    if not serp_normalized:
        logger.warning("No serp_normalized data found for clustering")
        return {"seo_result": seo_result}

    query = serp_normalized.get("query") or state.get("serp_payload", {}).get("query", "")
    primary_intent = resolve_primary_intent(
        seo_result=seo_result,
        serp_backlinks=serp_backlinks,
        serp_normalized=serp_normalized,
        final_intent_type=state.get("final_intent_type"),
    )
    intent_matched_signals = serp_normalized.get("intent_matched_signals") or {}

    logger.info(
        "Starting LLM keyword clustering for query=%r intent=%s",
        query,
        primary_intent,
    )

    extractor = KeywordExtractor()
    extracted = extractor.extract_keywords(serp_normalized, top_n=50)

    if not extracted:
        logger.warning("No keywords extracted for clustering")
        return {"seo_result": seo_result}

    service = KeywordClusteringService()
    clusters = await service.cluster_keywords(
        keywords_data=extracted,
        query=query,
        primary_intent=primary_intent,
        intent_matched_signals=intent_matched_signals,
    )

    return {
        "seo_result": {
            **seo_result,
            "keyword_clusters": clusters,
            "intent_type": primary_intent.upper()
            if primary_intent
            else seo_result.get("intent_type"),
        },
    }
