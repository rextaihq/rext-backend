"""Realistic per-content-type outline fixtures, derived from the REAL schemas.

Nothing here is hand-maintained per content type: the outline dict is built by
walking the content type's own Pydantic outline model, so a schema change flows
straight into the fixture. Values are deliberately REAL (real tool names, real
URLs, real prose) — the point of the matrix run is to prove the pipeline never
emits placeholder entities, so the input must never contain one either.
"""

from __future__ import annotations

import typing
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from src.flow.model.structure.outlines import get_outline_model

# ---------------------------------------------------------------------------
# The fixed, realistic world every fixture is built from.
# ---------------------------------------------------------------------------

FOCUS_KEYPHRASE = "seo content tools"
SELECTED_TITLE = "SEO Content Tools That Actually Move Rankings"
TOPIC = SELECTED_TITLE

BRAND = {
    "brand_name": "Rankwell",
    "brand_url": "https://rankwell.io",
    "about": (
        "Rankwell is an SEO content platform that turns a keyword into a researched brief, "
        "a drafted article and a published post. It connects to WordPress and Shopify, pulls "
        "live SERP data into every brief, and gives editors an approval step before anything "
        "goes live."
    ),
    "selling_position": (
        "Rankwell suits lean in-house marketing teams that need an agency-sized content "
        "pipeline without agency retainers: briefs, drafts and publishing in one workflow."
    ),
}

# Real, publicly recognisable products. Used wherever a schema asks for a
# product/tool/company name, so a placeholder can only ever come FROM the
# pipeline, never from the fixture.
REAL_PRODUCTS = [
    "Ahrefs",
    "Semrush",
    "Surfer SEO",
    "Clearscope",
    "MarketMuse",
    "Frase",
    "Moz Pro",
]

INTERNAL_LINKS = [
    {
        "title": "our guide to keyword clustering",
        "anchor_text": "our guide to keyword clustering",
        "url": "https://rankwell.io/blog/keyword-clustering-guide",
        "context": "keyword clustering for seo content tools and topical maps",
        "status": "approved",
        "score": 0.82,
    },
    {
        "title": "how we run content audits",
        "anchor_text": "how we run content audits",
        "url": "https://rankwell.io/blog/content-audit-process",
        "context": "content audit workflow, refreshing existing seo content",
        "status": "approved",
        "score": 0.71,
    },
]

# Search results the "writer" is pretended to have fetched. Citations must trace
# back to these or facts_and_external_links blocks.
SEARCHED_RESULTS = [
    {
        "url": "https://ahrefs.com/blog/seo-statistics/",
        "title": "SEO statistics",
        "snippet": (
            "Organic search drives 53% of all website traffic across the sites studied, "
            "making it the single largest acquisition channel for most content teams."
        ),
    },
    {
        "url": "https://backlinko.com/search-engine-ranking",
        "title": "Search engine ranking factors",
        "snippet": (
            "Pages that cover a topic comprehensively rank higher on average than thin pages "
            "targeting the same query, according to an analysis of 11.8 million results."
        ),
    },
]

KEY_FACTS = [
    {
        "text": "Organic search drives 53% of all website traffic.",
        "source_url": "https://ahrefs.com/blog/seo-statistics/",
    },
    {
        "text": "Pages that cover a topic comprehensively rank higher than thin pages.",
        "source_url": "https://backlinko.com/search-engine-ranking",
    },
]

AUTHOR_PROFILE = (
    "Written by Dana Whitfield, an in-house SEO lead who has run content programmes for "
    "B2B SaaS teams for nine years."
)

TARGET_WORD_COUNT = 1400

# Topical vocabulary reused by the generic string filler, so every generated
# string overlaps the article's subject. Link-relevance and fact-fidelity checks
# both measure word overlap, so lorem-style filler would fail them for reasons
# that have nothing to do with the pipeline.
_TOPICAL = (
    "seo content tools help marketing teams plan briefs, draft articles and publish them "
    "without losing editorial control"
)

# Field names that hold a PRODUCT/TOOL/COMPANY name. These are the fields the
# placeholder guard exists for, so they get a real product name rather than the
# generic filler.
_PRODUCT_NAME_FIELDS = {
    "name",
    "product_name",
    "tool_name",
    "brand_name",
    "company_name",
    "vendor",
    "vendor_name",
    "competitor",
    "competitor_name",
    "alternative_name",
    "product",
    "tool",
    "title_of_product",
}

