import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from langchain.messages import HumanMessage, SystemMessage

from src.flow.engines.serp import serp_cache
from src.flow.engines.serp.serp_intent_heuristics import (
    filter_paa_questions,
    filter_related_topics,
)
from src.flow.model.llm_manager import load_model
from src.flow.model.runaway import ainvoke_watched
from src.flow.model.structure.intent import BatchSEOIntentOutput, SEOIntentResult
from src.flow.prompts.system.intent import SEO_INTENT_SYSTEM_PROMPT
from src.flow.states.rext import REXT, SERPNORMALIZED, Competitor, IntentMatchedSerpSignals
from src.utils.stage_timing import timed_stage

logger = logging.getLogger(__name__)

_MAX_ORGANIC_FALLBACK_TITLES = 5
_MAX_RELATED = 10
_MAX_PAA = 8


def _build_competitor_groups(organic: List[dict]) -> Dict[str, dict]:
    domain_groups: Dict[str, dict] = {}

    for item in organic:
        url = item.get("link", "")
        domain = urlparse(url).netloc.replace("www.", "")
        if not domain:
            continue

        if domain not in domain_groups:
            domain_groups[domain] = {
                "top_positions": [],
                "total_occurrences": 0,
                "intent_distribution": {
                    "INFORMATIONAL": 0,
                    "COMMERCIAL": 0,
                    "NAVIGATIONAL": 0,
                    "TRANSACTIONAL": 0,
                },
                "freshness": {"recent": 0, "older": 0},
                "avg_snippet_length": 0.0,
                "featured_snippet": False,
                "is_brand": False,
                "top_result": item,
            }

        group = domain_groups[domain]
        group["top_positions"].append(item.get("position", 0))
        group["total_occurrences"] += 1

        if item.get("position", 999) < group["top_result"].get("position", 999):
            group["top_result"] = item

        snippet = item.get("snippet", "")
        group["avg_snippet_length"] += len(snippet) if snippet else 0

        date = item.get("date")
        if date:
            match = re.search(r"\b(20\d{2})\b", date)
            if match:
                year = match.group(1)
                if year.isdigit() and int(year) >= datetime.now(timezone.utc).year - 2:
                    group["freshness"]["recent"] += 1
                else:
                    group["freshness"]["older"] += 1
            else:
                group["freshness"]["older"] += 1
        else:
            group["freshness"]["older"] += 1

        if item.get("position") == 1:
            group["featured_snippet"] = True

    return domain_groups


async def _classify_competitor_intents(
    query: str, domain_groups: Dict[str, dict]
) -> Tuple[str, Dict[str, Any], List[str]]:
    """
    Single LLM call: primary keyword intent + per-competitor intent + brand flag + keyword suggestions.
    """
    competitor_data_list = []
    for domain, data in domain_groups.items():
        top_item = data["top_result"]
        competitor_data_list.append(
            {
                "domain": domain,
                "title": top_item.get("title", ""),
                "snippet": top_item.get("snippet", ""),
            }
        )

    final_intent_type = "UNKNOWN"
    if not competitor_data_list:
        try:
            batch_model = load_model().with_structured_output(BatchSEOIntentOutput)
            classification_results = await ainvoke_watched(
                batch_model,
                [
                    SystemMessage(
                        content=(
                            SEO_INTENT_SYSTEM_PROMPT
                            + f"\nNo competitor data is available. Your only task is to "
                            f"determine the primary search intent for the keyword and suggest related keywords. "
                            f"Return an empty results list and populate "
                            f"final_intent_type and suggested_keywords only. Keyword: {query}"
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Query: {query}\n\n"
                            f"No SERP competitors were found. "
                            f"Based on the query alone, classify its primary intent, "
                            f"suggest related keywords, and return an empty results list."
                        )
                    ),
                ],
                stage="intent",
                schema=BatchSEOIntentOutput,
            )
            final_intent_type = classification_results.final_intent_type
            suggested_keywords = classification_results.suggested_keywords or []
            logger.info(
                f"Intent derived from query only (no competitors): {final_intent_type}, "
                f"suggested {len(suggested_keywords)} keywords"
            )
            return final_intent_type, {}, suggested_keywords
        except Exception as e:
            logger.error(f"Error in query-only intent classification: {e}")

    batch_model = load_model().with_structured_output(BatchSEOIntentOutput)
    human_content = f"Query: {query}\n\nClassify the following competitors:\n"
    for i, comp in enumerate(competitor_data_list):
        human_content += (
            f"--- Competitor {i + 1} ---\n"
            f"Domain: {comp['domain']}\n"
            f"Title: {comp['title']}\n"
            f"Snippet: {comp['snippet']}\n\n"
        )

    classification_results = await ainvoke_watched(
        batch_model,
        [
            SystemMessage(
                content=SEO_INTENT_SYSTEM_PROMPT
                + f"\nClassify each competitor, return the primary intent of the keyword, "
                f"and suggest related keywords. Keyword: {query}"
            ),
            HumanMessage(content=human_content),
        ],
        stage="intent",
        schema=BatchSEOIntentOutput,
    )

    final_intent_type = classification_results.final_intent_type
    suggested_keywords = classification_results.suggested_keywords or []
    logger.info(f"LLM suggested {len(suggested_keywords)} keywords for query: {query}")
    return (
        final_intent_type,
        {res.domain: res for res in classification_results.results},
        suggested_keywords,
    )


