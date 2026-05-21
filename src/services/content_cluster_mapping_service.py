from __future__ import annotations

from typing import Any

_MAX_H2_SECTIONS = 6
_MAX_H3_TOPICS_PER_SECTION = 4
_MAX_SUPPORTING_KEYWORDS = 8


_COMMERCIAL_TYPES = {
    "alternatives",
    "best-tools",
    "buying-guide",
    "comparison",
    "in-depth-review",
    "product-roundup",
    "pros-cons",
}

_NAVIGATIONAL_TYPES = {
    "about-us",
    "brand-page",
    "contact-us",
    "documentation",
    "feature-overview",
    "help-center",
    "login-guide",
    "product-homepage",
}

_TRANSACTIONAL_TYPES = {
    "checkout-page",
    "coupon-page",
    "demo-page",
    "landing-page",
    "pricing-page",
    "sales-page",
    "service-page",
    "signup-page",
}


def is_pillar_content_type(content_type: str | None) -> bool:
    key = _normalize_key(content_type)
    compact_key = key.replace("-", "")
    return key == "pillar-content" or compact_key in {
        "pillar",
        "pillarcontent",
        "pillarpage",
    }


def build_cluster_heading_map(
    *,
    keyword_clusters: list[dict[str, Any]] | None,
    topic: str,
    content_type: str,
    questions: list[str] | None = None,
) -> dict[str, Any]:
    normalized_content_type = _normalize_key(content_type)

    if is_pillar_content_type(content_type):
        return {
            "enabled": False,
            "skipped": True,
            "reason": "Cluster heading mapping is intentionally skipped for pillar content.",
            "content_type": normalized_content_type,
            "h1": {},
            "h2_sections": [],
            "rules": [],
        }

    clusters = [cluster for cluster in keyword_clusters or [] if cluster.get("keywords")]
    if not clusters:
        return {
            "enabled": False,
            "skipped": False,
            "reason": "No keyword clusters available for heading mapping.",
            "content_type": normalized_content_type,
            "h1": {},
            "h2_sections": [],
            "rules": [],
        }

    sorted_clusters = sorted(clusters, key=_cluster_score, reverse=True)
    h2_clusters = sorted_clusters[:_MAX_H2_SECTIONS]
    overflow_clusters = sorted_clusters[_MAX_H2_SECTIONS:]

    primary_keyword = _primary_keyword(h2_clusters[0]) or _clean_text(topic)
    h1_heading = _clean_text(topic) or primary_keyword

    h2_sections = []
    for index, cluster in enumerate(h2_clusters, start=1):
        cluster_name = _clean_text(cluster.get("cluster_name"))
        cluster_primary = _primary_keyword(cluster) or cluster_name
        keywords = _unique_keywords(cluster.get("keywords") or [])
        supporting_keywords = [
            keyword
            for keyword in keywords
            if keyword.lower() not in {cluster_primary.lower(), cluster_name.lower()}
        ][:_MAX_SUPPORTING_KEYWORDS]

        h2_sections.append(
            {
                "order": index,
                "heading_level": "H2",
                "suggested_heading": cluster_name or cluster_primary,
                "cluster_name": cluster_name or cluster_primary,
                "topic_theme": _clean_text(cluster.get("topic_theme")),
                "primary_keyword": cluster_primary,
                "supporting_keywords": supporting_keywords,
                "search_intent": _clean_text(cluster.get("main_intent")) or "informational",
                "rationale": _clean_text(cluster.get("rationale")),
                "h3_topics": supporting_keywords[:_MAX_H3_TOPICS_PER_SECTION],
                "questions_to_answer": _questions_for_cluster(
                    questions or [],
                    [cluster_primary, *supporting_keywords],
                ),
            }
        )

    return {
        "enabled": True,
        "skipped": False,
        "reason": "",
        "content_type": normalized_content_type,
        "h1": {
            "heading_level": "H1",
            "suggested_heading": h1_heading,
            "primary_keyword": primary_keyword,
        },
        "h2_sections": h2_sections,
        "additional_keywords": _overflow_keywords(overflow_clusters),
        "rules": [
            "Use exactly one H1: the selected topic/title.",
            "Map each major semantic cluster to one H2 unless two clusters clearly overlap.",
            (
                "Use H3 headings only for supporting long-tail keywords or questions "
                "under their parent H2."
            ),
            "Do not force every keyword into a heading; cover extra terms naturally in body copy.",
            "Keep headings descriptive and natural, not keyword-stuffed.",
        ],
        "content_type_guidance": _content_type_guidance(normalized_content_type),
    }


