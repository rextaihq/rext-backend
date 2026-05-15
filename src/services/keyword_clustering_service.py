import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity

from src.flow.states.seo_state import KeywordCluster
from src.utils.embedding import get_embedding

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KeywordClusteringConfig:
    """
    Tunables for keyword clustering.

    Notes (2026):
    - We prefer intent-consistent clusters. Seed-intent mismatch is filtered early.
    - We prefer semantic closeness to the seed keyword (min_seed_similarity).
    - If keyword metrics are available (search_volume/kd), we can filter for
      high-volume + low-difficulty opportunities.
    """

    # Semantic filters
    min_seed_similarity: float = 0.35  # cosine similarity to seed keyword embedding
    min_pairwise_similarity: float = 0.25  # used for validation diagnostics only

    # HDBSCAN knobs (when available)
    min_cluster_size: int = 2
    min_samples: Optional[int] = None
    cluster_selection_epsilon: float = 0.0

    # Validation / safety rails
    max_noise_ratio: float = 0.6  # if too much noise, fallback to agglomerative
    min_silhouette: float = 0.02  # if silhouette too low, fallback to agglomerative

    # Metric-based opportunity filters (optional)
    require_metrics: bool = False
    min_search_volume: int = 0
    max_keyword_difficulty: int = 100
    enable_dataforseo_metrics: bool = False  # fetch missing KD/volume for candidates
    location_name: Optional[str] = None
    location_code: Optional[int] = None
    language_code: Optional[str] = None
    language_name: Optional[str] = None

    # Agglomerative fallback
    agglomerative_distance_threshold: float = 0.45


def _normalize_intent(intent: Optional[str]) -> str:
    if not intent:
        return "unknown"
    i = str(intent).strip().lower()
    if not i:
        return "unknown"
    aliases = {
        "info": "informational",
        "informative": "informational",
        "commercial investigation": "commercial",
        "investigational": "commercial",
        "navigational": "navigational",
        "transactional": "transactional",
    }
    return aliases.get(i, i)


def infer_keyword_intent(keyword: str) -> str:
    """
    Lightweight intent inference from the keyword itself.

    This is a heuristic used only for filtering/consistency when we don't have
    per-result intent labels from upstream.
    """
    text = (keyword or "").strip().lower()
    if not text:
        return "unknown"

    transactional_markers = {
        "buy",
        "order",
        "coupon",
        "discount",
        "deal",
        "price",
        "pricing",
        "cheap",
        "sale",
        "subscribe",
        "booking",
        "book",
        "hire",
        "near me",
    }
    commercial_markers = {
        "best",
        "top",
        "vs",
        "compare",
        "comparison",
        "review",
        "reviews",
        "software",
        "tool",
        "tools",
        "service",
        "services",
        "agency",
        "provider",
        "alternative",
        "alternatives",
    }
    informational_markers = {
        "what",
        "how",
        "why",
        "when",
        "where",
        "guide",
        "tutorial",
        "learn",
        "meaning",
        "examples",
        "template",
    }

    # Order matters: transactional is most specific.
    if any(m in text for m in transactional_markers):
        return "transactional"
    if any(m in text for m in commercial_markers):
        return "commercial"
    if any(text.startswith(m + " ") or text == m for m in informational_markers):
        return "informational"

    return "unknown"


