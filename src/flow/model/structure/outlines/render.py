"""
Outline renderer — normalizes any content-type-specific outline dict
into a single RenderableOutline shape for generic frontend display.

Frontend renders one format regardless of schema_type.
Each block represents the primary structural content of the outline
(sections, steps, clusters, phases, etc.) — not metadata.
"""

from __future__ import annotations
from typing import Any


# ── field-name helpers ──────────────────────────────────────────────────────

def _label(key: str) -> str:
    return key.replace("_", " ").title()


_LABEL_FIELDS = (
    "title", "heading", "name", "cluster_name", "phase", "term",
    "metric_name", "feature", "use_case", "scenario", "category",
    "module", "section", "insight", "challenge", "objective",
    "service", "question", "decision", "step_number",
)

_POINTS_FIELDS = (
    "key_points", "points", "actions", "tips", "questions",
    "items", "strengths", "weaknesses", "highlights",
    "requirements", "checks", "variations", "examples",
    "goals", "alternatives", "pros", "cons", "features",
)

_SKIP_LABEL_FIELDS = {
    "heading_level", "type", "id", "level", "difficulty_level",
    "intent_type", "answer_format", "optional", "required",
}

# Nested answer sub-object keys to surface as prose alongside a question label
_ANSWER_PROSE_FIELDS = ("short_answer", "brief", "content", "text")
_ANSWER_WRAPPER_KEYS = ("answer", "description", "explanation", "summary")

# Per content-type: ordered list of top-level keys that hold
# the primary structural content (what the article is actually made of).
_STRUCTURAL_KEYS: dict[str, list[str]] = {
    # Informational
    "blog":           ["structure"],
    "faq":            ["clusters"],
    "how-to-guide":   ["steps"],
    "tutorial":       ["modules", "steps"],
    "checklist":      ["phases"],
    "explainer":      ["progressive_explanation", "concept_breakdown", "how_it_works"],
    "glossary":       ["terms", "clusters"],
    "pillar-content": ["cluster_architecture", "structure"],
    "resource-list":  ["categories"],
    "white-paper":    ["methodology", "analysis", "solution", "recommendations"],
    "case-study":     ["problem", "goals", "strategy", "implementation", "results", "challenges", "insights"],
    # Commercial
    "comparison":     ["products", "feature_matrix", "use_cases"],
    "alternatives":   ["alternatives_list", "comparison_matrices"],
    "best-tools":     ["rankings", "categories"],
    "buying-guide":   ["product_options", "comparison_matrix", "decision_framework"],
    "in-depth-review":["features", "usability", "pros_cons", "verdict"],
    "product-roundup":["best_picks", "comparison_matrix"],
    "pros-cons":      ["pros", "cons", "tradeoffs"],
    # Navigational
    "about-us":           ["company_story", "services_snapshot", "team", "values"],
    "brand-page":         ["positioning", "story", "ecosystem"],
    "contact-us":         ["routing", "channels"],
    "documentation":      ["navigation", "guides", "api_reference"],
    "feature-overview":   ["function", "benefits", "use_cases", "how_it_works"],
    "help-center":        ["knowledge_base", "troubleshooting", "learning_paths"],
    "login-guide":        ["authentication", "error_handling", "troubleshooting"],
    "product-homepage":   ["value_proposition", "features", "use_cases", "how_it_works"],
    # Transactional
    "checkout-page": ["checkout_flow", "payment", "trust"],
    "coupon-page":   ["coupon_offer", "redemption_flow"],
    "demo-page":     ["walkthrough", "value_proof", "objection_handling"],
    "landing-page":  ["problem", "solution", "benefits", "offer"],
    "pricing-page":  ["pricing_plans", "comparison_table", "objection_handling"],
    "sales-page":    ["problem", "solution", "offer", "benefits", "social_proof"],
    "service-page":  ["service_overview", "solution", "benefits"],
    "signup-page":   ["value_stack", "signup_form", "onboarding"],
}