def format_cluster_heading_map_for_prompt(cluster_heading_map: dict[str, Any] | None) -> str:
    if not cluster_heading_map or not cluster_heading_map.get("enabled"):
        reason = (cluster_heading_map or {}).get("reason") or "No cluster heading map available."
        return f"None. {reason}"

    h1 = cluster_heading_map.get("h1") or {}
    lines = [
        "Use this cluster-to-heading map as the structural plan.",
        f"H1: {h1.get('suggested_heading', '')} | Primary keyword: {h1.get('primary_keyword', '')}",
        f"Content-type guidance: {cluster_heading_map.get('content_type_guidance', '')}",
        "Rules:",
    ]

    for rule in cluster_heading_map.get("rules") or []:
        lines.append(f"- {rule}")

    lines.append("Mapped sections:")
    for section in cluster_heading_map.get("h2_sections") or []:
        keywords = [section.get("primary_keyword", ""), *(section.get("supporting_keywords") or [])]
        keywords = [keyword for keyword in keywords if keyword]
        lines.append(
            f"- H2: {section.get('suggested_heading', '')} "
            f"(cluster: {section.get('cluster_name', '')}; "
            f"intent: {section.get('search_intent', '')})"
        )
        if keywords:
            lines.append(f"  Keyword coverage: {', '.join(keywords[:_MAX_SUPPORTING_KEYWORDS])}")
        h3_topics = section.get("h3_topics") or []
        if h3_topics:
            lines.append(f"  H3 topics: {', '.join(h3_topics)}")
        questions = section.get("questions_to_answer") or []
        if questions:
            lines.append(f"  Questions to answer: {'; '.join(questions)}")

    additional_keywords = cluster_heading_map.get("additional_keywords") or []
    if additional_keywords:
        lines.append(f"Additional body keywords: {', '.join(additional_keywords)}")

    return "\n".join(lines)


def _normalize_key(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("_", "-").replace(" ", "-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-")


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip(" -")


def _score_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _cluster_score(cluster: dict[str, Any]) -> float:
    total_score = _score_value(cluster.get("total_score"))
    if total_score:
        return total_score
    return sum(_score_value(keyword.get("score")) for keyword in cluster.get("keywords") or [])


def _primary_keyword(cluster: dict[str, Any]) -> str:
    keywords = cluster.get("keywords") or []
    if not keywords:
        return _clean_text(cluster.get("cluster_name"))
    sorted_keywords = sorted(
        keywords,
        key=lambda item: _score_value(item.get("score")),
        reverse=True,
    )
    return _clean_text(sorted_keywords[0].get("keyword"))


def _unique_keywords(keywords: list[dict[str, Any]]) -> list[str]:
    seen = set()
    result = []
    sorted_keywords = sorted(
        keywords,
        key=lambda item: _score_value(item.get("score")),
        reverse=True,
    )
    for item in sorted_keywords:
        keyword = _clean_text(item.get("keyword"))
        key = keyword.lower()
        if keyword and key not in seen:
            seen.add(key)
            result.append(keyword)
    return result


def _questions_for_cluster(questions: list[str], keywords: list[str]) -> list[str]:
    keyword_tokens = {
        token
        for keyword in keywords
        for token in keyword.lower().split()
        if len(token) >= 4
    }
    matches = []
    for question in questions:
        clean_question = _clean_text(question)
        question_lower = clean_question.lower()
        if clean_question and any(token in question_lower for token in keyword_tokens):
            matches.append(clean_question)
        if len(matches) >= 2:
            break
    return matches


def _overflow_keywords(clusters: list[dict[str, Any]]) -> list[str]:
    keywords = []
    seen = set()
    for cluster in clusters:
        for keyword in _unique_keywords(cluster.get("keywords") or []):
            key = keyword.lower()
            if key not in seen:
                seen.add(key)
                keywords.append(keyword)
    return keywords[:_MAX_SUPPORTING_KEYWORDS]


def _content_type_guidance(content_type: str) -> str:
    if content_type in _COMMERCIAL_TYPES:
        return (
            "Use H2 sections for decision criteria, comparisons, alternatives, "
            "use cases, and buyer objections."
        )
    if content_type in _TRANSACTIONAL_TYPES:
        return (
            "Use H2 sections for the conversion journey: problem, solution, proof, "
            "offer, objections, and action."
        )
    if content_type in _NAVIGATIONAL_TYPES:
        return (
            "Use H2 sections for the user's navigation task, product or brand context, "
            "support paths, and next actions."
        )
    if content_type in {"how-to-guide", "tutorial", "checklist"}:
        return (
            "Use H2 sections for the task flow and H3s for detailed steps, checks, "
            "examples, or troubleshooting."
        )
    if content_type == "faq":
        return "Use H2 sections for question groups and H3s for individual high-intent questions."
    return (
        "Use H2 sections for major informational topic buckets and H3s for "
        "supporting subtopics or questions."
    )