class KeywordClusteringService:
    """
    Service for grouping keywords into semantic clusters using embeddings.

    Pipeline:
    1) Filter to intent-consistent candidates (heuristic intent inference)
    2) (Optional) Filter by KD/volume if those metrics exist
    3) Embeddings
    4) Similarity matrix
    5) HDBSCAN clustering (preferred) with validation
    6) Fallback to Agglomerative clustering if needed
    """
    
    def __init__(self, config: Optional[KeywordClusteringConfig] = None):
        self.config = config or KeywordClusteringConfig()
        self.embeddings_model = get_embedding()
        
    async def cluster_keywords(
        self,
        keywords_data: List[Dict[str, Any]],
        *,
        seed_keyword: Optional[str] = None,
        seed_intent: Optional[str] = None,
    ) -> List[KeywordCluster]:
        """
        Clusters a list of keyword objects into semantic groups.
        
        Args:
            keywords_data: List of dicts containing 'keyword' and 'score'
            seed_keyword: The user seed keyword (used for similarity filtering)
            seed_intent: The seed keyword intent (used for intent-consistency filtering)
            
        Returns:
            List of KeywordCluster objects.
        """
        if not keywords_data:
            return []
            
        seed_intent_norm = _normalize_intent(seed_intent)
        filtered = self._filter_candidates(
            keywords_data,
            seed_intent=seed_intent_norm,
            apply_metric_filters=False,
        )

        if not filtered:
            # If we filtered everything out, fall back to the original list.
            filtered = keywords_data

        # Optional: enrich missing metrics (search_volume / keyword_difficulty) for candidates.
        if self.config.enable_dataforseo_metrics:
            filtered = await self._enrich_dataforseo_metrics(filtered)

        filtered_with_metrics = self._filter_candidates(
            filtered,
            seed_intent=seed_intent_norm,
            apply_metric_filters=True,
        )
        if filtered_with_metrics:
            filtered = filtered_with_metrics

        if len(filtered) == 1:
            return [self._format_cluster([filtered[0]], seed_intent=seed_intent_norm)]

        try:
            # 1. Extract raw keyword strings
            keyword_texts = [kw["keyword"] for kw in filtered]

            # 2. Generate embeddings (and seed embedding if provided)
            seed_embedding = None
            if seed_keyword:
                seed_embedding = await self._embed_one(seed_keyword)

            embeddings = await self.embeddings_model.aembed_documents(keyword_texts)
            embeddings_np = np.asarray(embeddings, dtype=float)

            # 3. Seed similarity filter (keeps only same-intent and semantically close keywords)
            if seed_embedding is not None and len(keyword_texts) > 1:
                kept_idx = self._filter_by_seed_similarity(
                    embeddings_np, seed_embedding, min_similarity=self.config.min_seed_similarity
                )
                if kept_idx:
                    filtered = [filtered[i] for i in kept_idx]
                    keyword_texts = [keyword_texts[i] for i in kept_idx]
                    embeddings_np = embeddings_np[kept_idx]

            if len(filtered) == 1:
                return [self._format_cluster([filtered[0]], seed_intent=seed_intent_norm)]

            # 4. Similarity matrix (cosine)
            similarity_matrix = cosine_similarity(embeddings_np)
            distance_matrix = np.clip(1.0 - similarity_matrix, 0.0, 2.0)

            # 5. HDBSCAN clustering (preferred)
            cluster_ids, diagnostics = self._try_hdbscan(distance_matrix, embeddings_np)

            # 6. Validate clusters; fallback if needed
            if self._should_fallback(cluster_ids, distance_matrix):
                cluster_ids = self._agglomerative_fallback(embeddings_np)
                diagnostics["fallback"] = "agglomerative"
            else:
                diagnostics["fallback"] = None
            
            # 4. Group keywords by cluster ID
            groups = {}
            for idx, cluster_id in enumerate(cluster_ids):
                if cluster_id not in groups:
                    groups[cluster_id] = []
                groups[cluster_id].append(filtered[idx])
                
            # 5. Format and name each cluster
            clusters = []
            for cluster_id, group_keywords in groups.items():
                if cluster_id == -1:
                    # Noise keywords: keep them as singletons (still useful long-tail candidates)
                    for kw in group_keywords:
                        clusters.append(self._format_cluster([kw], seed_intent=seed_intent_norm))
                else:
                    clusters.append(
                        self._format_cluster(group_keywords, seed_intent=seed_intent_norm)
                    )
                
            # Sort clusters by total score descending
            clusters.sort(key=lambda x: x["total_score"], reverse=True)
            
            logger.info(
                "Keyword clustering complete: "
                f"in={len(keywords_data)} kept={len(filtered)} clusters={len(clusters)} "
                f"hdbscan_noise_ratio={diagnostics.get('noise_ratio')} "
                f"fallback={diagnostics.get('fallback')}"
            )
            return clusters
            
        except Exception as e:
            logger.error(f"Error during keyword clustering: {e}")
            # Fallback: Treat all keywords as one cluster if clustering fails
            return [self._format_cluster(filtered, seed_intent=seed_intent_norm)]

    def _filter_candidates(
        self,
        keywords_data: List[Dict[str, Any]],
        *,
        seed_intent: str,
        apply_metric_filters: bool,
    ) -> List[Dict[str, Any]]:
        """
        Enforces:
        - De-duplication
        - Intent consistency (best-effort heuristic)
        - Optional metric filters (KD low, volume high) when metrics exist
        """
        seen: set[str] = set()
        out: list[dict[str, Any]] = []

        for item in keywords_data:
            kw = (item or {}).get("keyword")
            if not kw:
                continue
            key = str(kw).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)

            inferred_intent = _normalize_intent(item.get("intent"))
            if inferred_intent == "unknown":
                inferred_intent = infer_keyword_intent(key)

            intent_ok = True
            if seed_intent and seed_intent != "unknown":
                # Keep unknowns, but filter explicit mismatches
                if inferred_intent not in {"unknown", seed_intent}:
                    intent_ok = False

            if not intent_ok:
                continue

            if apply_metric_filters:
                vol = item.get("search_volume")
                kd = item.get("keyword_difficulty")
                has_metrics = isinstance(vol, (int, float)) and isinstance(kd, (int, float))
                if self.config.require_metrics and not has_metrics:
                    continue

                if has_metrics:
                    if int(vol) < self.config.min_search_volume:
                        continue
                    if int(kd) > self.config.max_keyword_difficulty:
                        continue

            enriched = dict(item)
            enriched["intent_inferred"] = inferred_intent
            enriched["intent_match"] = (
                True
                if seed_intent == "unknown"
                else inferred_intent in {seed_intent, "unknown"}
            )
            out.append(enriched)

        return out

    async def _embed_one(self, text: str) -> np.ndarray:
        vec = await self.embeddings_model.aembed_documents([text])
        return np.asarray(vec[0], dtype=float)

    async def _enrich_dataforseo_metrics(
        self, keywords_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Best-effort enrichment of missing metrics via DataForSEO keyword_overview/live.

        Requires env:
        - DATAFORSEO_BACKLINKS_URL
        - DATAFORSEO_AUTH_HEADER (base64 user:pass)

        If unavailable or API errors occur, returns the input unchanged.
        """
        url = os.getenv("DATAFORSEO_BACKLINKS_URL")
        auth = os.getenv("DATAFORSEO_AUTH_HEADER")
        if not url or not auth:
            return keywords_data

        missing = [
            (i, kw)
            for i, kw in enumerate(keywords_data)
            if not isinstance(kw.get("search_volume"), (int, float))
            or not isinstance(kw.get("keyword_difficulty"), (int, float))
        ]
        if not missing:
            return keywords_data

        # DataForSEO supports batching keywords in one task. Keep batches conservative.
        batch_size = 50
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        enriched = list(keywords_data)

        for start in range(0, len(missing), batch_size):
            batch = missing[start : start + batch_size]
            batch_keywords = [
                str(item[1].get("keyword", "")).strip()
                for item in batch
                if item[1].get("keyword")
            ]
            if not batch_keywords:
                continue

            task_payload: Dict[str, Any] = {"keywords": batch_keywords}

            if self.config.location_code is not None:
                task_payload["location_code"] = self.config.location_code
            elif self.config.location_name:
                task_payload["location_name"] = self.config.location_name
            else:
                logger.warning("Skipping DataForSEO enrichment: missing location_name/code")
                return enriched

            if self.config.language_code:
                task_payload["language_code"] = self.config.language_code
            elif self.config.language_name:
                task_payload["language_name"] = self.config.language_name
            else:
                logger.warning("Skipping DataForSEO enrichment: missing language_name/code")
                return enriched

            payload = [task_payload]

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:
                logger.warning(f"DataForSEO enrichment failed: {e}")
                continue

            task = (data.get("tasks") or [{}])[0]
            if task.get("status_code") != 20000:
                logger.warning(f"DataForSEO enrichment task error: {task.get('status_message')}")
                continue

            result = task.get("result") or []
            items = (result[0].get("items") or []) if result else []
            by_kw: Dict[str, Dict[str, Any]] = {}
            for item in items:
                k = (item.get("keyword") or "").strip().lower()
                if not k:
                    continue
                ki = item.get("keyword_info", {}) or {}
                kp = item.get("keyword_properties", {}) or {}
                by_kw[k] = {
                    "search_volume": int(ki.get("search_volume") or 0),
                    "keyword_difficulty": int(kp.get("keyword_difficulty") or 0),
                }

            for idx, kw in batch:
                k = str(kw.get("keyword", "")).strip().lower()
                metrics = by_kw.get(k)
                if not metrics:
                    continue
                merged = dict(enriched[idx])
                merged.update(metrics)
                enriched[idx] = merged

        return enriched

    def _filter_by_seed_similarity(
        self, embeddings: np.ndarray, seed_embedding: np.ndarray, *, min_similarity: float
    ) -> List[int]:
        seed = seed_embedding.reshape(1, -1)
        sims = cosine_similarity(embeddings, seed).reshape(-1)
        kept = [i for i, s in enumerate(sims) if float(s) >= float(min_similarity)]
        return kept

    def _try_hdbscan(
        self, distance_matrix: np.ndarray, embeddings: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Attempts HDBSCAN using whichever implementation is available.
        Returns (labels, diagnostics).
        """
        labels = None
        diagnostics: Dict[str, Any] = {}

        # Prefer scikit-learn's HDBSCAN if present (newer sklearn versions),
        # otherwise use the hdbscan package if installed.
        sklearn_hdbscan = None
        try:
            from sklearn.cluster import HDBSCAN as _SklearnHDBSCAN  # type: ignore

            sklearn_hdbscan = _SklearnHDBSCAN
        except Exception:
            sklearn_hdbscan = None

        if sklearn_hdbscan is not None:
            model = sklearn_hdbscan(
                min_cluster_size=self.config.min_cluster_size,
                min_samples=self.config.min_samples,
                metric="precomputed",
                cluster_selection_epsilon=self.config.cluster_selection_epsilon,
            )
            labels = model.fit_predict(distance_matrix)
        else:
            try:
                import hdbscan  # type: ignore

                model = hdbscan.HDBSCAN(
                    min_cluster_size=self.config.min_cluster_size,
                    min_samples=self.config.min_samples,
                    metric="precomputed",
                    cluster_selection_epsilon=self.config.cluster_selection_epsilon,
                )
                labels = model.fit_predict(distance_matrix)
            except Exception as e:
                # HDBSCAN unavailable: let validation decide fallback.
                logger.warning(f"HDBSCAN unavailable ({e}); will use fallback clustering")
                labels = np.zeros((embeddings.shape[0],), dtype=int)

        labels = np.asarray(labels, dtype=int)
        noise_ratio = float(np.mean(labels == -1)) if labels.size else 1.0
        diagnostics["noise_ratio"] = round(noise_ratio, 4)
        return labels, diagnostics

    def _should_fallback(self, labels: np.ndarray, distance_matrix: np.ndarray) -> bool:
        # Too much noise means HDBSCAN likely failed to find stable structure.
        if labels.size == 0:
            return True

        noise_ratio = float(np.mean(labels == -1))
        if noise_ratio > self.config.max_noise_ratio:
            return True

        # Silhouette validation: evaluate only non-noise points and only if 2+ clusters exist.
        mask = labels != -1
        kept = labels[mask]
        if kept.size < 3:
            return True
        unique = np.unique(kept)
        if unique.size < 2:
            return True

        try:
            sil = float(
                silhouette_score(distance_matrix[mask][:, mask], kept, metric="precomputed")
            )
        except Exception:
            return True

        return sil < self.config.min_silhouette

    def _agglomerative_fallback(self, embeddings: np.ndarray) -> np.ndarray:
        clustering_model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=self.config.agglomerative_distance_threshold,
            metric="cosine",
            linkage="average",
        )
        return clustering_model.fit_predict(embeddings)

    def _format_cluster(
        self, group_keywords: List[Dict[str, Any]], *, seed_intent: str = "unknown"
    ) -> KeywordCluster:
        """
        Identifies the centroid (best keyword) and formats the cluster object.
        """
        # Sort by score within the group to pick the "Name" (Centroid replacement)
        sorted_group = sorted(group_keywords, key=lambda x: x.get("score", 0), reverse=True)
        
        cluster_name = sorted_group[0]["keyword"]
        total_score = sum(kw.get("score", 0) for kw in group_keywords)
        
        return {
            "cluster_name": cluster_name,
            "keywords": sorted_group,
            "total_score": round(total_score, 2),
            "main_intent": _normalize_intent(
                sorted_group[0].get("intent")
                or sorted_group[0].get("intent_inferred")
                or seed_intent
            )
        }