# Keys that are metadata/SEO/UI and should never be treated as structural
_META_KEYS = {
    "title", "slug_suggestion", "focus_keyphrase", "target_audience", "tone",
    "schema_type", "target_word_count", "rejected_reason", "status",
    "target_reading_time_minutes", "target_completion_time_minutes",
    "content_goal", "conversion_goal", "success_metric", "success_definition",
    "decision_time_target_seconds", "target_time_to_decision_seconds",
    "hero", "seo", "eeat", "media", "references", "cta",
    "social_proof", "transparency", "snippets", "coverage",
    "authority", "ux", "summary", "internal_links",
    "related_questions", "data_sources",
}


# ── item extraction ─────────────────────────────────────────────────────────

def _prose_from_item(d: dict) -> str:
    """Extract a short answer/description string from a dict item.

    Handles both direct fields (short_answer, brief, …) and one level of
    nesting such as FAQItem.answer.short_answer.
    """
    for key in _ANSWER_PROSE_FIELDS:
        val = d.get(key)
        if isinstance(val, str) and val.strip() and len(val) < 500:
            return val.strip()
    for wrapper in _ANSWER_WRAPPER_KEYS:
        val = d.get(wrapper)
        if isinstance(val, dict):
            for key in _ANSWER_PROSE_FIELDS:
                inner = val.get(key)
                if isinstance(inner, str) and inner.strip() and len(inner) < 500:
                    return inner.strip()
    return ""


def _primary_label(d: dict) -> str:
    for key in _LABEL_FIELDS:
        if key in d:
            val = d[key]
            if isinstance(val, (str, int)) and str(val).strip():
                return str(val).strip()
    for v in d.values():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _primary_points(d: dict) -> list[str]:
    for key in _POINTS_FIELDS:
        if key in d:
            val = d[key]
            if isinstance(val, list) and val:
                result = []
                for item in val:
                    if isinstance(item, str) and item.strip():
                        result.append(item.strip())
                    elif isinstance(item, dict):
                        lbl = _primary_label(item)
                        prose = _prose_from_item(item)
                        if lbl and prose:
                            result.append(f"{lbl} — {prose}")
                        elif lbl:
                            result.append(lbl)
                        elif prose:
                            result.append(prose)
                return result
    # fallback: short string fields that aren't label/skip fields
    result = []
    for k, v in d.items():
        if k in _SKIP_LABEL_FIELDS or k in _LABEL_FIELDS:
            continue
        if isinstance(v, str) and v.strip() and len(v) < 400:
            result.append(v.strip())
            if len(result) >= 3:
                break
    return result


def _items_from_list(lst: list) -> list[dict]:
    result = []
    for elem in lst:
        if isinstance(elem, dict):
            label = _primary_label(elem)
            points = _primary_points(elem)
            if label or points:
                result.append({"label": label, "points": points})
        elif isinstance(elem, str) and elem.strip():
            result.append({"label": elem.strip(), "points": []})
    return result


def _unwrap_nested_list(raw: dict) -> list | None:
    """
    If a dict wraps a single important list field, return that list.
    e.g. steps.steps → [Step], structure.sections → [Section]
    """
    nested_keys = (
        "sections", "steps", "items", "faqs", "goals", "clusters",
        "tools", "sources", "rows", "metrics", "errors", "testimonials",
        "challenges", "insights", "variations", "checks", "categories",
        "alternatives", "rankings", "pros", "cons", "recommendations",
        "phases", "modules", "terms", "resources", "products",
    )
    for key in nested_keys:
        if key in raw and isinstance(raw[key], list):
            return raw[key]
    return None


