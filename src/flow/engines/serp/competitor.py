import re
import logging
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

from langchain.messages import SystemMessage, HumanMessage

from src.flow.states.rext import REXT, Competitor, IntentMatchedSerpSignals
from src.flow.model.llm_manager import load_model
from src.flow.prompts.system.intent import SEO_INTENT_SYSTEM_PROMPT
from src.flow.model.structure.intent import (
    BatchSEOIntentOutput,
    BatchSerpSignalIntentOutput,
)
from src.flow.states.rext import SERPNORMALIZED

logger = logging.getLogger(__name__)

_MAX_ORGANIC_FOR_INTENT = 15
_MAX_PAA_FOR_INTENT = 12
_MAX_RELATED_FOR_INTENT = 10


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
) -> Tuple[str, Dict[str, Any]]:
    competitor_data_list = []
    for domain, data in domain_groups.items():
        top_item = data["top_result"]
        competitor_data_list.append({
            "domain": domain,
            "title": top_item.get("title", ""),
            "snippet": top_item.get("snippet", ""),
        })

    final_intent_type = "UNKNOWN"
    if not competitor_data_list:
        return final_intent_type, {}

    batch_model = load_model().with_structured_output(BatchSEOIntentOutput)
    human_content = (
        f"Query: {query}\n\nClassify the following competitors:\n"
    )
    for i, comp in enumerate(competitor_data_list):
        human_content += (
            f"--- Competitor {i + 1} ---\n"
            f"Domain: {comp['domain']}\n"
            f"Title: {comp['title']}\n"
            f"Snippet: {comp['snippet']}\n\n"
        )

    classification_results = await batch_model.ainvoke([
        SystemMessage(
            content=SEO_INTENT_SYSTEM_PROMPT
            + f"\nClassify each competitor in the list and return the primary intent "
            f"of the keyword. Keyword: {query}"
        ),
        HumanMessage(content=human_content),
    ])

    final_intent_type = classification_results.final_intent_type
    return final_intent_type, {
        res.domain: res for res in classification_results.results
    }


def _collect_serp_signals_for_intent(
    serp_normalized: SERPNORMALIZED,
) -> List[Dict[str, str]]:
    """Build a flat list of SERP signals to classify (titles, PAA, related topics)."""
    signals: List[Dict[str, str]] = []

    for idx, result in enumerate(
        (serp_normalized.get("normalize_results") or [])[:_MAX_ORGANIC_FOR_INTENT]
    ):
        title = (result.get("title") or "").strip()
        if title:
            signals.append({
                "signal_id": f"title_{idx}",
                "signal_type": "title",
                "text": title,
            })

    for idx, question in enumerate(
        (serp_normalized.get("questions") or [])[:_MAX_PAA_FOR_INTENT]
    ):
        q = (question or "").strip() if isinstance(question, str) else ""
        if q:
            signals.append({
                "signal_id": f"paa_{idx}",
                "signal_type": "paa",
                "text": q,
            })

    for idx, topic in enumerate(
        (serp_normalized.get("related_topics") or [])[:_MAX_RELATED_FOR_INTENT]
    ):
        t = (topic or "").strip() if isinstance(topic, str) else ""
        if t:
            signals.append({
                "signal_id": f"related_{idx}",
                "signal_type": "related_topic",
                "text": t,
            })

    return signals


async def _classify_and_filter_serp_signals(
    query: str,
    primary_intent: str,
    serp_normalized: SERPNORMALIZED,
) -> IntentMatchedSerpSignals:
    """
    Classify titles, PAA questions, and related topics; keep only those matching
    the primary keyword intent (used as clustering ground truth).
    """
    intent_upper = (primary_intent or "UNKNOWN").upper()
    empty: IntentMatchedSerpSignals = {
        "primary_intent": intent_upper,
        "titles": [],
        "questions": [],
        "related_topics": [],
    }

    signals = _collect_serp_signals_for_intent(serp_normalized)
    if not signals or intent_upper == "UNKNOWN":
        return empty

    batch_model = load_model().with_structured_output(BatchSerpSignalIntentOutput)
    human_content = f"Query: {query}\n\nClassify each SERP signal:\n"
    for sig in signals:
        human_content += (
            f"--- Signal {sig['signal_id']} ({sig['signal_type']}) ---\n"
            f"Text: {sig['text']}\n\n"
        )

    try:
        classification = await batch_model.ainvoke([
            SystemMessage(
                content=SEO_INTENT_SYSTEM_PROMPT
                + "\nClassify each SERP signal (title, PAA question, or related search). "
                "Use the Text and Query context only."
            ),
            HumanMessage(content=human_content),
        ])
    except Exception as e:
        logger.error(f"SERP signal intent classification failed: {e}")
        return empty

    matched: IntentMatchedSerpSignals = {
        "primary_intent": intent_upper,
        "titles": [],
        "questions": [],
        "related_topics": [],
    }

    signal_lookup = {s["signal_id"]: s for s in signals}
    for res in classification.results:
        if res.intent.upper() != intent_upper:
            continue
        original = signal_lookup.get(res.signal_id)
        if not original:
            continue
        text = original["text"]
        stype = original["signal_type"]
        if stype == "title":
            matched["titles"].append(text)
        elif stype == "paa":
            matched["questions"].append(text)
        elif stype == "related_topic":
            matched["related_topics"].append(text)

    logger.info(
        "Intent-matched SERP signals for %s: %d titles, %d PAA, %d related",
        intent_upper,
        len(matched["titles"]),
        len(matched["questions"]),
        len(matched["related_topics"]),
    )
    return matched


async def extract_competitors_from_serp(state: REXT) -> Dict[str, Any]:
    """
    Extract competitors from SERP, classify intent via LLM, and build
    intent-matched SERP signals (titles, PAA, related topics) for keyword clustering.
    """
    logger.info("Starting competitor extraction from SERP")
    serp_result = state.get("serp_result", {})
    serp_normalized: SERPNORMALIZED = state.get("serp_normalized") or {}
    organic = serp_result.get("organic_results", [])
    query = state.get("serp_payload", {}).get("query", "")

    domain_groups = _build_competitor_groups(organic)
    final_intent_type = "UNKNOWN"
    results_map: Dict[str, Any] = {}

    try:
        final_intent_type, results_map = await _classify_competitor_intents(
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

    intent_matched_signals = await _classify_and_filter_serp_signals(
        query, final_intent_type, serp_normalized
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
