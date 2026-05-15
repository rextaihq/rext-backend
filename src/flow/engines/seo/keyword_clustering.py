"""
keyword_clustering_node — LangGraph node for intent-aware keyword clustering.

Full pipeline (per specification):
  1.  Extract seed keyword from serp_normalized / serp_payload / serp_result.
  2.  Determine seed intent:
        primary  → seo_result["intent_type"]  (user-confirmed or SEO engine)
        secondary→ seo_result["serp_backlinks"]["main_intent"]  (DataForSEO)
        fallback → heuristic inference from the seed keyword text itself.
  3.  Score every competitor in serp_normalized["normalize_results"] for
        intent match using their title + snippet text.
  4.  Keep only competitors whose inferred intent matches the seed intent
        (with a configurable min_match_ratio threshold so we never discard
         everything if SERP is heterogeneous).
  5.  Extract keywords via TF-IDF exclusively from the intent-matched
        competitor corpus (titles, snippets, related_topics, questions).
  6.  Hand the extracted keywords to KeywordClusteringService which runs:
        Embeddings → Cosine Similarity Matrix → Seed-similarity threshold →
        HDBSCAN → Cluster Validation (noise ratio + silhouette) →
        Agglomerative fallback → Final KeywordCluster list.

KD and search_volume are NOT used anywhere inside this pipeline.
"""

import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import sentry_sdk  # noqa: F401 — imported for side-effects (init)
from sentry_sdk import capture_exception, capture_message, push_scope

from src.flow.states.countries import ISO_TO_COUNTRY, VALID_COUNTRY_CODES
from src.flow.states.rext import REXT
from src.services.keyword_clustering_service import (
    KeywordClusteringConfig,
    KeywordClusteringService,
    infer_intent_from_text,
    _normalize_intent,
)
from src.services.keyword_service import KeywordExtractor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

# If fewer than this fraction of SERP competitors match the seed intent we
# relax the filter and use all competitors rather than starving the corpus.
_MIN_INTENT_MATCH_RATIO: float = 0.25

# Minimum number of intent-matched competitors before we trust the filtered
# set; below this we fall back to using all competitors.
_MIN_INTENT_MATCH_COUNT: int = 2


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

class _NumpyEncoder(json.JSONEncoder):
    """Handles numpy scalar / array types in json.dumps."""

    def default(self, obj: Any) -> Any:
        try:
            import numpy as np  # type: ignore

            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, np.bool_):
                return bool(obj)
        except ImportError:
            pass
        return super().default(obj)


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _resolve_location_name(raw_country: Optional[str]) -> str:
    if not raw_country or raw_country.lower() == "global":
        return "United States"
    country = ISO_TO_COUNTRY.get(raw_country.lower(), raw_country)
    if country not in VALID_COUNTRY_CODES:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_context(
                "country_validation",
                {"raw_country": raw_country, "resolved_country": country},
            )
            capture_message(
                f"keyword_clustering: country '{raw_country}' not supported; "
                "defaulting to United States",
                level="warning",
            )
        return "United States"
    return country


def _first_present(*values: Any) -> Any:
    for v in values:
        if v is not None and v != "":
            return v
    return None


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sanitize_filename(value: str) -> str:
    sanitized = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in (value or "").strip()
    )
    return sanitized[:100] if sanitized else "seed"


# ---------------------------------------------------------------------------
# SERP guard
# ---------------------------------------------------------------------------

