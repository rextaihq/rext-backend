import logging
from typing import List, Dict, Any, Optional

from langchain.messages import SystemMessage, HumanMessage

from src.flow.model.llm_manager import load_model
from src.flow.model.structure.keyword_clustering import KeywordClusteringLLMOutput
from src.flow.prompts.system.keyword_clustering import KEYWORD_CLUSTERING_SYSTEM_PROMPT
from src.flow.states.rext import IntentMatchedSerpSignals
from src.flow.states.seo_state import KeywordCluster

logger = logging.getLogger(__name__)

_VALID_INTENTS = frozenset({
    "informational", "commercial", "navigational", "transactional",
})


def resolve_primary_intent(
    seo_result: Optional[Dict[str, Any]] = None,
    serp_backlinks: Optional[Dict[str, Any]] = None,
    serp_normalized: Optional[Dict[str, Any]] = None,
    final_intent_type: Optional[str] = None,
) -> str:
    """
    Resolve the primary keyword intent from DataForSEO, competitor LLM, or
    intent-matched SERP signals (payload-aligned).
    """
    seo_result = seo_result or {}
    serp_backlinks = serp_backlinks or {}
    serp_normalized = serp_normalized or {}
    signals = serp_normalized.get("intent_matched_signals") or {}

    candidates = [
        serp_backlinks.get("main_intent", ""),
        seo_result.get("intent_type", ""),
        final_intent_type or "",
        signals.get("primary_intent", ""),
    ]

    for raw in candidates:
        intent = (raw or "").strip().lower()
        if intent and intent != "unknown":
            return intent

    return "informational"


def _format_intent_matched_context(signals: IntentMatchedSerpSignals) -> str:
    if not signals:
        return "(No intent-matched SERP signals available — use query and candidates only.)"

    lines = []
    titles = signals.get("titles") or []
    questions = signals.get("questions") or []
    related = signals.get("related_topics") or []

    if titles:
        lines.append("**Intent-matched ranking titles:**")
        for t in titles[:12]:
            lines.append(f"- {t}")

    if questions:
        lines.append("\n**Intent-matched People Also Ask:**")
        for q in questions[:10]:
            lines.append(f"- {q}")

    if related:
        lines.append("\n**Intent-matched related searches:**")
        for r in related[:10]:
            lines.append(f"- {r}")

    return "\n".join(lines) if lines else "(No intent-matched SERP signals.)"


def _format_candidates(keywords_data: List[Dict[str, Any]]) -> str:
    lines = []
    for kw in keywords_data:
        keyword = kw.get("keyword", "")
        score = kw.get("score", 0)
        if keyword:
            lines.append(f"- {keyword} (tfidf_score={score})")
    return "\n".join(lines)


class KeywordClusteringService:
    """
    LLM-based keyword clustering aligned with primary search intent and
    intent-matched SERP signals (Semrush / Ahrefs topic-group methodology).
    """

    async def cluster_keywords(
        self,
        keywords_data: List[Dict[str, Any]],
        query: str,
        primary_intent: str,
        intent_matched_signals: Optional[IntentMatchedSerpSignals] = None,
    ) -> List[KeywordCluster]:
        if not keywords_data:
            return []

        if len(keywords_data) == 1:
            return [self._single_keyword_cluster(keywords_data[0], primary_intent)]

        intent_lower = (primary_intent or "informational").lower()
        if intent_lower not in _VALID_INTENTS:
            intent_lower = "informational"
        intent_upper = intent_lower.upper()

        try:
            clusters = await self._cluster_with_llm(
                keywords_data=keywords_data,
                query=query,
                primary_intent=intent_lower,
                primary_intent_upper=intent_upper,
                intent_matched_signals=intent_matched_signals or {},
            )
            if clusters:
                clusters.sort(key=lambda x: x["total_score"], reverse=True)
                logger.info(
                    "LLM clustered %d keywords into %d intent-aligned groups",
                    len(keywords_data),
                    len(clusters),
                )
                return clusters
        except Exception as e:
            logger.error(f"LLM keyword clustering failed: {e}")

        return [self._fallback_cluster(keywords_data, intent_lower)]

    async def _cluster_with_llm(
        self,
        keywords_data: List[Dict[str, Any]],
        query: str,
        primary_intent: str,
        primary_intent_upper: str,
        intent_matched_signals: IntentMatchedSerpSignals,
    ) -> List[KeywordCluster]:
        context_block = _format_intent_matched_context(intent_matched_signals)
        system_prompt = KEYWORD_CLUSTERING_SYSTEM_PROMPT.format(
            primary_intent=primary_intent,
            primary_intent_upper=primary_intent_upper,
            intent_matched_context=context_block,
        )

        human_prompt = (
            f"Target query: {query}\n\n"
            f"Keyword candidates to cluster ({len(keywords_data)}):\n"
            f"{_format_candidates(keywords_data)}\n\n"
            "Group into topic clusters. Use only keywords from the candidate list."
        )

        model = load_model().with_structured_output(KeywordClusteringLLMOutput)
        result: KeywordClusteringLLMOutput = await model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])

        candidate_map = {
            kw["keyword"].lower(): kw for kw in keywords_data if kw.get("keyword")
        }
        clusters: List[KeywordCluster] = []

        for group in result.clusters:
            cluster_keywords: List[Dict[str, Any]] = []
            for item in group.keywords:
                key = item.keyword.strip().lower()
                base = candidate_map.get(key)
                if base:
                    cluster_keywords.append({
                        **base,
                        "score": round(float(item.relevance_score), 2),
                    })
                elif item.keyword.strip():
                    cluster_keywords.append({
                        "keyword": item.keyword.strip(),
                        "score": round(float(item.relevance_score), 2),
                        "rank": 0,
                        "word_count": len(item.keyword.split()),
                    })

            if not cluster_keywords:
                continue

            cluster_keywords.sort(key=lambda x: x.get("score", 0), reverse=True)
            clusters.append({
                "cluster_name": group.cluster_name,
                "topic_theme": group.topic_theme,
                "keywords": cluster_keywords,
                "total_score": round(
                    sum(k.get("score", 0) for k in cluster_keywords), 2
                ),
                "main_intent": group.intent.lower(),
                "rationale": group.rationale,
            })

        return clusters

    def _single_keyword_cluster(
        self, kw: Dict[str, Any], primary_intent: str
    ) -> KeywordCluster:
        return {
            "cluster_name": kw.get("keyword", ""),
            "topic_theme": kw.get("keyword", ""),
            "keywords": [kw],
            "total_score": round(float(kw.get("score", 0)), 2),
            "main_intent": primary_intent.lower(),
            "rationale": "Single keyword cluster",
        }

    def _fallback_cluster(
        self, keywords_data: List[Dict[str, Any]], primary_intent: str
    ) -> KeywordCluster:
        sorted_kws = sorted(
            keywords_data, key=lambda x: x.get("score", 0), reverse=True
        )
        return {
            "cluster_name": sorted_kws[0].get("keyword", "cluster"),
            "topic_theme": "general",
            "keywords": sorted_kws,
            "total_score": round(sum(k.get("score", 0) for k in sorted_kws), 2),
            "main_intent": primary_intent,
            "rationale": "Fallback: single cluster after LLM failure",
        }