_URL_FIELDS = {"url", "link", "href", "source_url", "website", "product_url", "brand_url"}


def _rotating_product(counter: list[int]) -> str:
    name = REAL_PRODUCTS[counter[0] % len(REAL_PRODUCTS)]
    counter[0] += 1
    return name


def _unwrap_optional(annotation: Any) -> Any:
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
        if args:
            return args[0]
    return annotation


def _constraint(field: FieldInfo, name: str) -> Any:
    for meta in field.metadata or []:
        if hasattr(meta, name):
            return getattr(meta, name)
    return None


def _string_for(field_name: str, counter: list[int]) -> str:
    lowered = field_name.lower()
    if lowered in _URL_FIELDS:
        return "https://ahrefs.com/blog/seo-statistics/"
    if lowered in _PRODUCT_NAME_FIELDS:
        return _rotating_product(counter)
    if "url" in lowered:
        return "https://ahrefs.com/blog/seo-statistics/"
    if "slug" in lowered:
        return "seo-content-tools"
    if "keyphrase" in lowered or lowered == "focus_keyphrase":
        return FOCUS_KEYPHRASE
    if "question" in lowered:
        return "Which seo content tools fit a small in-house team?"
    if "heading" in lowered or lowered == "title":
        return "Choosing seo content tools for a lean team"
    if "term" in lowered:
        return "Topical authority"
    if "email" in lowered:
        return "hello@rankwell.io"
    if "phone" in lowered:
        return "+1 415 555 0142"
    if "date" in lowered or "year" in lowered:
        return "2026"
    if "price" in lowered or "cost" in lowered:
        return "Plans start in the low double digits per month"
    return f"{field_name.replace('_', ' ').capitalize()}: {_TOPICAL}"


def _value_for(annotation: Any, field: FieldInfo, field_name: str, counter: list[int], depth: int):
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)

    if origin is typing.Literal:
        return get_args(annotation)[0]

    if origin in (list, typing.List):
        inner = get_args(annotation)
        inner_type = inner[0] if inner else str
        min_len = _constraint(field, "min_length") or 0
        count = max(2, min_len)
        if isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
            return [_fill_model(inner_type, counter, depth + 1) for _ in range(count)]
        if get_origin(inner_type) is typing.Literal:
            return [get_args(inner_type)[0]]
        return [_string_for(field_name, counter) for _ in range(count)]

    if origin in (dict, typing.Dict):
        return {"seo content tools": "planning, drafting and publishing"}

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _fill_model(annotation, counter, depth + 1)

    if annotation is bool:
        return False
    if annotation is int:
        ge = _constraint(field, "ge")
        le = _constraint(field, "le")
        value = 1400
        if ge is not None:
            value = max(value, ge)
        if le is not None:
            value = min(value, le)
        return value
    if annotation is float:
        return 1.2
    return _string_for(field_name, counter)


def _fill_model(model: type[BaseModel], counter: list[int], depth: int = 0) -> dict:
    if depth > 6:
        return {}
    out: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        out[name] = _value_for(field.annotation, field, name, counter, depth)
    return out


def build_outline(content_type: str) -> dict:
    """A realistic, fully-populated approved outline for `content_type`."""
    model = get_outline_model(content_type)
    counter = [0]
    outline = _fill_model(model, counter)

    # Pin the fields the pipeline treats as authoritative, overriding the
    # generic filler.
    outline.update(
        {
            "title": SELECTED_TITLE,
            "slug_suggestion": "seo-content-tools",
            "focus_keyphrase": FOCUS_KEYPHRASE,
            "keywords_to_include": [FOCUS_KEYPHRASE, "content briefs", "keyword research"],
            "keyphrase_synonyms": ["seo writing tools"],
            "target_word_count": TARGET_WORD_COUNT,
            "tone": "Professional",
            "key_facts": KEY_FACTS,
            "internal_links": INTERNAL_LINKS,
            "promote_brand": True,
            "brand_voice_promotion": BRAND,
            "schema_type": content_type,
        }
    )
    return outline


def generation_meta() -> dict:
    return {
        "searched_results": list(SEARCHED_RESULTS),
        "author_profile": AUTHOR_PROFILE,
        "link_inventory": [],
    }