def _serp_normalized_has_content(serp_normalized: Any) -> bool:
    """
    Returns True only when serp_normalized is a non-empty dict containing at
    least one usable SERP content field.
    """
    if not isinstance(serp_normalized, dict):
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_context(
                "type_error",
                {"expected": "dict", "got": type(serp_normalized).__name__},
            )
            capture_message(
                f"keyword_clustering: serp_normalized is not a dict "
                f"(got {type(serp_normalized).__name__}); skipping",
                level="warning",
            )
        return False

    if not serp_normalized:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            capture_message(
                "keyword_clustering: serp_normalized is empty {}; "
                "SERP engine may not have run yet — skipping",
                level="warning",
            )
        return False

    has_results = bool(serp_normalized.get("normalize_results"))
    has_query = bool(serp_normalized.get("query"))
    has_topics = bool(serp_normalized.get("related_topics"))
    has_questions = bool(serp_normalized.get("questions"))

    if not any([has_results, has_query, has_topics, has_questions]):
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_context(
                "field_status",
                {
                    "results_count": len(serp_normalized.get("normalize_results") or []),
                    "query_present": has_query,
                    "topics_count": len(serp_normalized.get("related_topics") or []),
                    "questions_count": len(serp_normalized.get("questions") or []),
                },
            )
            capture_message(
                "keyword_clustering: serp_normalized present but all fields empty",
                level="warning",
            )
        return False

    return True


# ---------------------------------------------------------------------------
# Competitor intent filtering
# ---------------------------------------------------------------------------

def _filter_competitors_by_intent(
    normalize_results: List[Dict[str, Any]],
    seed_intent: str,
) -> List[Dict[str, Any]]:
    """
    Score each SERP competitor by inferred intent (title + snippet text).
    Return only those whose intent matches the seed intent.

    Falls back to returning ALL competitors if:
      - seed_intent is "unknown"          (no reliable filter anchor)
      - match count is below threshold    (corpus would be too thin)
    """
    if not normalize_results:
        return []

    if seed_intent == "unknown":
        logger.info(
            "_filter_competitors_by_intent: seed intent is 'unknown' — "
            "using all %d competitors",
            len(normalize_results),
        )
        return normalize_results

    matched: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []

    for result in normalize_results:
        title = result.get("title") or ""
        snippet = result.get("snippet") or ""
        combined_text = f"{title} {snippet}"
        competitor_intent = infer_intent_from_text(combined_text)

        result_copy = dict(result)
        result_copy["_inferred_intent"] = competitor_intent
        result_copy["_intent_match"] = (
            competitor_intent == "unknown" or competitor_intent == seed_intent
        )

        if result_copy["_intent_match"]:
            matched.append(result_copy)
        else:
            unmatched.append(result_copy)

    total = len(normalize_results)
    match_ratio = len(matched) / total if total else 0.0

    logger.info(
        "_filter_competitors_by_intent: seed_intent=%r matched=%d/%d (%.0f%%)",
        seed_intent,
        len(matched),
        total,
        match_ratio * 100,
    )

    # If the match set is too small, return all competitors to avoid corpus starvation
    if len(matched) < _MIN_INTENT_MATCH_COUNT or match_ratio < _MIN_INTENT_MATCH_RATIO:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_context(
                "intent_filter_fallback",
                {
                    "seed_intent": seed_intent,
                    "matched": len(matched),
                    "total": total,
                    "match_ratio": round(match_ratio, 3),
                    "threshold_count": _MIN_INTENT_MATCH_COUNT,
                    "threshold_ratio": _MIN_INTENT_MATCH_RATIO,
                },
            )
            capture_message(
                "keyword_clustering: intent filter match too low "
                f"({len(matched)}/{total}) — using all competitors",
                level="warning",
            )
        return normalize_results

    return matched


# ---------------------------------------------------------------------------
# Debug persistence
# ---------------------------------------------------------------------------

