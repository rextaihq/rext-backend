import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import sentry_sdk
from sentry_sdk import capture_exception, capture_message, push_scope

from src.flow.states.countries import ISO_TO_COUNTRY, VALID_COUNTRY_CODES
from src.flow.states.rext import REXT
from src.services.keyword_clustering_service import (
    KeywordClusteringConfig,
    KeywordClusteringService,
)
from src.services.keyword_service import KeywordExtractor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _NumpyEncoder(json.JSONEncoder):
    """
    JSON encoder that handles numpy scalar / array types.

    numpy.float32/64 → float
    numpy.int32/64   → int
    numpy.ndarray    → list
    numpy.bool_      → bool

    This prevents silent TypeError when json.dumps encounters numpy types
    that are not natively JSON-serializable.
    """

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


def _resolve_location_name(raw_country: str | None) -> str:
    if not raw_country or raw_country.lower() == "global":
        return "United States"

    country = ISO_TO_COUNTRY.get(raw_country.lower(), raw_country)
    if country not in VALID_COUNTRY_CODES:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_context("country_validation", {"raw_country": raw_country, "resolved_country": country})
            capture_message(
                f"Keyword clustering country '{raw_country}' is not supported; defaulting to United States",
                level="warning"
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


def _sanitize_filename(value: str) -> str:
    sanitized = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in (value or "").strip()
    )
    return sanitized[:100] if sanitized else "seed"


def _serp_normalized_has_content(serp_normalized: Any) -> bool:
    """
    Returns True only when serp_normalized is a non-empty dict that contains
    at least ONE piece of usable SERP content.

    The old check ``if not serp_normalized`` returns True for an empty dict
    ``{}`` — which is falsy — causing a silent early return even when the
    SERP engine ran but produced no results.  This helper makes the guard
    explicit and logs *why* it failed.
    """
    if not isinstance(serp_normalized, dict):
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("validation", "type_check")
            scope.set_context("type_error", {"expected": "dict", "got": type(serp_normalized).__name__})
            capture_message(
                f"keyword_clustering: serp_normalized is not a dict (got {type(serp_normalized).__name__}); skipping",
                level="warning"
            )
        return False

    if not serp_normalized:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("validation", "empty_dict")
            capture_message(
                "keyword_clustering: serp_normalized is an empty dict {}; SERP engine may not have run yet — skipping",
                level="warning"
            )
        return False

    has_results = bool(serp_normalized.get("normalize_results"))
    has_query = bool(serp_normalized.get("query"))
    has_topics = bool(serp_normalized.get("related_topics"))
    has_questions = bool(serp_normalized.get("questions"))

    if not any([has_results, has_query, has_topics, has_questions]):
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("validation", "empty_fields")
            scope.set_context("field_status", {
                "normalize_results_count": len(serp_normalized.get("normalize_results") or []),
                "query_present": bool(serp_normalized.get("query")),
                "related_topics_count": len(serp_normalized.get("related_topics") or []),
                "questions_count": len(serp_normalized.get("questions") or [])
            })
            capture_message(
                "keyword_clustering: serp_normalized present but all content fields are empty",
                level="warning"
            )
        return False

    return True


def _persist_keyword_clusters(clusters: Any, seed_keyword: str | None) -> None:
    """
    Write the cluster result to a JSON file for debugging / audit.

    Uses _NumpyEncoder so that numpy scalar types (int64, float64, …) that
    may be present in the keyword dicts do not cause a silent TypeError.

    The output directory defaults to /tmp/keyword_clusters and can be
    overridden via the KEYWORD_CLUSTER_OUTPUT_DIR env var.
    """
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
            scope.set_tag("operation", "persist")
            scope.set_context("persistence_result", {
                "cluster_count": len(clusters) if clusters else 0,
                "file_path": str(file_path),
                "seed_keyword": seed_keyword
            })
            capture_message(
                f"keyword_clustering: persisted {len(clusters) if clusters else 0} cluster(s) to {file_path}",
                level="info"
            )
    except Exception as e:  # noqa: BLE001
        # Log the FULL traceback — not just the message — so the actual error
        # (e.g. "Object of type X is not JSON serializable") is visible in logs.
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("operation", "persist_clusters")
            scope.set_context("persistence", {"output_dir": str(output_dir), "seed_keyword": seed_keyword, "traceback": traceback.format_exc()})
            capture_exception(e)


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------

