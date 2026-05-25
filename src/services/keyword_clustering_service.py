import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from langchain.messages import HumanMessage, SystemMessage

from src.flow.model.llm_manager import load_model
from src.flow.model.structure.keyword_clustering import KeywordClusteringLLMOutput
from src.flow.prompts.system.keyword_clustering import KEYWORD_CLUSTERING_SYSTEM_PROMPT
from src.flow.states.rext import IntentMatchedSerpSignals
from src.flow.states.seo_state import KeywordCluster

logger = logging.getLogger(__name__)

_VALID_INTENTS = frozenset({
    "informational", "commercial", "navigational", "transactional",
})

_MAX_CANDIDATES_FOR_LLM = 30
_MIN_CLUSTER_OVERALL_SCORE = 62
_MIN_CLUSTER_INTENT_SCORE = 78
_MIN_CLUSTER_PAGE_FIT_SCORE = 60
_MIN_TOPIC_PROMISE_SCORE = 32

_TRANSACTIONAL_CONTENT_TYPES = {
    "checkout-page",
    "coupon-page",
    "demo-page",
    "pricing-page",
    "sales-page",
    "service-page",
    "signup-page",
}

_COMMERCIAL_CONTENT_TYPES = {
    "alternatives",
    "best-tools",
    "buying-guide",
    "comparison",
    "in-depth-review",
    "product-roundup",
    "pros-cons",
}

_NAVIGATIONAL_CONTENT_TYPES = {
    "about-us",
    "brand-page",
    "contact-us",
    "documentation",
    "feature-overview",
    "help-center",
    "login-guide",
    "product-homepage",
}

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "how", "in", "into", "is", "it", "its", "of", "on",
    "or", "that", "the", "their", "this", "to", "was", "were", "what",
    "when", "where", "which", "who", "why", "with", "your",
}

_FRAGMENT_EDGE_WORDS = {
    "and", "or", "for", "to", "of", "with", "from", "the", "a", "an",
    "vs", "versus", "near",
}

_LOW_QUALITY_PATTERNS = (
    "click here",
    "read more",
    "learn more",
    "official site",
    "privacy policy",
    "terms conditions",
    "cookie policy",
)