def _persist_keyword_clusters(clusters: Any, seed_keyword: Optional[str]) -> None:
    """Write cluster results to a JSON file for debugging / audit."""
    output_dir = Path(
        os.getenv("KEYWORD_CLUSTER_OUTPUT_DIR", "/tmp/keyword_clusters")
    )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        seed_part = _sanitize_filename(seed_keyword or "seed")
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        file_path = output_dir / f"keyword_clusters_{seed_part}_{timestamp}.json"
        file_path.write_text(
            json.dumps(
                {
                    "seed_keyword": seed_keyword,
                    "cluster_count": len(clusters) if clusters else 0,
                    "keyword_clusters": clusters,
                },
                ensure_ascii=False,
                indent=2,
                cls=_NumpyEncoder,
            ),
            encoding="utf-8",
        )
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_context(
                "persistence_result",
                {
                    "cluster_count": len(clusters) if clusters else 0,
                    "file_path": str(file_path),
                    "seed_keyword": seed_keyword,
                },
            )
            capture_message(
                f"keyword_clustering: persisted {len(clusters) if clusters else 0} "
                f"cluster(s) to {file_path}",
                level="info",
            )
    except Exception as e:  # noqa: BLE001
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_context(
                "persistence",
                {
                    "output_dir": str(output_dir),
                    "seed_keyword": seed_keyword,
                    "traceback": traceback.format_exc(),
                },
            )
            capture_exception(e)


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------