async def keyword_clustering_node(state: REXT) -> Dict[str, Any]:
    """
    LangGraph node for semantic keyword clustering.

    This node extracts a broad list of keyword candidates from the SERP data
    and groups them into semantic clusters using vector embeddings.
    """

    serp_normalized: Any = state.get("serp_normalized")
    serp_result: Dict[str, Any] = state.get("serp_result", {}) or {}
    seo_result: Dict[str, Any] = state.get("seo_result", {}) or {}
    serp_payload: Dict[str, Any] = state.get("serp_payload", {}) or {}

    # ------------------------------------------------------------------
    # Guard: serp_normalized must have real content
    # ------------------------------------------------------------------
    if not _serp_normalized_has_content(serp_normalized):
        # Log the full state keys so callers can diagnose what was present
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("status", "early_return_no_content")
            scope.set_context("state_keys", {"keys": list(state.keys())})
            capture_message(
                "keyword_clustering: returning early — no SERP content detected",
                level="warning"
            )
        return {"seo_result": seo_result}

    with push_scope() as scope:
        scope.set_tag("module", "keyword_clustering")
        scope.set_tag("status", "started")
        capture_message("keyword_clustering: starting analysis", level="info")

    # Three-level fallback for seed_keyword — all None-safe
    seed_keyword: str | None = (
        (serp_normalized or {}).get("query")
        or (serp_payload or {}).get("query")
        or (serp_result or {}).get("search_params", {}).get("keyword")
    )

    with push_scope() as scope:
        scope.set_tag("module", "keyword_clustering")
        scope.set_context("seed_info", {"seed_keyword": seed_keyword, "seed_intent": seed_intent})
        capture_message(f"keyword_clustering: seed_keyword={seed_keyword!r}, intent={seed_intent!r}", level="debug")

    # Seed intent: user-selected > SEO engine intent_type > DataForSEO intent
    seed_intent: str = (
        (seo_result.get("intent_type") or "").strip()
        or ((seo_result.get("serp_backlinks") or {}).get("main_intent") or "").strip()
        or "unknown"
    )

    # ------------------------------------------------------------------
    # 1. Extract raw keyword candidates from SERP data
    # ------------------------------------------------------------------
    extractor = KeywordExtractor()
    try:
        extracted: List[Dict[str, Any]] = extractor.extract_keywords(
            serp_normalized, top_n=50
        )
    except Exception as e:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("operation", "extract_keywords")
            scope.set_context("extraction_data", {"seed_keyword": seed_keyword, "top_n": 50})
            capture_exception(e)
        extracted = []

    if not extracted:
        with push_scope() as scope:
            scope.set_tag("module", "keyword_clustering")
            scope.set_tag("status", "no_keywords_extracted")
            scope.set_context("extraction_stats", {
                "normalize_results_count": len(serp_normalized.get("normalize_results") or []),
                "query": serp_normalized.get("query"),
                "related_topics_count": len(serp_normalized.get("related_topics") or []),
                "questions_count": len(serp_normalized.get("questions") or [])
            })
            capture_message("keyword_clustering: no keywords extracted from SERP data", level="warning")
        return {"seo_result": seo_result}

    with push_scope() as scope:
        scope.set_tag("module", "keyword_clustering")
        scope.set_tag("status", "keywords_extracted")
        scope.set_context("extraction_result", {"keyword_count": len(extracted)})
        capture_message(f"keyword_clustering: extracted {len(extracted)} keyword candidates", level="info")

    # ------------------------------------------------------------------
    # 2. Build clustering config from payload / seo_result overrides
    # ------------------------------------------------------------------
    payload_cfg: Dict[str, Any] = (
        serp_payload.get("keyword_clustering_config", {})
        if isinstance(serp_payload, dict)
        else {}
    ) or {}
    seo_cfg: Dict[str, Any] = (
        seo_result.get("keyword_clustering_config", {})
        if isinstance(seo_result, dict)
        else {}
    ) or {}
    cfg_overrides: Dict[str, Any] = {**seo_cfg, **payload_cfg}

    defaults = KeywordClusteringConfig()
    search_params: Dict[str, Any] = (
        serp_result.get("search_params", {}) if isinstance(serp_result, dict) else {}
    ) or {}

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
        min_search_volume=int(
            cfg_overrides.get("min_search_volume", defaults.min_search_volume)
        ),
        max_keyword_difficulty=int(
            cfg_overrides.get("max_keyword_difficulty", defaults.max_keyword_difficulty)
        ),
        require_metrics=bool(
            cfg_overrides.get("require_metrics", defaults.require_metrics)
        ),
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

    # ------------------------------------------------------------------
    # 3. Cluster
    # ------------------------------------------------------------------
    service = KeywordClusteringService(config=config)
    clusters: List[Any] = await service.cluster_keywords(
        extracted, seed_keyword=seed_keyword, seed_intent=seed_intent
    )

    with push_scope() as scope:
        scope.set_tag("module", "keyword_clustering")
        scope.set_tag("status", "clustering_complete")
        scope.set_context("clustering_result", {"cluster_count": len(clusters), "seed_keyword": seed_keyword})
        capture_message(f"keyword_clustering: produced {len(clusters)} cluster(s)", level="info")

    # Persist debug file — always attempted, never crashes the node
    _persist_keyword_clusters(clusters, seed_keyword)

    # ------------------------------------------------------------------
    # 4. Update state
    # ------------------------------------------------------------------
    return {
        "seo_result": {
            **seo_result,
            "keyword_clusters": clusters,
        }
    }