def _extract_items(raw: Any) -> list[dict]:
    """
    Given any field value, return a list of {"label": str, "points": [str]} items.
    """
    if isinstance(raw, list):
        return _items_from_list(raw)

    if isinstance(raw, dict):
        # Try to unwrap a nested list first
        inner = _unwrap_nested_list(raw)
        if inner is not None:
            return _items_from_list(inner)

        # Dict of named objects (e.g. products: {product_a: {...}, product_b: {...}})
        items = []
        for k, v in raw.items():
            if isinstance(v, dict):
                inner_label = _primary_label(v)
                full_label = f"{_label(k)}: {inner_label}" if inner_label else _label(k)
                points = _primary_points(v)
                items.append({"label": full_label, "points": points})
            elif isinstance(v, str) and v.strip():
                items.append({"label": _label(k), "points": [v.strip()]})
            elif isinstance(v, list) and v:
                flat = [str(i) for i in v if isinstance(i, str) and i]
                if flat:
                    items.append({"label": _label(k), "points": flat[:5]})
        return items

    if isinstance(raw, str) and raw.strip():
        return [{"label": raw.strip(), "points": []}]

    return []


# ── metadata helpers ────────────────────────────────────────────────────────

def _resolve_focus_keyphrase(outline_dict: dict) -> str:
    """Get focus_keyphrase regardless of nesting (direct or under seo/seo_plan)."""
    direct = outline_dict.get("focus_keyphrase")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for wrapper in ("seo", "seo_plan"):
        obj = outline_dict.get(wrapper)
        if isinstance(obj, dict):
            nested = obj.get("focus_keyphrase")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return ""


def _resolve_keywords(outline_dict: dict) -> list[str]:
    """Surface the primary keyword list regardless of per-type field name."""
    for key in ("keywords_to_include", "secondary_keywords", "focus_keywords", "semantic_keywords", "keywords"):
        val = outline_dict.get(key)
        if isinstance(val, list) and val:
            return [str(k).strip() for k in val if k]
    for wrapper in ("seo", "seo_plan"):
        obj = outline_dict.get(wrapper)
        if isinstance(obj, dict):
            for key in ("secondary_keywords", "keywords_to_include", "search_variants"):
                val = obj.get(key)
                if isinstance(val, list) and val:
                    return [str(k).strip() for k in val if k]
    return []


# ── public API ───────────────────────────────────────────────────────────────

def normalize_outline(outline_dict: dict, content_type: str) -> dict:
    """
    Convert any outline dict into a generic renderable shape.

    Returns:
        {
            "title": str,
            "schema_type": str,
            "slug_suggestion": str,
            "focus_keyphrase": str,   # resolved from top-level or seo.focus_keyphrase
            "keywords_to_include": [str],  # unified keyword list across all model variants
            "target_word_count": int,
            "rejected_reason": str,
            "status": str,
            "blocks": [
                {
                    "heading": str,       # human label for this structural block
                    "items": [
                        {
                            "label": str,     # section/step/cluster name
                            "points": [str],  # key points / questions / actions
                        }
                    ]
                }
            ]
        }
    """
    from src.flow.model.structure.outlines import normalize_content_type

    ct = normalize_content_type(content_type)
    keys_to_try = _STRUCTURAL_KEYS.get(ct) or []

    blocks: list[dict] = []

    for key in keys_to_try:
        raw = outline_dict.get(key)
        if raw is None:
            continue
        items = _extract_items(raw)
        if items:
            blocks.append({"heading": _label(key), "items": items})

    # Fallback: scan all non-meta fields for any list/dict content
    if not blocks:
        for key, raw in outline_dict.items():
            if key in _META_KEYS:
                continue
            if isinstance(raw, (list, dict)):
                items = _extract_items(raw)
                if items:
                    blocks.append({"heading": _label(key), "items": items})
                    if len(blocks) >= 6:
                        break

    return {
        "title": outline_dict.get("title", ""),
        "schema_type": outline_dict.get("schema_type", ""),
        "slug_suggestion": outline_dict.get("slug_suggestion", ""),
        "focus_keyphrase": _resolve_focus_keyphrase(outline_dict),
        "keywords_to_include": _resolve_keywords(outline_dict),
        "target_word_count": outline_dict.get("target_word_count", 0),
        "rejected_reason": outline_dict.get("rejected_reason", ""),
        "status": outline_dict.get("status", ""),
        "blocks": blocks,
    }
