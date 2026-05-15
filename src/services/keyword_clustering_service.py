"""
Keyword Clustering Service — Intent-Aware Semantic Clustering

Pipeline (per user spec):
  1.  Receive only intent-matched competitor keywords (pre-filtered upstream).
  2.  Deduplicate & sanitize.
  3.  Embed all keywords + seed keyword.
  4.  Compute cosine Semantic Similarity Matrix.
  5.  Filter by min_seed_similarity threshold (no KD/volume used here).
  6.  HDBSCAN clustering on distance matrix.
  7.  Cluster Validation (noise ratio + silhouette score thresholds).
  8.  Agglomerative fallback when HDBSCAN underperforms.
  9.  Format & sort final clusters.

KD and search_volume are NOT used inside any clustering logic.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity

from src.flow.states.seo_state import KeywordCluster
from src.utils.embedding import get_embedding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KeywordClusteringConfig:
    """
    Tunables for semantic keyword clustering.

    KD / search_volume fields are retained for DataForSEO metric enrichment
    only — they are NEVER used inside the clustering or filtering logic.
    """

    # ── Semantic similarity thresholds ────────────────────────────────────
    # Minimum cosine similarity between a candidate keyword embedding and the
    # seed keyword embedding.  Raise to get tighter clusters; lower to allow
    # more tangential terms.
    min_seed_similarity: float = 0.30

    # ── HDBSCAN knobs ─────────────────────────────────────────────────────
    min_cluster_size: int = 2
    min_samples: Optional[int] = None
    cluster_selection_epsilon: float = 0.0

    # ── Cluster-quality thresholds ────────────────────────────────────────
    # If HDBSCAN labels too many points as noise (−1), fall back.
    max_noise_ratio: float = 0.55
    # If the silhouette score for non-noise clusters is below this, fall back.
    min_silhouette: float = 0.05

    # ── Agglomerative fallback ─────────────────────────────────────────────
    agglomerative_distance_threshold: float = 0.40

    # ── DataForSEO enrichment (metadata only — not used in clustering) ─────
    enable_dataforseo_metrics: bool = False
    require_metrics: bool = False          # kept for API compat, ignored in logic
    min_search_volume: int = 0             # kept for API compat, ignored in logic
    max_keyword_difficulty: int = 100      # kept for API compat, ignored in logic
    location_name: Optional[str] = None
    location_code: Optional[int] = None
    language_code: Optional[str] = None
    language_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Intent helpers
# ---------------------------------------------------------------------------

def _normalize_intent(intent: Optional[str]) -> str:
    if not intent:
        return "unknown"
    i = str(intent).strip().lower()
    aliases = {
        "info": "informational",
        "informative": "informational",
        "commercial investigation": "commercial",
        "investigational": "commercial",
    }
    return aliases.get(i, i) if i else "unknown"


def infer_intent_from_text(text: str) -> str:
    """
    Lightweight heuristic intent inference from a text string (keyword, title,
    or snippet).  Used to label competitor SERP results before filtering.
    """
    t = (text or "").strip().lower()
    if not t:
        return "unknown"

    transactional = {
        "buy", "order", "coupon", "discount", "deal", "price", "pricing",
        "cheap", "sale", "subscribe", "booking", "book", "hire", "near me",
        "get", "download", "free trial", "sign up", "register",
    }
    commercial = {
        "best", "top", "vs", "compare", "comparison", "review", "reviews",
        "software", "tool", "tools", "service", "services", "agency",
        "provider", "alternative", "alternatives", "ranked", "ranking",
    }
    informational = {
        "what", "how", "why", "when", "where", "guide", "tutorial",
        "learn", "meaning", "examples", "template", "definition",
        "explained", "overview", "introduction",
    }

    if any(m in t for m in transactional):
        return "transactional"
    if any(m in t for m in commercial):
        return "commercial"
    if any(t.startswith(m + " ") or t == m for m in informational):
        return "informational"
    return "unknown"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class KeywordClusteringService:
    """
    Intent-aware semantic keyword clustering service.

    Expects `keywords_data` to already be pre-filtered for intent by the
    upstream LangGraph node.  This service focuses purely on:
        - Deduplication
        - Embedding generation
        - Semantic similarity filtering against seed keyword
        - HDBSCAN clustering with validation & fallback
    """

    def __init__(self, config: Optional[KeywordClusteringConfig] = None):
        self.config = config or KeywordClusteringConfig()
        self.embeddings_model = get_embedding()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def cluster_keywords(
        self,
        keywords_data: List[Dict[str, Any]],
        *,
        seed_keyword: Optional[str] = None,
        seed_intent: Optional[str] = None,
    ) -> List[KeywordCluster]:
        """
        Cluster a list of keyword dicts into semantic groups.

        Args:
            keywords_data:  [{keyword, score, source, ...}, ...]
                            Pre-filtered by intent upstream.
            seed_keyword:   Seed keyword string for similarity filtering.
            seed_intent:    Normalised intent label of the seed keyword.

        Returns:
            List[KeywordCluster] sorted by total_score descending.
        """
        if not keywords_data:
            logger.warning("cluster_keywords: received empty keyword list")
            return []

        seed_intent_norm = _normalize_intent(seed_intent)

        # Step 1 — Deduplicate
        deduped = self._deduplicate(keywords_data)
        logger.info(
            "cluster_keywords: dedup %d → %d unique keywords",
            len(keywords_data),
            len(deduped),
        )

        if not deduped:
            return []

        if len(deduped) == 1:
            return [self._format_cluster(deduped, seed_intent=seed_intent_norm)]

        try:
            # Step 2 — Embed seed keyword
            seed_embedding: Optional[np.ndarray] = None
            if seed_keyword:
                seed_embedding = await self._embed_one(seed_keyword)

            # Step 3 — Embed all candidate keywords
            keyword_texts = [kw["keyword"] for kw in deduped]
            raw_embeddings = await self.embeddings_model.aembed_documents(keyword_texts)
            embeddings_np = np.asarray(raw_embeddings, dtype=float)

            # Step 4 — Semantic Similarity Matrix (cosine) & seed similarity filter
            if seed_embedding is not None:
                kept_idx, seed_sims = self._filter_by_seed_similarity(
                    embeddings_np,
                    seed_embedding,
                    min_similarity=self.config.min_seed_similarity,
                )
                if kept_idx:
                    deduped = [deduped[i] for i in kept_idx]
                    # attach seed_similarity score for diagnostics
                    for j, kw in enumerate(deduped):
                        kw["seed_similarity"] = round(float(seed_sims[kept_idx[j]]), 4)
                    keyword_texts = [kw["keyword"] for kw in deduped]
                    embeddings_np = embeddings_np[kept_idx]
                    logger.info(
                        "cluster_keywords: seed-sim filter kept %d / %d keywords "
                        "(threshold=%.2f)",
                        len(kept_idx),
                        len(keyword_texts) + (len(deduped) - len(kept_idx)),
                        self.config.min_seed_similarity,
                    )
                else:
                    logger.warning(
                        "cluster_keywords: seed-sim filter removed ALL keywords "
                        "(threshold=%.2f) — using full deduped set",
                        self.config.min_seed_similarity,
                    )

            if len(deduped) == 1:
                return [self._format_cluster(deduped, seed_intent=seed_intent_norm)]

            # Step 5 — Build distance matrix from cosine similarity matrix
            similarity_matrix = cosine_similarity(embeddings_np)
            distance_matrix = np.clip(1.0 - similarity_matrix, 0.0, 2.0)

            # Step 6 — HDBSCAN clustering
            cluster_ids, diagnostics = self._run_hdbscan(distance_matrix, embeddings_np)

            # Step 7 — Cluster validation + fallback
            if self._should_fallback(cluster_ids, distance_matrix):
                logger.info(
                    "cluster_keywords: HDBSCAN quality below threshold "
                    "(noise_ratio=%.2f) — switching to Agglomerative fallback",
                    diagnostics.get("noise_ratio", -1),
                )
                cluster_ids = self._agglomerative_fallback(embeddings_np)
                diagnostics["fallback"] = "agglomerative"
            else:
                diagnostics["fallback"] = None

            # Step 8 — Group & format
            clusters = self._group_and_format(
                deduped, cluster_ids, seed_intent=seed_intent_norm
            )

            logger.info(
                "cluster_keywords: done — input=%d kept=%d clusters=%d "
                "noise_ratio=%.2f fallback=%s",
                len(keywords_data),
                len(deduped),
                len(clusters),
                diagnostics.get("noise_ratio", 0.0),
                diagnostics.get("fallback"),
            )
            return clusters

        except Exception:
            logger.exception("cluster_keywords: unexpected error — returning single cluster")
            return [self._format_cluster(deduped, seed_intent=seed_intent_norm)]

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _deduplicate(self, keywords_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate keywords (case-insensitive) preserving highest score."""
        seen: Dict[str, Dict[str, Any]] = {}
        for item in keywords_data:
            kw = (item or {}).get("keyword")
            if not kw:
                continue
            key = str(kw).strip().lower()
            if not key:
                continue
            existing = seen.get(key)
            if existing is None or item.get("score", 0) > existing.get("score", 0):
                seen[key] = dict(item)
        return list(seen.values())

    async def _embed_one(self, text: str) -> np.ndarray:
        vecs = await self.embeddings_model.aembed_documents([text])
        return np.asarray(vecs[0], dtype=float)

    def _filter_by_seed_similarity(
        self,
        embeddings: np.ndarray,
        seed_embedding: np.ndarray,
        *,
        min_similarity: float,
    ) -> Tuple[List[int], np.ndarray]:
        """
        Returns (kept_indices, all_similarities).
        kept_indices are those whose cosine similarity to seed >= min_similarity.
        """
        seed = seed_embedding.reshape(1, -1)
        sims = cosine_similarity(embeddings, seed).reshape(-1)
        kept = [i for i, s in enumerate(sims) if float(s) >= min_similarity]
        return kept, sims

    def _run_hdbscan(
        self,
        distance_matrix: np.ndarray,
        embeddings: np.ndarray,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Try sklearn's HDBSCAN first (newer sklearn), then the hdbscan package,
        then fall back to all-zeros labels so _should_fallback triggers.
        """
        diagnostics: Dict[str, Any] = {}
        labels: Optional[np.ndarray] = None

        # sklearn HDBSCAN (sklearn ≥ 1.3)
        try:
            from sklearn.cluster import HDBSCAN as _SkHDBSCAN  # type: ignore

            model = _SkHDBSCAN(
                min_cluster_size=self.config.min_cluster_size,
                min_samples=self.config.min_samples,
                metric="precomputed",
                cluster_selection_epsilon=self.config.cluster_selection_epsilon,
            )
            labels = model.fit_predict(distance_matrix)
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("sklearn HDBSCAN failed: %s", exc)

        # hdbscan package fallback
        if labels is None:
            try:
                import hdbscan as _hdbscan_pkg  # type: ignore

                model = _hdbscan_pkg.HDBSCAN(
                    min_cluster_size=self.config.min_cluster_size,
                    min_samples=self.config.min_samples,
                    metric="precomputed",
                    cluster_selection_epsilon=self.config.cluster_selection_epsilon,
                )
                labels = model.fit_predict(distance_matrix)
            except Exception as exc:
                logger.warning("hdbscan package failed: %s — all-noise fallback", exc)
                labels = np.full(embeddings.shape[0], -1, dtype=int)

        labels = np.asarray(labels, dtype=int)
        noise_ratio = float(np.mean(labels == -1)) if labels.size else 1.0
        diagnostics["noise_ratio"] = round(noise_ratio, 4)
        diagnostics["n_clusters"] = int(np.unique(labels[labels >= 0]).size)
        return labels, diagnostics

    def _should_fallback(
        self,
        labels: np.ndarray,
        distance_matrix: np.ndarray,
    ) -> bool:
        """
        Return True if HDBSCAN quality is below acceptable thresholds:
          - Too many noise points (> max_noise_ratio)
          - All points are noise
          - Only one cluster found (silhouette undefined)
          - Silhouette score below min_silhouette
        """
        if labels.size == 0:
            return True

        noise_ratio = float(np.mean(labels == -1))
        if noise_ratio > self.config.max_noise_ratio:
            return True

        # Evaluate silhouette on non-noise points only
        mask = labels != -1
        non_noise_labels = labels[mask]
        if non_noise_labels.size < 3:
            return True

        unique_clusters = np.unique(non_noise_labels)
        if unique_clusters.size < 2:
            # Single cluster — silhouette undefined; check noise ratio instead
            return noise_ratio > 0.3

        try:
            sub_dist = distance_matrix[mask][:, mask]
            sil = float(silhouette_score(sub_dist, non_noise_labels, metric="precomputed"))
            return sil < self.config.min_silhouette
        except Exception:
            return True

    def _agglomerative_fallback(self, embeddings: np.ndarray) -> np.ndarray:
        model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=self.config.agglomerative_distance_threshold,
            metric="cosine",
            linkage="average",
        )
        return model.fit_predict(embeddings)

    def _group_and_format(
        self,
        keywords: List[Dict[str, Any]],
        cluster_ids: np.ndarray,
        *,
        seed_intent: str,
    ) -> List[KeywordCluster]:
        """Group keywords by cluster label and format each cluster."""
        groups: Dict[int, List[Dict[str, Any]]] = {}
        for idx, cid in enumerate(cluster_ids):
            groups.setdefault(int(cid), []).append(keywords[idx])

        clusters: List[KeywordCluster] = []
        for cid, group in groups.items():
            if cid == -1:
                # HDBSCAN noise: emit as singleton clusters (long-tail candidates)
                for kw in group:
                    clusters.append(self._format_cluster([kw], seed_intent=seed_intent))
            else:
                clusters.append(self._format_cluster(group, seed_intent=seed_intent))

        clusters.sort(key=lambda c: c["total_score"], reverse=True)
        return clusters

    def _format_cluster(
        self,
        group: List[Dict[str, Any]],
        *,
        seed_intent: str = "unknown",
    ) -> KeywordCluster:
        """
        Pick the highest-scoring keyword as the cluster name (centroid proxy)
        and compute the cluster's total relevance score.

        seed_similarity is used as a secondary sort signal when scores tie.
        """
        sorted_group = sorted(
            group,
            key=lambda x: (x.get("score", 0), x.get("seed_similarity", 0)),
            reverse=True,
        )
        cluster_name = sorted_group[0]["keyword"]
        total_score = round(sum(kw.get("score", 0) for kw in group), 4)

        # Determine dominant intent across the cluster
        intent_votes: Dict[str, int] = {}
        for kw in group:
            intent = _normalize_intent(
                kw.get("intent") or kw.get("intent_inferred")
            )
            if intent != "unknown":
                intent_votes[intent] = intent_votes.get(intent, 0) + 1
        dominant_intent = (
            max(intent_votes, key=lambda k: intent_votes[k])
            if intent_votes
            else seed_intent
        )

        return {
            "cluster_name": cluster_name,
            "keywords": sorted_group,
            "total_score": total_score,
            "main_intent": dominant_intent,
        }