async def _classify_cached(
    query: str, domain_groups: Dict[str, dict]
) -> Tuple[str, Dict[str, Any], List[str]]:
    """_classify_competitor_intents, through the day's cache (serp_cache): the same keyword
    and the same rows get the same answer without another model call."""
    with timed_stage("intent") as timing:
        key = serp_cache.intent_key(query, domain_groups)
        cached = await serp_cache.read(key)
        if cached:
            timing["cache"] = "hit"
            results = {d: SEOIntentResult(**r) for d, r in (cached.get("results") or {}).items()}
            return cached["final_intent_type"], results, cached.get("suggested_keywords") or []
        timing["cache"] = "miss"
        final_intent_type, results_map, suggested = await _classify_competitor_intents(
            query, domain_groups
        )
        if final_intent_type and final_intent_type != "UNKNOWN":
            await serp_cache.write(
                key,
                {
                    "final_intent_type": final_intent_type,
                    "results": {d: r.model_dump() for d, r in results_map.items()},
                    "suggested_keywords": suggested,
                },
            )
        return final_intent_type, results_map, suggested


def build_intent_matched_signals_from_competitors(
    query: str,
    primary_intent: str,
    domain_groups: Dict[str, dict],
    results_map: Dict[str, Any],
    serp_normalized: SERPNORMALIZED,
) -> IntentMatchedSerpSignals:
    """
    Build clustering context without a second LLM call.

    Titles/snippets: only from competitors whose classified intent equals
    the keyword's primary intent (from the competitor batch LLM call).

    Related topics & PAA: heuristic filters aligned to primary intent.
    """
    intent_upper = (primary_intent or "UNKNOWN").upper()
    intent_lower = intent_upper.lower()

    titles: List[str] = []
    snippets: List[str] = []
    matched_domains: List[str] = []

    for domain, data in domain_groups.items():
        res = results_map.get(domain)
        if not res or res.intent.upper() != intent_upper:
            continue

        matched_domains.append(domain)
        top = data["top_result"]
        title = (top.get("title") or "").strip()
        snippet = (top.get("snippet") or "").strip()

        if title and title not in titles:
            titles.append(title)
        if snippet and snippet not in snippets:
            snippets.append(snippet)

    if not titles:
        logger.warning(
            "No intent-matched competitor titles for %s; using top organic fallback",
            intent_upper,
        )
        for row in (serp_normalized.get("normalize_results") or [])[:_MAX_ORGANIC_FALLBACK_TITLES]:
            t = (row.get("title") or "").strip()
            if t and t not in titles:
                titles.append(t)

    related = filter_related_topics(
        serp_normalized.get("related_topics") or [],
        intent_lower,
        query,
        max_items=_MAX_RELATED,
    )
    questions = filter_paa_questions(
        serp_normalized.get("questions") or [],
        intent_lower,
        query,
        max_items=_MAX_PAA,
    )

    logger.info(
        "Intent-matched clustering context for %s: %d competitor titles, "
        "%d domains, %d PAA, %d related",
        intent_upper,
        len(titles),
        len(matched_domains),
        len(questions),
        len(related),
    )

    return {
        "primary_intent": intent_upper,
        "titles": titles,
        "snippets": snippets,
        "questions": questions,
        "related_topics": related,
        "matched_domains": matched_domains,
    }


async def extract_competitors_from_serp(state: REXT) -> Dict[str, Any]:
    """
    Extract competitors, classify intent (one LLM call), and build
    intent-matched SERP context for keyword clustering.
    """
    logger.info("Starting competitor extraction from SERP")
    serp_result = state.get("serp_result", {})
    serp_normalized: SERPNORMALIZED = state.get("serp_normalized") or {}
    organic = serp_result.get("organic_results", [])
    query = state.get("serp_payload", {}).get("query", "")

    domain_groups = _build_competitor_groups(organic)
    final_intent_type = "UNKNOWN"
    results_map: Dict[str, Any] = {}
    llm_suggested_keywords: List[str] = []

    try:
        final_intent_type, results_map, llm_suggested_keywords = await _classify_cached(
            query, domain_groups
        )
        for domain, data in domain_groups.items():
            res = results_map.get(domain)
            if res:
                intent = res.intent.upper()
                if intent in data["intent_distribution"]:
                    data["intent_distribution"][intent] = 1
                data["is_brand"] = res.is_brand
            else:
                logger.warning(f"No classification result found for domain: {domain}")
    except Exception as e:
        logger.error(f"Error in batch competitor classification: {e}")

    # Backfill related_topics with LLM suggestions when SERP returned none
    existing_related = serp_normalized.get("related_topics") or []
    if not existing_related and llm_suggested_keywords:
        serp_normalized = {**serp_normalized, "related_topics": llm_suggested_keywords}
        logger.info(
            f"Backfilled {len(llm_suggested_keywords)} LLM-suggested keywords into related_topics"
        )

    intent_matched_signals = build_intent_matched_signals_from_competitors(
        query=query,
        primary_intent=final_intent_type,
        domain_groups=domain_groups,
        results_map=results_map,
        serp_normalized=serp_normalized,
    )

    competitors: List[Competitor] = []
    for domain, data in domain_groups.items():
        total_snippets = data["total_occurrences"]
        data["avg_snippet_length"] = (
            data["avg_snippet_length"] / total_snippets if total_snippets else 0.0
        )
        competitors.append(
            Competitor(
                domain=domain,
                top_positions=data["top_positions"],
                total_occurrences=data["total_occurrences"],
                intent_distribution=data["intent_distribution"],
                freshness=data["freshness"],
                avg_snippet_length=data["avg_snippet_length"],
                featured_snippet=data["featured_snippet"],
                is_brand=data["is_brand"],
            )
        )

    competitors.sort(key=lambda x: min(x["top_positions"]))
    logger.info(f"Extracted {len(competitors)} competitors from SERP")

    return {
        "competitors": competitors,
        "final_intent_type": final_intent_type,
        "serp_normalized": {
            **serp_normalized,
            "intent_matched_signals": intent_matched_signals,
        },
        "seo_result": {
            "intent_type": final_intent_type,
        },
    }