def _normalize_content_type(content_type: str | None) -> str:
    normalized = str(content_type or "").strip().lower()
    normalized = normalized.replace("_", "-").replace(" ", "-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    normalized = normalized.strip("-")
    if normalized in {"article", "post", "blog-post", "blogpost", "listicle"}:
        return "blog"
    if normalized in {"landing", "landingpage"}:
        return "landing-page"
    if normalized in {"transactional", "transactional-page", "transactional-pages"}:
        return "transactional-page"
    return normalized or "blog"


def _content_type_group(content_type: str | None) -> str:
    key = _normalize_content_type(content_type)
    if key == "faq":
        return "faq"
    if key in {"tutorial", "how-to-guide", "checklist"}:
        return "tutorial"
    if key == "glossary":
        return "glossary"
    if key == "landing-page":
        return "landing-page"
    if key in _TRANSACTIONAL_CONTENT_TYPES or key == "transactional-page":
        return "transactional"
    if key in _COMMERCIAL_CONTENT_TYPES:
        return "comparison" if key == "comparison" else "commercial"
    if key in _NAVIGATIONAL_CONTENT_TYPES:
        return "navigational"
    if key == "blog":
        return "blog"
    return "other"


def _content_type_rules(content_type: str | None) -> Dict[str, Any]:
    key = _normalize_content_type(content_type)
    group = _content_type_group(key)
    base = {
        "key": key,
        "group": group,
        "page_types": {"article", "guide"},
        "min_keywords": 2,
        "max_keywords": 6,
        "max_keyword_words": 8,
        "allow_single_word": False,
        "guidance": (
            "Use compact informational clusters that can be handled on one page. "
            "Map broad themes to H2s and long-tail support to H3/body copy."
        ),
    }

    if group == "blog":
        base.update({
            "page_types": {"article", "blog-post", "guide", "faq", "how-to"},
            "guidance": (
                "Blog clusters should support one article promise. Use H2s for major "
                "topic buckets, H3s for long-tail questions, and body copy for variants."
            ),
        })
    elif group == "faq":
        base.update({
            "page_types": {"faq", "help-answer"},
            "min_keywords": 1,
            "max_keywords": 4,
            "guidance": (
                "FAQ clusters should be question-led and answerable by one FAQ page. "
                "Use H2s for question groups and H3s for individual questions."
            ),
        })
    elif group == "comparison":
        base.update({
            "page_types": {"comparison", "review", "commercial-list"},
            "guidance": (
                "Comparison clusters should share a buyer evaluation intent: vs, "
                "alternatives, feature differences, pricing, use cases, and tradeoffs."
            ),
        })
    elif group == "tutorial":
        base.update({
            "page_types": {"how-to", "tutorial", "guide", "troubleshooting"},
            "guidance": (
                "Tutorial clusters should follow the task flow. Use H2s for stages, "
                "H3s for steps, examples, checks, or troubleshooting."
            ),
        })
    elif group == "glossary":
        base.update({
            "page_types": {"glossary", "definition"},
            "min_keywords": 1,
            "max_keywords": 5,
            "allow_single_word": True,
            "guidance": (
                "Glossary clusters should group terms that one definition page or "
                "term section can satisfy without mixing unrelated concepts."
            ),
        })
    elif group == "landing-page":
        base.update({
            "page_types": {"landing-page", "service-page", "commercial-page"},
            "min_keywords": 1,
            "max_keywords": 5,
            "guidance": (
                "Landing page clusters should fit the conversion journey: problem, "
                "solution, proof, objections, offer, and action."
            ),
        })
    elif group == "transactional":
        base.update({
            "page_types": {"transactional-page", "service-page", "pricing-page", "checkout"},
            "min_keywords": 1,
            "max_keywords": 5,
            "guidance": (
                "Transactional clusters should target purchase, signup, pricing, demo, "
                "coupon, checkout, or service-intent terms only."
            ),
        })
    elif group == "navigational":
        base.update({
            "page_types": {"navigation-page", "support-page", "documentation", "brand-page"},
            "min_keywords": 1,
            "max_keywords": 5,
            "guidance": (
                "Navigational clusters should help users reach a product, brand, docs, "
                "login, support, or contact path."
            ),
        })
    elif group == "commercial":
        base.update({
            "page_types": {"comparison", "review", "commercial-list", "buying-guide"},
            "guidance": (
                "Commercial clusters should support evaluation: best options, reviews, "
                "alternatives, benefits, objections, features, pricing, and use cases."
            ),
        })

    return base


def _content_type_rule_block(content_type: str | None) -> str:
    rules = _content_type_rules(content_type)
    return (
        f"Content type: {rules['key']} ({rules['group']})\n"
        f"Allowed SERP page types: {', '.join(sorted(rules['page_types']))}\n"
        f"Cluster size target: {rules['min_keywords']}-{rules['max_keywords']} keywords\n"
        f"Guidance: {rules['guidance']}"
    )


def _clean_keyword(value: Any) -> str:
    keyword = " ".join(str(value or "").strip().split())
    keyword = keyword.strip(" \t\r\n-_:;,.!?|/\\")
    return keyword.lower()


def _keyword_key(keyword: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", keyword.lower()).strip()


def _meaningful_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {
        token
        for token in tokens
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _serp_context_text(signals: IntentMatchedSerpSignals | None) -> str:
    signals = signals or {}
    parts: list[str] = []
    for key in ("titles", "snippets", "questions", "related_topics"):
        parts.extend(str(item) for item in signals.get(key) or [])
    return " ".join(parts)


def _is_query_or_topic_keyword(keyword: str, query: str, selected_topic: str) -> bool:
    key = _keyword_key(keyword)
    return key in {_keyword_key(query), _keyword_key(selected_topic)}


def _is_low_quality_keyword(
    keyword: str,
    rules: Dict[str, Any],
    query: str,
    selected_topic: str,
) -> bool:
    if not keyword or len(keyword) < 3:
        return True
    if re.search(r"https?://|www\.|\.com\b|\.net\b|\.org\b", keyword):
        return True
    if any(pattern in keyword for pattern in _LOW_QUALITY_PATTERNS):
        return True
    if not re.search(r"[a-z]", keyword):
        return True
    if re.search(r"[_=+#@{}[\]<>]", keyword):
        return True

    words = keyword.split()
    if len(words) > int(rules.get("max_keyword_words", 8)):
        return True
    if words[0] in _FRAGMENT_EDGE_WORDS or words[-1] in _FRAGMENT_EDGE_WORDS:
        return True
    if len(words) > 1 and len(set(words)) == 1:
        return True
    if len(words) == 1:
        if rules.get("allow_single_word"):
            return False
        return not _is_query_or_topic_keyword(keyword, query, selected_topic)
    if len(keyword) / max(len(words), 1) < 2.5:
        return True
    return False


def _infer_keyword_intent_and_page_type(
    keyword: str,
    primary_intent: str,
    content_type: str,
) -> tuple[str, str]:
    lower = f" {keyword.lower()} "
    group = _content_type_group(content_type)

    transactional_markers = (
        " buy ", " order ", " pricing ", " price ", " cost ", " coupon ",
        " discount ", " deal ", " checkout ", " sign up ", " signup ",
        " demo ", " quote ", " hire ", " service ", " near me ",
    )
    commercial_markers = (
        " best ", " top ", " review ", " reviews ", " vs ", " versus ",
        " compare ", " comparison ", " alternative ", " alternatives ",
        " software ", " tool ", " tools ", " platform ", " features ",
    )
    navigational_markers = (
        " login ", " sign in ", " contact ", " support ", " docs ",
        " documentation ", " help center ", " website ", " app ",
    )

    if any(marker in lower for marker in navigational_markers):
        return "navigational", "navigation-page"

    if any(marker in lower for marker in transactional_markers):
        if primary_intent == "transactional" or group in {"transactional", "landing-page"}:
            if " pricing " in lower or " price " in lower or " cost " in lower:
                return "transactional", "pricing-page"
            if " coupon " in lower or " discount " in lower or " deal " in lower:
                return "transactional", "coupon-page"
            return "transactional", "transactional-page"
        return "commercial", "commercial-page"

    if any(marker in lower for marker in commercial_markers):
        if (
            " vs " in lower
            or " versus " in lower
            or " compare " in lower
            or " comparison " in lower
        ):
            return "commercial", "comparison"
        if " review " in lower or " reviews " in lower:
            return "commercial", "review"
        return "commercial", "commercial-list"

    if keyword.startswith(("how to ", "how do ", "how can ")) or " tutorial" in lower:
        return "informational", "how-to"
    if (
        keyword.startswith(("what is ", "what are "))
        or " definition" in lower
        or " meaning" in lower
    ):
        return "informational", "definition"
    if keyword.endswith("?") or keyword.startswith(
        ("can ", "does ", "do ", "is ", "are ", "when ", "where ", "why ", "which ")
    ):
        return "informational", "faq"

    default_page_type = {
        "faq": "faq",
        "tutorial": "how-to",
        "glossary": "definition",
        "comparison": "comparison",
        "commercial": "commercial-list",
        "landing-page": "landing-page",
        "transactional": "transactional-page",
        "navigational": "navigation-page",
    }.get(group, "article")
    return primary_intent or "informational", default_page_type


def _intent_match_score(keyword_intent: str, primary_intent: str) -> float:
    keyword_intent = (keyword_intent or "").lower()
    primary_intent = (primary_intent or "informational").lower()
    if keyword_intent == primary_intent:
        return 100.0
    if not keyword_intent or keyword_intent == "unknown":
        return 76.0
    if {keyword_intent, primary_intent} == {"commercial", "transactional"}:
        return 70.0
    return 20.0


def _page_type_fit_score(page_type: str, rules: Dict[str, Any]) -> float:
    page_type = (page_type or "").lower()
    allowed = set(rules.get("page_types") or [])
    group = rules.get("group")
    if page_type in allowed:
        return 100.0
    if group == "blog" and page_type in {"faq", "how-to", "definition", "commercial-list"}:
        return 72.0
    if group in {"commercial", "comparison"} and page_type in {
        "commercial-page", "commercial-list", "comparison", "review", "pricing-page",
    }:
        return 84.0
    if group in {"landing-page", "transactional"} and page_type in {
        "commercial-page", "pricing-page", "transactional-page", "service-page",
    }:
        return 82.0
    if group == "tutorial" and page_type in {"article", "guide", "faq"}:
        return 70.0
    return 42.0


def _topic_promise_score(
    keyword: str,
    query: str,
    selected_topic: str,
    intent_matched_signals: IntentMatchedSerpSignals | None,
) -> float:
    keyword_key = _keyword_key(keyword)
    query_key = _keyword_key(query)
    topic_key = _keyword_key(selected_topic)
    if keyword_key and keyword_key in {query_key, topic_key}:
        return 100.0

    anchor_tokens = _meaningful_tokens(f"{query} {selected_topic}")
    keyword_tokens = _meaningful_tokens(keyword)
    if not keyword_tokens:
        return 0.0
    if not anchor_tokens:
        return 72.0

    overlap = keyword_tokens & anchor_tokens
    if overlap:
        ratio = len(overlap) / max(1, min(len(keyword_tokens), len(anchor_tokens)))
        return min(100.0, 35.0 + (65.0 * ratio))

    serp_tokens = _meaningful_tokens(_serp_context_text(intent_matched_signals))
    serp_overlap = keyword_tokens & serp_tokens
    if serp_overlap:
        ratio = len(serp_overlap) / max(1, len(keyword_tokens))
        return min(72.0, 38.0 + (34.0 * ratio))

    return 0.0


def _serp_overlap_score(
    keywords: list[dict[str, Any]],
    cluster_name: str,
    intent_matched_signals: IntentMatchedSerpSignals | None,
) -> float:
    context = _serp_context_text(intent_matched_signals).lower()
    if not context:
        return 62.0

    scores: list[float] = []
    for item in keywords:
        keyword = _clean_keyword(item.get("keyword"))
        if not keyword:
            continue
        if keyword in context:
            scores.append(100.0)
            continue
        tokens = _meaningful_tokens(keyword)
        if not tokens:
            continue
        context_tokens = _meaningful_tokens(context)
        ratio = len(tokens & context_tokens) / max(1, len(tokens))
        scores.append(25.0 + (75.0 * ratio))

    cluster_tokens = _meaningful_tokens(cluster_name)
    context_tokens = _meaningful_tokens(context)
    if cluster_tokens:
        scores.append(25.0 + (75.0 * (len(cluster_tokens & context_tokens) / len(cluster_tokens))))

    return round(sum(scores) / len(scores), 2) if scores else 0.0


def _cluster_strength_score(cluster: dict[str, Any], rules: Dict[str, Any]) -> float:
    keywords = cluster.get("keywords") or []
    if not keywords:
        return 0.0

    scores = [float(item.get("score") or 0) for item in keywords]
    avg_keyword_score = sum(scores) / len(scores)
    min_size = int(rules.get("min_keywords", 2))
    max_size = int(rules.get("max_keywords", 6))
    size = len(keywords)
    if min_size <= size <= max_size:
        size_score = 100.0
    elif size == 1 and min_size == 1:
        size_score = 92.0
    elif size == 1:
        size_score = 68.0
    else:
        size_score = 70.0

    cluster_tokens = _meaningful_tokens(cluster.get("cluster_name", ""))
    cohesion_scores = []
    for item in keywords:
        tokens = _meaningful_tokens(item.get("keyword", ""))
        if tokens and cluster_tokens:
            cohesion_scores.append(
                len(tokens & cluster_tokens)
                / max(1, min(len(tokens), len(cluster_tokens)))
            )
    cohesion = (sum(cohesion_scores) / len(cohesion_scores) * 100) if cohesion_scores else 70.0

    return round((avg_keyword_score * 0.45) + (size_score * 0.25) + (cohesion * 0.30), 2)


def _page_fit_score(page_types: list[str], rules: Dict[str, Any]) -> float:
    if not page_types:
        return 0.0
    counts = Counter(page_types)
    dominant_count = counts.most_common(1)[0][1]
    dominant_ratio = dominant_count / len(page_types)
    avg_fit = (
        sum(_page_type_fit_score(page_type, rules) for page_type in page_types)
        / len(page_types)
    )
    return round((dominant_ratio * 55.0) + (avg_fit * 0.45), 2)


def _title_case_heading(text: str) -> str:
    small_words = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "to", "vs"}
    words = _clean_keyword(text).split()
    titled = []
    for index, word in enumerate(words):
        if index > 0 and word in small_words:
            titled.append(word.upper() if word == "vs" else word)
        else:
            titled.append(
                word.upper()
                if len(word) <= 3 and word in {"seo", "crm", "api"}
                else word.capitalize()
            )
    return " ".join(titled)


def _natural_heading(cluster_name: str, content_type: str, placement: str) -> str:
    cluster_name = _clean_keyword(cluster_name)
    group = _content_type_group(content_type)
    heading = _title_case_heading(cluster_name)
    if group == "faq" and not heading.endswith("?"):
        return f"{heading} Questions"
    if group == "glossary" and placement.upper() != "H2":
        return f"What Is {heading}?"
    if group == "tutorial" and not cluster_name.startswith("how"):
        return f"How to Use {heading}"
    return heading


def _outline_placement(
    cluster: dict[str, Any],
    rules: Dict[str, Any],
    overall_score: float,
) -> str:
    explicit = str(cluster.get("outline_placement") or "").strip().lower()
    if explicit in {"h2", "h3", "body"}:
        return explicit.upper() if explicit != "body" else "body"
    keyword_count = len(cluster.get("keywords") or [])
    group = rules.get("group")
    if overall_score >= 78 and keyword_count >= max(1, int(rules.get("min_keywords", 1))):
        return "H2"
    if group in {"faq", "tutorial", "glossary"} or overall_score >= 68:
        return "H3"
    return "body"


def _filter_keyword_candidates(
    keywords_data: List[Dict[str, Any]],
    query: str,
    primary_intent: str,
    intent_matched_signals: IntentMatchedSerpSignals | None,
    content_type: str,
    selected_topic: str,
) -> List[Dict[str, Any]]:
    rules = _content_type_rules(content_type)
    deduped: dict[str, Dict[str, Any]] = {}

    for raw in keywords_data:
        keyword = _clean_keyword(raw.get("keyword"))
        if _is_low_quality_keyword(keyword, rules, query, selected_topic):
            continue

        inferred_intent, page_type = _infer_keyword_intent_and_page_type(
            keyword,
            primary_intent,
            content_type,
        )
        intent_score = _intent_match_score(inferred_intent, primary_intent)
        topic_score = _topic_promise_score(
            keyword,
            query,
            selected_topic,
            intent_matched_signals,
        )
        page_fit = _page_type_fit_score(page_type, rules)
        source_score = float(raw.get("score") or 0)
        quality_score = round(
            (intent_score * 0.32)
            + (topic_score * 0.28)
            + (page_fit * 0.20)
            + (source_score * 0.20),
            2,
        )

        if intent_score < 60:
            continue
        if topic_score < 25 and source_score < 70:
            continue
        if quality_score < 48:
            continue

        item = {
            **raw,
            "keyword": keyword,
            "score": round(max(source_score, quality_score), 2),
            "quality_score": quality_score,
            "intent_match_score": round(intent_score, 2),
            "topic_promise_score": round(topic_score, 2),
            "content_type_fit_score": round(page_fit, 2),
            "inferred_intent": inferred_intent,
            "likely_serp_page_type": page_type,
            "word_count": len(keyword.split()),
        }
        key = _keyword_key(keyword)
        previous = deduped.get(key)
        if previous is None or item["score"] > previous.get("score", 0):
            deduped[key] = item

    filtered = sorted(deduped.values(), key=lambda item: item.get("score", 0), reverse=True)
    return filtered[:_MAX_CANDIDATES_FOR_LLM]


def resolve_primary_intent(
    seo_result: Optional[Dict[str, Any]] = None,
    serp_normalized: Optional[Dict[str, Any]] = None,
    final_intent_type: Optional[str] = None,
    **_ignored,
) -> str:
    """
    Primary intent from competitor LLM only (not DataForSEO).

    Order: final_intent_type → seo_result.intent_type → intent_matched_signals.
    """
    seo_result = seo_result or {}
    serp_normalized = serp_normalized or {}
    signals = serp_normalized.get("intent_matched_signals") or {}

    candidates = [
        final_intent_type or "",
        seo_result.get("intent_type", ""),
        signals.get("primary_intent", ""),
    ]

    for raw in candidates:
        intent = (raw or "").strip().lower()
        if intent and intent != "unknown":
            return intent

    return "informational"


def _format_intent_matched_context(signals: IntentMatchedSerpSignals) -> str:
    if not signals:
        return "(No intent-matched competitor context — use query and candidates only.)"

    lines = []
    titles = signals.get("titles") or []
    snippets = signals.get("snippets") or []
    questions = signals.get("questions") or []
    related = signals.get("related_topics") or []
    domains = signals.get("matched_domains") or []

    if domains:
        lines.append(f"**Intent-matched competitor domains ({len(domains)}):**")
        lines.append(", ".join(domains[:12]))

    if titles:
        lines.append("\n**Titles (intent-matched competitors only):**")
        for t in titles[:12]:
            lines.append(f"- {t}")

    if snippets:
        lines.append("\n**Snippets (intent-matched competitors):**")
        for s in snippets[:6]:
            lines.append(f"- {s[:200]}{'…' if len(s) > 200 else ''}")

    if questions:
        lines.append("\n**People Also Ask (heuristic, intent-aligned):**")
        for q in questions[:8]:
            lines.append(f"- {q}")

    if related:
        lines.append("\n**Related searches (heuristic, intent-aligned):**")
        for r in related[:8]:
            lines.append(f"- {r}")

    return "\n".join(lines) if lines else "(No intent-matched competitor context.)"


def _format_candidates(keywords_data: List[Dict[str, Any]]) -> str:
    lines = []
    for kw in keywords_data[:_MAX_CANDIDATES_FOR_LLM]:
        keyword = kw.get("keyword", "")
        score = kw.get("score", 0)
        if keyword:
            intent = kw.get("inferred_intent", "")
            page_type = kw.get("likely_serp_page_type", "")
            quality = kw.get("quality_score", "")
            lines.append(
                f"- {keyword} "
                f"(score={score}, quality={quality}, intent={intent}, page_type={page_type})"
            )
    return "\n".join(lines)


def _dedupe_clusters(clusters: List[KeywordCluster]) -> List[KeywordCluster]:
    """Ensure each keyword appears in only one cluster (highest score wins)."""
    assigned: Dict[str, tuple[float, Dict[str, Any], int]] = {}

    for idx, cluster in enumerate(clusters):
        for kw in cluster.get("keywords") or []:
            key = (kw.get("keyword") or "").strip().lower()
            if not key:
                continue
            score = float(kw.get("score", 0))
            prev = assigned.get(key)
            if prev is None or score > prev[0]:
                assigned[key] = (score, kw, idx)

    rebuilt: List[KeywordCluster] = []
    for idx, cluster in enumerate(clusters):
        kept = []
        for kw in cluster.get("keywords") or []:
            key = (kw.get("keyword") or "").strip().lower()
            if assigned.get(key) and assigned[key][2] == idx:
                kept.append(kw)
        if kept:
            kept.sort(key=lambda x: x.get("score", 0), reverse=True)
            rebuilt.append({
                **cluster,
                "keywords": kept,
                "total_score": round(sum(k.get("score", 0) for k in kept), 2),
            })

    rebuilt.sort(key=lambda x: x["total_score"], reverse=True)
    return rebuilt


class KeywordClusteringService:
    """
    LLM keyword clustering using competitor-LLM intent and titles from
    intent-matched competitors only (Semrush / Ahrefs-style).
    """

    async def cluster_keywords(
        self,
        keywords_data: List[Dict[str, Any]],
        query: str,
        primary_intent: str,
        intent_matched_signals: Optional[IntentMatchedSerpSignals] = None,
        content_type: str = "blog",
        selected_topic: str = "",
    ) -> List[KeywordCluster]:
        if not keywords_data:
            return []

        intent_lower = (primary_intent or "informational").lower()
        if intent_lower not in _VALID_INTENTS:
            intent_lower = "informational"
        intent_upper = intent_lower.upper()
        normalized_content_type = _normalize_content_type(content_type)
        signals = intent_matched_signals or {}

        filtered_keywords = _filter_keyword_candidates(
            keywords_data=keywords_data,
            query=query,
            primary_intent=intent_lower,
            intent_matched_signals=signals,
            content_type=normalized_content_type,
            selected_topic=selected_topic,
        )

        if not filtered_keywords:
            logger.info("No keyword candidates survived quality and intent filtering")
            return []

        if len(filtered_keywords) == 1:
            return self._score_and_filter_clusters(
                [self._single_keyword_cluster(filtered_keywords[0], intent_lower)],
                query=query,
                primary_intent=intent_lower,
                intent_matched_signals=signals,
                content_type=normalized_content_type,
                selected_topic=selected_topic,
            )

        try:
            clusters = await self._cluster_with_llm(
                keywords_data=filtered_keywords,
                query=query,
                primary_intent=intent_lower,
                primary_intent_upper=intent_upper,
                intent_matched_signals=signals,
                content_type=normalized_content_type,
                selected_topic=selected_topic,
            )
            if clusters:
                clusters = _dedupe_clusters(clusters)
                clusters = self._score_and_filter_clusters(
                    clusters,
                    query=query,
                    primary_intent=intent_lower,
                    intent_matched_signals=signals,
                    content_type=normalized_content_type,
                    selected_topic=selected_topic,
                )
                logger.info(
                    "LLM clustered %d filtered keywords into %d page-ready groups",
                    len(filtered_keywords),
                    len(clusters),
                )
                return clusters
        except Exception as e:
            logger.error(f"LLM keyword clustering failed: {e}")

        return self._fallback_clusters(
            filtered_keywords,
            intent_lower,
            query=query,
            intent_matched_signals=signals,
            content_type=normalized_content_type,
            selected_topic=selected_topic,
        )

    async def _cluster_with_llm(
        self,
        keywords_data: List[Dict[str, Any]],
        query: str,
        primary_intent: str,
        primary_intent_upper: str,
        intent_matched_signals: IntentMatchedSerpSignals,
        content_type: str,
        selected_topic: str,
    ) -> List[KeywordCluster]:
        context_block = _format_intent_matched_context(intent_matched_signals)
        system_prompt = KEYWORD_CLUSTERING_SYSTEM_PROMPT.format(
            primary_intent=primary_intent,
            primary_intent_upper=primary_intent_upper,
            intent_matched_context=context_block,
            content_type_rules=_content_type_rule_block(content_type),
        )

        human_prompt = (
            f"Target query: {query}\n"
            f"Content Type: {content_type}\n"
            f"Selected Topic: {selected_topic}\n\n"
            f"Keyword candidates to cluster ({len(keywords_data)}):\n"
            f"{_format_candidates(keywords_data)}\n\n"
            "Group into compact page-ready clusters based on the content type rules. "
            "Use only candidates that share the same primary intent, same likely SERP page type, "
            "and the same one-page promise. Prefer keywords match with intent topic content type. Selecting from the candidate list is not mandatory, you can reject all keywords if they don't fit well into clusters."
            "For each cluster, provide a natural heading, likely SERP page type, outline placement "
            "(H2, H3, or body), and quality scores. Reject weak, awkward, unrelated, "
            "or mixed-intent terms."
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
                    base_score = float(base.get("score") or 0)
                    relevance_score = float(item.relevance_score)
                    cluster_keywords.append({
                        **base,
                        "score": round(max(base_score, relevance_score), 2),
                        "llm_relevance_score": round(relevance_score, 2),
                    })

            if not cluster_keywords:
                continue

            cluster_keywords.sort(key=lambda x: x.get("score", 0), reverse=True)
            placement = str(group.outline_placement or "H2").strip()
            clusters.append({
                "cluster_name": group.cluster_name,
                "topic_theme": group.topic_theme,
                "keywords": cluster_keywords,
                "total_score": round(
                    sum(k.get("score", 0) for k in cluster_keywords), 2
                ),
                "main_intent": group.intent.lower(),
                "rationale": group.rationale,
                "likely_serp_page_type": group.likely_serp_page_type,
                "recommended_heading": group.natural_heading,
                "outline_placement": placement,
                "intent_match_score": round(float(group.intent_match_score or 0), 2),
                "serp_overlap_score": round(float(group.serp_overlap_score or 0), 2),
                "content_type_fit_score": round(float(group.content_type_fit_score or 0), 2),
                "cluster_strength_score": round(float(group.cluster_strength_score or 0), 2),
            })

        return clusters

    def _score_and_filter_clusters(
        self,
        clusters: List[KeywordCluster],
        *,
        query: str,
        primary_intent: str,
        intent_matched_signals: IntentMatchedSerpSignals | None,
        content_type: str,
        selected_topic: str,
    ) -> List[KeywordCluster]:
        rules = _content_type_rules(content_type)
        validated: List[KeywordCluster] = []

        for cluster in clusters:
            raw_keywords = cluster.get("keywords") or []
            cleaned_keywords: list[dict[str, Any]] = []
            keyword_intent_scores: list[float] = []
            keyword_page_types: list[str] = []
            keyword_topic_scores: list[float] = []

            for raw in raw_keywords:
                keyword = _clean_keyword(raw.get("keyword"))
                if _is_low_quality_keyword(keyword, rules, query, selected_topic):
                    continue

                inferred_intent, page_type = _infer_keyword_intent_and_page_type(
                    keyword,
                    primary_intent,
                    content_type,
                )
                intent_score = _intent_match_score(inferred_intent, primary_intent)
                topic_score = _topic_promise_score(
                    keyword,
                    query,
                    selected_topic,
                    intent_matched_signals,
                )
                page_fit = _page_type_fit_score(page_type, rules)

                if intent_score < 60:
                    continue
                if topic_score < 25 and float(raw.get("score") or 0) < 70:
                    continue
                if page_fit < 40:
                    continue

                cleaned = {
                    **raw,
                    "keyword": keyword,
                    "intent_match_score": round(intent_score, 2),
                    "topic_promise_score": round(topic_score, 2),
                    "content_type_fit_score": round(page_fit, 2),
                    "inferred_intent": inferred_intent,
                    "likely_serp_page_type": page_type,
                    "word_count": len(keyword.split()),
                }
                cleaned_keywords.append(cleaned)
                keyword_intent_scores.append(intent_score)
                keyword_page_types.append(page_type)
                keyword_topic_scores.append(topic_score)

            if not cleaned_keywords:
                continue

            dominant_page_type = Counter(keyword_page_types).most_common(1)[0][0]
            if len(set(keyword_page_types)) > 1:
                cleaned_keywords = [
                    item
                    for item in cleaned_keywords
                    if item.get("likely_serp_page_type") == dominant_page_type
                ]
                if not cleaned_keywords:
                    continue
                keyword_intent_scores = [
                    float(item.get("intent_match_score") or 0)
                    for item in cleaned_keywords
                ]
                keyword_page_types = [
                    str(item.get("likely_serp_page_type") or "")
                    for item in cleaned_keywords
                ]
                keyword_topic_scores = [
                    float(item.get("topic_promise_score") or 0)
                    for item in cleaned_keywords
                ]

            cleaned_keywords.sort(key=lambda item: item.get("score", 0), reverse=True)
            cluster_name = (
                _clean_keyword(cluster.get("cluster_name"))
                or cleaned_keywords[0]["keyword"]
            )
            cluster_intent = str(cluster.get("main_intent") or "").lower()
            cluster_intent_score = 100.0 if cluster_intent == primary_intent else 0.0
            avg_intent_score = sum(keyword_intent_scores) / len(keyword_intent_scores)
            llm_intent_score = float(cluster.get("intent_match_score") or 0)
            if cluster_intent and cluster_intent != primary_intent:
                llm_intent_score = 0.0
            intent_match = max(
                llm_intent_score,
                (avg_intent_score * 0.75) + (cluster_intent_score * 0.25),
            )
            serp_overlap = max(
                float(cluster.get("serp_overlap_score") or 0),
                _serp_overlap_score(cleaned_keywords, cluster_name, intent_matched_signals),
            )
            content_type_fit = max(
                float(cluster.get("content_type_fit_score") or 0),
                sum(_page_type_fit_score(page_type, rules) for page_type in keyword_page_types)
                / len(keyword_page_types),
            )
            cluster_strength = max(
                float(cluster.get("cluster_strength_score") or 0),
                _cluster_strength_score({**cluster, "keywords": cleaned_keywords}, rules),
            )
            page_fit = _page_fit_score(keyword_page_types, rules)
            topic_promise = max(
                _topic_promise_score(cluster_name, query, selected_topic, intent_matched_signals),
                sum(keyword_topic_scores) / len(keyword_topic_scores),
            )
            overall_score = round(
                (intent_match * 0.24)
                + (serp_overlap * 0.18)
                + (content_type_fit * 0.18)
                + (cluster_strength * 0.20)
                + (page_fit * 0.12)
                + (topic_promise * 0.08),
                2,
            )

            if intent_match < _MIN_CLUSTER_INTENT_SCORE:
                continue
            if page_fit < _MIN_CLUSTER_PAGE_FIT_SCORE:
                continue
            if topic_promise < _MIN_TOPIC_PROMISE_SCORE:
                continue
            if overall_score < _MIN_CLUSTER_OVERALL_SCORE:
                continue

            page_type = Counter(keyword_page_types).most_common(1)[0][0]
            placement = _outline_placement(cluster, rules, overall_score)
            recommended_heading = (
                str(cluster.get("recommended_heading") or "").strip()
                or _natural_heading(cluster_name, content_type, placement)
            )

            scored_cluster: KeywordCluster = {
                **cluster,
                "cluster_name": cluster_name,
                "topic_theme": _clean_keyword(cluster.get("topic_theme")) or cluster_name,
                "keywords": cleaned_keywords[: int(rules.get("max_keywords", 6))],
                "total_score": round(sum(k.get("score", 0) for k in cleaned_keywords), 2),
                "main_intent": primary_intent,
                "likely_serp_page_type": page_type,
                "recommended_heading": recommended_heading,
                "outline_placement": placement,
                "page_fit_valid": True,
                "intent_match_score": round(intent_match, 2),
                "serp_overlap_score": round(serp_overlap, 2),
                "content_type_fit_score": round(content_type_fit, 2),
                "cluster_strength_score": round(cluster_strength, 2),
                "page_fit_score": round(page_fit, 2),
                "topic_promise_score": round(topic_promise, 2),
                "overall_score": overall_score,
                "quality_scores": {
                    "intent_match": round(intent_match, 2),
                    "serp_overlap": round(serp_overlap, 2),
                    "content_type_fit": round(content_type_fit, 2),
                    "cluster_strength": round(cluster_strength, 2),
                    "page_fit": round(page_fit, 2),
                    "topic_promise": round(topic_promise, 2),
                    "overall": overall_score,
                },
                "outline_mapping": {
                    "heading_level": placement,
                    "suggested_heading": recommended_heading,
                    "page_role": placement.lower() if placement != "body" else "body_copy",
                },
            }
            validated.append(scored_cluster)

        validated.sort(
            key=lambda item: item.get("overall_score", item.get("total_score", 0)),
            reverse=True,
        )
        return validated

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

    def _fallback_clusters(
        self,
        keywords_data: List[Dict[str, Any]],
        primary_intent: str,
        *,
        query: str,
        intent_matched_signals: IntentMatchedSerpSignals | None,
        content_type: str,
        selected_topic: str,
    ) -> List[KeywordCluster]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for kw in keywords_data:
            page_type = kw.get("likely_serp_page_type") or "article"
            grouped.setdefault(page_type, []).append(kw)

        clusters: list[KeywordCluster] = []
        rules = _content_type_rules(content_type)
        for page_type, items in grouped.items():
            sorted_kws = sorted(items, key=lambda item: item.get("score", 0), reverse=True)
            sorted_kws = sorted_kws[: int(rules.get("max_keywords", 6))]
            if not sorted_kws:
                continue
            cluster_name = sorted_kws[0].get("keyword", "cluster")
            clusters.append({
                "cluster_name": cluster_name,
                "topic_theme": page_type,
                "keywords": sorted_kws,
                "total_score": round(sum(k.get("score", 0) for k in sorted_kws), 2),
                "main_intent": primary_intent,
                "likely_serp_page_type": page_type,
                "rationale": (
                    "Fallback: grouped by inferred intent and SERP page type "
                    "after LLM failure"
                ),
            })

        return self._score_and_filter_clusters(
            clusters,
            query=query,
            primary_intent=primary_intent,
            intent_matched_signals=intent_matched_signals,
            content_type=content_type,
            selected_topic=selected_topic,
        )
