import asyncio
import logging
import re
from typing import Any, Dict

from src.flow.states.rext import REXT
from src.services.keyword_clustering_service import (
    KeywordClusteringService,
    resolve_primary_intent,
)
from src.services.keyword_service import KeywordExtractor
from src.utils.stage_timing import timed_stage

logger = logging.getLogger(__name__)

_TOP_N_KEYWORDS = 30
_MAX_AUGMENTED_CANDIDATES = 50


def _clean_candidate_phrase(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    text = text.strip(" \t\r\n-_:;,.!?|/\\")
    return text.lower()


def _candidate_word_count(keyword: str) -> int:
    return len([word for word in keyword.split() if word])


def _candidate_from_phrase(
    keyword: str,
    score: float,
    source: str,
    rank: int,
) -> dict[str, Any] | None:
    keyword = _clean_candidate_phrase(keyword)
    if not keyword:
        return None
    if not re.search(r"[a-z]", keyword):
        return None
    word_count = _candidate_word_count(keyword)
    if word_count > 9:
        return None
    return {
        "keyword": keyword,
        "score": round(float(score), 2),
        "raw_tfidf": 0,
        "rank": rank,
        "word_count": word_count,
        "source": source,
    }


def _augment_keyword_candidates(
    extracted: list[dict[str, Any]],
    *,
    query: str,
    selected_topic: str,
    serp_normalized: dict[str, Any],
    intent_matched_signals: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}

    def add(item: dict[str, Any] | None) -> None:
        if not item:
            return
        key = item["keyword"].lower()
        previous = candidates.get(key)
        if previous is None or item.get("score", 0) > previous.get("score", 0):
            candidates[key] = item

    for item in extracted:
        add(
            {
                **item,
                "keyword": _clean_candidate_phrase(item.get("keyword")),
                "source": item.get("source") or "tfidf",
            }
        )

    rank_offset = len(candidates) + 1
    add(_candidate_from_phrase(query, 100, "target_query", rank_offset))
    add(_candidate_from_phrase(selected_topic, 100, "selected_topic", rank_offset + 1))

    related_topics = (
        intent_matched_signals.get("related_topics") or serp_normalized.get("related_topics") or []
    )
    for index, topic in enumerate(related_topics[:12], start=rank_offset + 2):
        add(_candidate_from_phrase(topic, 86, "serp_related_topic", index))

    questions = intent_matched_signals.get("questions") or serp_normalized.get("questions") or []
    for index, question in enumerate(questions[:10], start=rank_offset + 20):
        add(_candidate_from_phrase(question, 82, "serp_question", index))

    augmented = sorted(
        candidates.values(),
        key=lambda item: item.get("score", 0),
        reverse=True,
    )[:_MAX_AUGMENTED_CANDIDATES]

    logger.info(
        "Keyword candidate pool prepared: extracted=%d augmented=%d query=%r topic=%r",
        len(extracted),
        len(augmented),
        query,
        selected_topic,
    )
    return augmented


async def keyword_clustering_node(state: REXT) -> Dict[str, Any]:
    """
    LLM keyword clustering grounded in user-selected intent.

    - Primary intent: user selection from keyword_recommendation interrupt
      (serp_backlinks.main_intent), falling back to competitor LLM.
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

    # Use the user-selected intent stored in serp_backlinks.main_intent by
    # keyword_recommendation. Fall back to competitor-LLM resolution only when
    # the user hasn't made a selection (main_intent is absent or "unknown").
    serp_backlinks = seo_result.get("serp_backlinks", {})
    user_main_intent = (serp_backlinks.get("main_intent") or "").strip().lower()
    if user_main_intent and user_main_intent != "unknown":
        primary_intent = user_main_intent
    else:
        primary_intent = resolve_primary_intent(
            seo_result=seo_result,
            serp_normalized=serp_normalized,
            final_intent_type=state.get("final_intent_type"),
        )

    logger.info(
        "Starting LLM keyword clustering for query=%r intent=%s (user-selected)",
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

    # The tokenizing and TF-IDF pass is CPU work: in a worker thread, so the
    # event loop keeps serving every other request (rext-control#386). The NLTK
    # corpora it reads are loaded when keyword_service is imported, at start.
    def _extract():
        return KeywordExtractor().extract_keywords(
            clustering_serp,
            top_n=_TOP_N_KEYWORDS,
            intent_matched_titles=matched_titles or None,
            intent_matched_domains=list(matched_domains) if matched_domains else None,
        )

    extracted = await asyncio.to_thread(_extract)

    if not extracted:
        logger.warning("No keywords extracted for clustering")
        return {"seo_result": seo_result}

    content_state = state.get("content", {})
    content_type = content_state.get("content_type", "blog")
    selected_topic = content_state.get("selected_topic") or state.get("selected_topic") or query
    keyword_candidates = _augment_keyword_candidates(
        extracted,
        query=query,
        selected_topic=selected_topic,
        serp_normalized=serp_normalized,
        intent_matched_signals=intent_matched_signals,
    )

    service = KeywordClusteringService()
    with timed_stage("clustering", candidates=len(keyword_candidates)):
        clusters = await service.cluster_keywords(
            keywords_data=keyword_candidates,
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
