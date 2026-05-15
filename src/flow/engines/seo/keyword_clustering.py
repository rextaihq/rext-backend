import logging
from typing import Any, Dict

from src.flow.states.countries import ISO_TO_COUNTRY, VALID_COUNTRY_CODES
from src.flow.states.rext import REXT
from src.services.keyword_clustering_service import (
    KeywordClusteringConfig,
    KeywordClusteringService,
)
from src.services.keyword_service import KeywordExtractor

logger = logging.getLogger(__name__)


def _resolve_location_name(raw_country: str | None) -> str:
    if not raw_country or raw_country.lower() == "global":
        return "United States"

    country = ISO_TO_COUNTRY.get(raw_country.lower(), raw_country)
    if country not in VALID_COUNTRY_CODES:
        logger.warning(
            "Keyword clustering country '%s' is not supported; defaulting to United States",
            raw_country,
        )
        return "United States"
    return country


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def keyword_clustering_node(state: REXT) -> Dict[str, Any]:
    """
    LangGraph node for semantic keyword clustering.
    
    This node extracts a broad list of keyword candidates from the SERP data
    and groups them into semantic clusters using vector embeddings.
    """
    
    serp_normalized = state.get("serp_normalized")
    serp_result = state.get("serp_result", {})
    seo_result = state.get("seo_result", {})
    serp_payload = state.get("serp_payload", {}) or {}
    
    if not serp_normalized:
        logger.warning("No serp_normalized data found for clustering")
        return {"seo_result": seo_result}
    
    logger.info("Starting keyword clustering analysis")

    seed_keyword = serp_normalized.get("query") or serp_payload.get("query")

    # Seed intent: user-selected intent > SEO engine intent_type > DataForSEO intent
    seed_intent = (
        (seo_result.get("intent_type") or "").strip()
        or ((seo_result.get("serp_backlinks") or {}).get("main_intent") or "").strip()
        or "unknown"
    )
    
    # 1. Extract raw keyword candidates from SERP data
    # Increase top_n to 50/100 to have a rich set to cluster
    extractor = KeywordExtractor()
    extracted = extractor.extract_keywords(serp_normalized, top_n=50)
    
    if not extracted:
        logger.warning("No keywords extracted for clustering")
        return {"seo_result": seo_result}
        
    # 2. Perform Semantic Clustering
    # Preferred: HDBSCAN with semantic similarity matrix, with validation + fallbacks.
    payload_cfg = (
        serp_payload.get("keyword_clustering_config", {})
        if isinstance(serp_payload, dict)
        else {}
    )
    seo_cfg = (
        seo_result.get("keyword_clustering_config", {}) if isinstance(seo_result, dict) else {}
    )
    cfg_overrides = {**seo_cfg, **payload_cfg}

    defaults = KeywordClusteringConfig()
    search_params = serp_result.get("search_params", {}) if isinstance(serp_result, dict) else {}
    location_code = _to_int(
        _first_present(
            cfg_overrides.get("location_code"),
            serp_payload.get("location_code"),
            search_params.get("location_code"),
        )
    )
    raw_location_name = _first_present(
        cfg_overrides.get("location_name"),
        serp_payload.get("location_name"),
        serp_payload.get("country"),
        search_params.get("location_name"),
    )
    location_name = None if location_code is not None else _resolve_location_name(raw_location_name)
    language_code = _first_present(
        cfg_overrides.get("language_code"),
        serp_payload.get("language_code"),
        search_params.get("language_code"),
        "en",
    )
    language_name = _first_present(
        cfg_overrides.get("language_name"),
        serp_payload.get("language_name"),
        search_params.get("language_name"),
    )
    config = KeywordClusteringConfig(
        min_seed_similarity=float(
            cfg_overrides.get("min_seed_similarity", defaults.min_seed_similarity)
        ),
        min_cluster_size=int(cfg_overrides.get("min_cluster_size", defaults.min_cluster_size)),
        min_search_volume=int(cfg_overrides.get("min_search_volume", defaults.min_search_volume)),
        max_keyword_difficulty=int(
            cfg_overrides.get("max_keyword_difficulty", defaults.max_keyword_difficulty)
        ),
        require_metrics=bool(cfg_overrides.get("require_metrics", defaults.require_metrics)),
        enable_dataforseo_metrics=bool(
            cfg_overrides.get(
                "enable_dataforseo_metrics", defaults.enable_dataforseo_metrics
            )
        ),
        location_name=str(location_name) if location_name else None,
        location_code=location_code,
        language_code=str(language_code).lower() if language_code else None,
        language_name=str(language_name) if language_name else None,
    )
    service = KeywordClusteringService(config=config)
    clusters = await service.cluster_keywords(
        extracted, seed_keyword=seed_keyword, seed_intent=seed_intent
    )
    
    # 3. Update state with clusters
    return {
        "seo_result": {
            **seo_result,
            "keyword_clusters": clusters
        }
    }
