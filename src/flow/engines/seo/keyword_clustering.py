import logging
from typing import Dict, Any

from src.flow.states.rext import REXT
from src.services.keyword_clustering_service import (
    KeywordClusteringService,
    resolve_primary_intent,
)
from src.services.keyword_service import KeywordExtractor

logger = logging.getLogger(__name__)

_TOP_N_KEYWORDS = 30


async def keyword_clustering_node(state: REXT) -> Dict[str, Any]:
    """
    LLM keyword clustering grounded in competitor-derived intent.

    - Primary intent: competitor batch LLM only (not DataForSEO).
    - TF-IDF corpus: titles/snippets from intent-matched competitors.
    - Clustering LLM: candidates + intent-matched competitor context.
    """
    serp_normalized = state.get("serp_normalized")
    seo_result = state.get("seo_result", {})

    if not serp_normalized:
        logger.warning("No serp_normalized data found for clustering")
        return {"seo_result": seo_result}

    query = serp_normalized.get("query") or state.get("serp_payload", {}).get("query", "")
    intent_matched_signals = serp_normalized.get("intent_matched_signals") or {}

    primary_intent = resolve_primary_intent(
        seo_result=seo_result,
        serp_normalized=serp_normalized,
        final_intent_type=state.get("final_intent_type"),
    )

    logger.info(
        "Starting LLM keyword clustering for query=%r intent=%s (competitor LLM)",
        query,
        primary_intent,
    )

    matched_domains = set(intent_matched_signals.get("matched_domains") or [])
    matched_titles = intent_matched_signals.get("titles") or []

    clustering_serp = {
        **serp_normalized,
        "related_topics": intent_matched_signals.get("related_topics")
        or serp_normalized.get("related_topics", []),
        "questions": intent_matched_signals.get("questions")
        or serp_normalized.get("questions", []),
    }

    extractor = KeywordExtractor()
    extracted = extractor.extract_keywords(
        clustering_serp,
        top_n=_TOP_N_KEYWORDS,
        intent_matched_titles=matched_titles or None,
        intent_matched_domains=list(matched_domains) if matched_domains else None,
    )

    if not extracted:
        logger.warning("No keywords extracted for clustering")
        return {"seo_result": seo_result}

    content_state = state.get("content", {})
    content_type = content_state.get("content_type", "blog")
    selected_topic = content_state.get("selected_topic") or state.get("selected_topic") or query

    service = KeywordClusteringService()
    clusters = await service.cluster_keywords(
        keywords_data=extracted,
        query=query,
        primary_intent=primary_intent,
        intent_matched_signals=intent_matched_signals,
        content_type=content_type,
        selected_topic=selected_topic,
    )

    return {
        "seo_result": {
            **seo_result,
            "keyword_clusters": clusters,
            "intent_type": primary_intent.upper(),
        },
    }