async def keyword_clustering_node(state: REXT) -> Dict[str, Any]:
    """
    LangGraph node — intent-aware semantic keyword clustering.

    Steps:
      1. Guard: serp_normalized must have real content.
      2. Resolve seed_keyword (3-level fallback).
      3. Resolve seed_intent (3-level fallback + heuristic).
      4. Filter SERP competitors to only those whose intent matches seed intent.
      5. Extract keyword candidates from intent-matched competitor corpus only.
      6. Run semantic clustering (Embeddings → HDBSCAN → Validation).
      7. Persist debug file & update state.
    """

    serp_normalized: Any = state.get("serp_normalized")
    serp_result: Dict[str, Any] = state.get("serp_result") or {}
    seo_result: Dict[str, Any] = state.get("seo_result") or {}
    serp_payload: Dict[str, Any] = state.get("serp_payload") or {}

    # ── Step 1: Guard ──────────────────────────────────────────────────────
    if not _serp_normalized_has_content(serp_normalized):
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("status", "early_return_no_content")
            scope.set_context("state_keys", {"keys": list(state.keys())})
            capture_message(
                "keyword_clustering: returning early — no SERP content detected",
                level="warning",
            )
        return {"seo_result": seo_result}

    # ── Step 2: Seed keyword ───────────────────────────────────────────────
    seed_keyword: Optional[str] = (
        (serp_normalized or {}).get("query")
        or (serp_payload or {}).get("query")
        or (serp_result or {}).get("search_params", {}).get("keyword")
    )

    # ── Step 3: Seed intent ────────────────────────────────────────────────
    # Priority 1: user-confirmed / SEO engine intent_type
    # Priority 2: DataForSEO main_intent from serp_backlinks
    # Priority 3: heuristic inference from the seed keyword text itself
    raw_seed_intent: str = (
        (seo_result.get("intent_type") or "").strip()
        or ((seo_result.get("serp_backlinks") or {}).get("main_intent") or "").strip()
    )
    if not raw_seed_intent and seed_keyword:
        raw_seed_intent = infer_intent_from_text(seed_keyword)

    seed_intent: str = _normalize_intent(raw_seed_intent) if raw_seed_intent else "unknown"

    with push_scope() as scope:
        scope.set_tag("module", "keyword_clustering")
        scope.set_context(
            "seed_info",
            {"seed_keyword": seed_keyword, "seed_intent": seed_intent},
        )
        capture_message(
            f"keyword_clustering: seed_keyword={seed_keyword!r}, "
            f"seed_intent={seed_intent!r}",
            level="info",
        )

    # ── Step 4: Filter competitors by intent ──────────────────────────────
    all_results: List[Dict[str, Any]] = list(
        (serp_normalized or {}).get("normalize_results") or []
    )
    intent_matched_results = _filter_competitors_by_intent(all_results, seed_intent)

    with push_scope() as scope:
        scope.set_tag("module", "keyword_clustering")
        scope.set_context(
            "intent_filter_result",
            {
                "total_competitors": len(all_results),
                "intent_matched": len(intent_matched_results),
                "seed_intent": seed_intent,
            },
        )
        capture_message(
            f"keyword_clustering: intent filter — "
            f"{len(intent_matched_results)}/{len(all_results)} competitors passed",
            level="info",
        )

    # ── Step 5: Extract keywords from intent-matched corpus ───────────────
    related_topics: List[str] = list((serp_normalized or {}).get("related_topics") or [])
    questions: List[str] = list((serp_normalized or {}).get("questions") or [])

    extractor = KeywordExtractor()
    try:
        extracted: List[Dict[str, Any]] = extractor.extract_keywords_from_competitors(
            intent_matched_results=intent_matched_results,
            query=seed_keyword or "",
            related_topics=related_topics,
            questions=questions,
            top_n=80,
        )
    except Exception as e:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("operation", "extract_keywords")
            scope.set_context(
                "extraction_data",
                {
                    "seed_keyword": seed_keyword,
                    "competitor_count": len(intent_matched_results),
                },
            )
            capture_exception(e)
        extracted = []

    if not extracted:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("status", "no_keywords_extracted")
            scope.set_context(
                "extraction_stats",
                {
                    "intent_matched_competitors": len(intent_matched_results),
                    "seed_keyword": seed_keyword,
                    "seed_intent": seed_intent,
                },
            )
            capture_message(
                "keyword_clustering: no keywords extracted from intent-matched "
                "competitor corpus",
                level="warning",
            )
        return {"seo_result": seo_result}

    with push_scope() as scope:
        scope.set_tag("module", "keyword_clustering")
        scope.set_context("extraction_result", {"keyword_count": len(extracted)})
        capture_message(
            f"keyword_clustering: extracted {len(extracted)} keyword candidates "
            f"from {len(intent_matched_results)} intent-matched competitors",
            level="info",
        )

    # ── Step 6: Build clustering config ───────────────────────────────────
    payload_cfg: Dict[str, Any] = (
        serp_payload.get("keyword_clustering_config") or {}
        if isinstance(serp_payload, dict)
        else {}
    )
    seo_cfg: Dict[str, Any] = (
        seo_result.get("keyword_clustering_config") or {}
        if isinstance(seo_result, dict)
        else {}
    )
    cfg_overrides: Dict[str, Any] = {**seo_cfg, **payload_cfg}

    defaults = KeywordClusteringConfig()
    search_params: Dict[str, Any] = (
        serp_result.get("search_params") or {}
        if isinstance(serp_result, dict)
        else {}
    )

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
    location_name = (
        None if location_code is not None else _resolve_location_name(raw_location_name)
    )
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
        min_cluster_size=int(
            cfg_overrides.get("min_cluster_size", defaults.min_cluster_size)
        ),
        max_noise_ratio=float(
            cfg_overrides.get("max_noise_ratio", defaults.max_noise_ratio)
        ),
        min_silhouette=float(
            cfg_overrides.get("min_silhouette", defaults.min_silhouette)
        ),
        agglomerative_distance_threshold=float(
            cfg_overrides.get(
                "agglomerative_distance_threshold",
                defaults.agglomerative_distance_threshold,
            )
        ),
        # DataForSEO enrichment settings (metadata only — not used in clustering)
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

    # ── Step 7: Cluster ────────────────────────────────────────────────────
    service = KeywordClusteringService(config=config)
    clusters = await service.cluster_keywords(
        extracted,
        seed_keyword=seed_keyword,
        seed_intent=seed_intent,
    )

    with push_scope() as scope:
        scope.set_tag("module", "keyword_clustering")
        scope.set_tag("status", "clustering_complete")
        scope.set_context(
            "clustering_result",
            {"cluster_count": len(clusters), "seed_keyword": seed_keyword},
        )
        capture_message(
            f"keyword_clustering: produced {len(clusters)} cluster(s)",
            level="info",
        )

    # Persist debug snapshot — never crashes the node
    _persist_keyword_clusters(clusters, seed_keyword)

    # ── Step 8: Update state ───────────────────────────────────────────────
    return {
        "seo_result": {
            **seo_result,
            "keyword_clusters": clusters,
        }
    }
