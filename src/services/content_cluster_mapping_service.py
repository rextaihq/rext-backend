from __future__ import annotations

from typing import Any

_MAX_H2_SECTIONS = 6
_MAX_H3_TOPICS_PER_SECTION = 4
_MAX_SUPPORTING_KEYWORDS = 8
_MIN_MAPPING_OVERALL_SCORE = 62
_MIN_H2_OVERALL_SCORE = 72
_MIN_H2_TOPIC_PROMISE_SCORE = 55
_MIN_H2_CLUSTER_STRENGTH_SCORE = 55
_NAVIGATION_FRAGMENT_TERMS = {"home", "homepage", "official", "login", "signin", "sign-in", "website"}
_ENTITY_ONLY_TERMS = {"foundation", "institute", "association", "center", "centre", "home", "homepage", "official", "site", "website"}
_SHORT_TOPIC_TERMS = {"ai", "api", "seo", "crm", "llm"}


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

    clusters = [
        cluster
        for cluster in keyword_clusters or []
        if cluster.get("keywords") and cluster.get("page_fit_valid", True) is not False
    ]
    clusters = [
        cluster
        for cluster in clusters
        if _cluster_quality(cluster, "overall") >= _MIN_MAPPING_OVERALL_SCORE
        and _cluster_has_usable_keywords(cluster, normalized_content_type)
    ]
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
    h2_candidates: list[dict[str, Any]] = []
    h3_candidates: list[dict[str, Any]] = []
    body_candidates: list[dict[str, Any]] = []

    for cluster in sorted_clusters:
        placement = _cluster_outline_placement(cluster)
        if placement == "H2" and not _is_h2_worthy(cluster):
            placement = "H3"
        if placement == "body":
            body_candidates.append(cluster)
        elif placement == "H3":
            h3_candidates.append(cluster)
        else:
            h2_candidates.append(cluster)

    if not h2_candidates and h3_candidates:
        h2_candidates.append(h3_candidates.pop(0))
    if not h2_candidates and body_candidates:
        h2_candidates.append(body_candidates.pop(0))

    h2_clusters = h2_candidates[:_MAX_H2_SECTIONS]
    overflow_clusters = h2_candidates[_MAX_H2_SECTIONS:] + body_candidates
    h3_assignments = _assign_h3_clusters(h3_candidates, h2_clusters)

    primary_source = h2_clusters[0] if h2_clusters else sorted_clusters[0]
    primary_keyword = _primary_keyword(primary_source) or _clean_text(topic)
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
        child_h3_clusters = h3_assignments.get(index - 1, [])
        child_h3_headings = [_cluster_heading(child) for child in child_h3_clusters]
        h3_topics = _unique_strings(
            [*supporting_keywords[:_MAX_H3_TOPICS_PER_SECTION], *child_h3_headings]
        )[:_MAX_H3_TOPICS_PER_SECTION]

        h2_sections.append(
            {
                "order": index,
                "heading_level": "H2",
                "suggested_heading": _cluster_heading(cluster) or cluster_name or cluster_primary,
                "cluster_name": cluster_name or cluster_primary,
                "topic_theme": _clean_text(cluster.get("topic_theme")),
                "primary_keyword": cluster_primary,
                "supporting_keywords": supporting_keywords,
                "search_intent": _clean_text(cluster.get("main_intent")) or "informational",
                "rationale": _clean_text(cluster.get("rationale")),
                "h3_topics": h3_topics,
                "mapped_h3_clusters": [
                    _cluster_mapping_payload(child, heading_level="H3")
                    for child in child_h3_clusters
                ],
                "questions_to_answer": _questions_for_cluster(
                    questions or [],
                    [cluster_primary, *supporting_keywords],
                ),
                "quality_scores": cluster.get("quality_scores") or {},
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
        "h3_sections": [
            {
                **_cluster_mapping_payload(child, heading_level="H3"),
                "parent_h2_order": parent_index + 1,
            }
            for parent_index, children in h3_assignments.items()
            for child in children
        ],
        "body_copy_clusters": [
            _cluster_mapping_payload(cluster, heading_level="body")
            for cluster in overflow_clusters
        ],
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

    h3_sections = cluster_heading_map.get("h3_sections") or []
    if h3_sections:
        lines.append("Mapped H3/supporting sections:")
        for section in h3_sections:
            keywords = [section.get("primary_keyword", ""), *(section.get("supporting_keywords") or [])]
            keywords = [keyword for keyword in keywords if keyword]
            lines.append(
                f"- H3 under H2 #{section.get('parent_h2_order', '')}: "
                f"{section.get('suggested_heading', '')}"
            )
            if keywords:
                lines.append(f"  Keyword coverage: {', '.join(keywords[:_MAX_SUPPORTING_KEYWORDS])}")

    body_clusters = cluster_heading_map.get("body_copy_clusters") or []
    if body_clusters:
        lines.append("Body-copy support clusters:")
        for cluster in body_clusters:
            keywords = [
                cluster.get("primary_keyword", ""),
                *(cluster.get("supporting_keywords") or []),
            ]
            keywords = [keyword for keyword in keywords if keyword]
            if keywords:
                lines.append(
                    f"- {cluster.get('suggested_heading', cluster.get('cluster_name', ''))}: "
                    f"{', '.join(keywords[:_MAX_SUPPORTING_KEYWORDS])}"
                )

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


def _keyword_is_usable_for_mapping(keyword: str, content_type: str) -> bool:
    words = [
        word
        for word in "".join(ch.lower() if ch.isalnum() or ch == "-" else " " for ch in keyword).split()
        if word
    ]
    if not words:
        return False
    if content_type not in _NAVIGATIONAL_TYPES and any(
        term in words for term in _NAVIGATION_FRAGMENT_TERMS
    ):
        return False

    acronym_like_terms = [
        word
        for word in words
        if (
            2 <= len(word) <= 5
            and word.isalpha()
            and word not in _SHORT_TOPIC_TERMS
        )
    ]
    if (
        content_type not in _NAVIGATIONAL_TYPES
        and acronym_like_terms
        and all(word in _ENTITY_ONLY_TERMS or word in acronym_like_terms for word in words)
    ):
        return False
    return True


def _cluster_has_usable_keywords(cluster: dict[str, Any], content_type: str) -> bool:
    return any(
        _keyword_is_usable_for_mapping(_clean_text(item.get("keyword")), content_type)
        for item in cluster.get("keywords") or []
    )


def _score_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _cluster_quality(cluster: dict[str, Any], key: str) -> float:
    scores = cluster.get("quality_scores") or {}
    direct_key = f"{key}_score"
    if key in scores:
        return _score_value(scores.get(key))
    if direct_key in cluster:
        return _score_value(cluster.get(direct_key))
    if key == "overall":
        return _score_value(cluster.get("overall_score"))
    return 0.0


def _cluster_score(cluster: dict[str, Any]) -> float:
    overall_score = _cluster_quality(cluster, "overall")
    if overall_score:
        return overall_score * 10
    total_score = _score_value(cluster.get("total_score"))
    if total_score:
        return total_score
    return sum(_score_value(keyword.get("score")) for keyword in cluster.get("keywords") or [])


def _is_h2_worthy(cluster: dict[str, Any]) -> bool:
    return (
        _cluster_quality(cluster, "overall") >= _MIN_H2_OVERALL_SCORE
        and _cluster_quality(cluster, "topic_promise") >= _MIN_H2_TOPIC_PROMISE_SCORE
        and _cluster_quality(cluster, "cluster_strength") >= _MIN_H2_CLUSTER_STRENGTH_SCORE
    )


def _cluster_outline_placement(cluster: dict[str, Any]) -> str:
    mapping = cluster.get("outline_mapping") or {}
    raw = (
        mapping.get("heading_level")
        or mapping.get("page_role")
        or cluster.get("outline_placement")
        or "H2"
    )
    placement = str(raw).strip().lower()
    if placement in {"body", "body-copy", "body_copy"}:
        return "body"
    if placement == "h3":
        return "H3"
    return "H2"


def _cluster_heading(cluster: dict[str, Any]) -> str:
    mapping = cluster.get("outline_mapping") or {}
    return (
        _clean_text(mapping.get("suggested_heading"))
        or _clean_text(cluster.get("recommended_heading"))
        or _clean_text(cluster.get("natural_heading"))
        or _clean_text(cluster.get("cluster_name"))
    )


def _token_set(value: str) -> set[str]:
    stopwords = {"a", "an", "and", "are", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}
    return {
        token
        for token in "".join(ch.lower() if ch.isalnum() else " " for ch in value).split()
        if len(token) >= 3 and token not in stopwords
    }


def _cluster_tokens(cluster: dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            _cluster_heading(cluster),
            _clean_text(cluster.get("cluster_name")),
            _primary_keyword(cluster),
            " ".join(_unique_keywords(cluster.get("keywords") or [])[:4]),
        ]
    )
    return _token_set(text)


def _assign_h3_clusters(
    h3_clusters: list[dict[str, Any]],
    h2_clusters: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    assignments: dict[int, list[dict[str, Any]]] = {idx: [] for idx in range(len(h2_clusters))}
    if not h2_clusters:
        return assignments

    h2_tokens = [_cluster_tokens(cluster) for cluster in h2_clusters]
    for child in h3_clusters:
        child_tokens = _cluster_tokens(child)
        best_index = 0
        best_score = -1
        for idx, tokens in enumerate(h2_tokens):
            if not child_tokens or not tokens:
                score = 0
            else:
                score = len(child_tokens & tokens)
            if score > best_score:
                best_score = score
                best_index = idx
        assignments.setdefault(best_index, []).append(child)
    return assignments


def _unique_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        clean = _clean_text(value)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _cluster_mapping_payload(
    cluster: dict[str, Any],
    *,
    heading_level: str,
) -> dict[str, Any]:
    keywords = _unique_keywords(cluster.get("keywords") or [])
    primary_keyword = _primary_keyword(cluster)
    supporting_keywords = [
        keyword for keyword in keywords if keyword.lower() != primary_keyword.lower()
    ][:_MAX_SUPPORTING_KEYWORDS]
    return {
        "heading_level": heading_level,
        "suggested_heading": _cluster_heading(cluster),
        "cluster_name": _clean_text(cluster.get("cluster_name")),
        "topic_theme": _clean_text(cluster.get("topic_theme")),
        "primary_keyword": primary_keyword,
        "supporting_keywords": supporting_keywords,
        "search_intent": _clean_text(cluster.get("main_intent")),
        "likely_serp_page_type": _clean_text(cluster.get("likely_serp_page_type")),
        "quality_scores": cluster.get("quality_scores") or {},
        "rationale": _clean_text(cluster.get("rationale")),
    }


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
