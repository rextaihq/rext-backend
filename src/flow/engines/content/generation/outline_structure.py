"""Single source of truth for "what structure and data did the user approve?".

The per-content-type Pydantic outline model (LandingPageOutline, BestToolsOutline,
...) IS the contract for how a generated article is shaped — it defines which
structural blocks exist and, by field declaration order, the order they belong
in. This module reads that contract directly and pairs it with the live,
user-approved values from the outline dict.

Why this exists
---------------
Generation and validation previously both read `outline["_render"]`, the output
of `normalize_outline()` — a *presentation adapter* whose own docstring says it
exists "for generic frontend display" and that it "intentionally excludes"
fields. Two consequences:

1. It is lossy by design. Its `_STRUCTURAL_KEYS` whitelist had to enumerate the
   structural keys of all 34 content types by hand, and anything missing from
   that list silently vanished. `hero` was missing for every single page type —
   so a landing page was planned with no hero section at all, which is why an
   approved brand mention had nowhere to go at the top and kept sliding to the
   bottom of the article.
2. It is frozen before human review (outline.py builds `_render` ahead of the
   approval interrupt), so it can never reflect what the user actually approved.

Reading the Pydantic model instead makes the structure self-maintaining: adding
a field to an outline schema flows into generation AND validation with no other
edit. Both consumers call `resolve_outline_structure()`, so the prompt and the
validator cannot drift apart again — that drift was the defect, not a missing
whitelist entry.

`normalize_outline()` keeps its original job: shaping outlines for the approval
UI, where partial values are fine.
"""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from src.flow.model.structure.outlines import get_outline_model

logger = logging.getLogger(__name__)

# Fields that are structurally shaped (nested models) but are AI-writing
# guidance rather than sections of the finished page — SEO targets, E-E-A-T
# signals, entity graphs, snippet targets, link plans. They must not become
# "## Seo" headings in the article. The link plan and reference list are
# excluded here because the prompt already injects them through their own
# dedicated blocks (LINKS TO EMBED / Required facts); including them again as
# structural sections would double-instruct the model.
#
# This is an EXCLUSION list, which is the important inversion: forgetting an
# entry here surfaces an extra block in the output (loud, obvious on the first
# generation) instead of silently deleting a real section the way the old
# inclusion whitelist did.
_GUIDANCE_FIELDS = frozenset({
    "seo",
    "search_intent",
    "intent",
    "eeat",
    "engagement",
    "authority",
    "ux",
    "topic_cluster",
    "topic_authority",
    "semantic_coverage",
    "coverage",
    "entity_graph",
    "content_depth",
    "internal_links",
    "internal_linking",
    "references",
    "snippets",
    "media",
    "visuals",
    "effort",
    "user_journey",
})

# Keys on the outline dict that are metadata, never structural blocks. Used
# only when scanning for user/LLM-added keys the Pydantic model doesn't know
# about, so an unrecognised *section* is preserved while ordinary metadata is
# not mistaken for one.
_NON_STRUCTURAL_KEYS = frozenset({
    "title", "slug", "slug_suggestion", "focus_keyphrase", "keywords_to_include",
    "secondary_keywords", "target_audience", "tone", "target_word_count",
    "content_goal", "conversion_goal", "traffic_source", "campaign_name",
    "reading_time", "schema_type", "status", "rejected_reason", "brief",
    "lead_magnet", "visual_direction", "promote_brand", "brand_voice_promotion",
    "selected_persona_id", "cluster_heading_map", "key_facts", "facts",
})
# NOTE: `sections` / `content_structure` are deliberately absent above. Some
# outlines carry a flat top-level `sections` list that no schema declares; the
# unknown-key scan picks it up as a container block so its per-section headings
# still reach generation and validation instead of being dropped.

# Recursion bound for _render_value. Must clear the deepest REAL schema nesting,
# not merely guard against runaway: the commercial types bury the thing that
# matters several levels down —
#   rankings -> ToolRanking -> ranked_tools -> RankedTool -> tool -> name
# which lands at depth 5. At a limit of 3 that entire subtree was dropped, so
# the prompt showed "- Tool:" with no name under it and product-roundup's
# Products list rendered empty. The writer model was being asked to rank
# products it was never told the names of.
_MAX_DEPTH = 6


@dataclass(frozen=True)
class OutlineBlock:
    """One structural block of the approved outline."""

    key: str          # schema field name, e.g. "hero"
    heading: str      # human label, e.g. "Hero"
    required: bool    # the schema field is non-Optional
    data: Any         # the approved values, verbatim from the outline dict
    order: int        # position in the schema's declaration order


# Acronyms that .title() would mangle ("Cta", "Faq") — these end up as headings
# in the prompt and, via _expected_sections, as the labels validation matches
# against, so they need to read correctly.
_ACRONYMS = {"cta": "CTA", "faq": "FAQ", "faqs": "FAQs", "seo": "SEO", "ux": "UX", "roi": "ROI"}


def humanize_key(key: str) -> str:
    return " ".join(_ACRONYMS.get(word, word.title()) for word in key.split("_"))


def _unwrap_optional(annotation: Any) -> Any:
    """Optional[X] / Union[X, None] -> X (leaves genuine multi-type unions alone)."""
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _is_structural(annotation: Any) -> bool:
    """True when a field holds a nested model (or list of them) — i.e. a page section.

    Scalars, `List[str]`, and `Literal` enums are outline metadata (title, tone,
    keywords, word count), never structural blocks.
    """
    annotation = _unwrap_optional(annotation)
    if get_origin(annotation) in (list, typing.List):
        inner = get_args(annotation)
        return bool(inner and isinstance(inner[0], type) and issubclass(inner[0], BaseModel))
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _is_empty(value: Any) -> bool:
    """Empty means the user removed/never filled this block — it gets no section."""
    if value is None:
        return True
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) == 0
    return False


def _looks_structural(value: Any) -> bool:
    """Shape test for a key the schema doesn't define (user- or LLM-added)."""
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value) and isinstance(value[0], dict)
    return False


def resolve_outline_structure(outline: dict, content_type: str) -> list[OutlineBlock]:
    """The approved structure of this article: schema order + live outline data.

    Structure and order come from the content type's Pydantic outline model;
    the values come from `outline`, so whatever the user approved (or edited)
    is what generation and validation both see.

    Reconciliation is explicit — nothing is ever silently dropped:
      * in schema + has data  -> block, ordered by field declaration
      * in schema + empty     -> skipped (user removed it / never generated);
                                 logged when the field is required
      * in outline only       -> appended after known blocks, never discarded
    """
    outline = outline or {}
    model = get_outline_model(content_type)
    blocks: list[OutlineBlock] = []
    skipped_required: list[str] = []
    skipped_empty: list[str] = []

    known_fields: set[str] = set()

    if model is not None:
        for order, (name, field) in enumerate(model.model_fields.items()):
            known_fields.add(name)
            if name in _GUIDANCE_FIELDS or not _is_structural(field.annotation):
                continue
            value = outline.get(name)
            if _is_empty(value):
                (skipped_required if field.is_required() else skipped_empty).append(name)
                continue
            blocks.append(
                OutlineBlock(
                    key=name,
                    heading=humanize_key(name),
                    required=field.is_required(),
                    data=value,
                    order=order,
                )
            )
    else:
        logger.warning("resolve_outline_structure: no outline model for content_type=%r", content_type)

    # Keys the schema doesn't define — a user-added section, or LLM drift.
    # Kept and appended rather than dropped: silently discarding unrecognised
    # structure is precisely the failure this module exists to end.
    extra: list[str] = []
    for name, value in outline.items():
        if name in known_fields or name.startswith("_"):
            continue
        if name in _NON_STRUCTURAL_KEYS or name in _GUIDANCE_FIELDS:
            continue
        if not _looks_structural(value):
            continue
        extra.append(name)
        blocks.append(
            OutlineBlock(
                key=name,
                heading=humanize_key(name),
                required=False,
                data=value,
                order=len(blocks) + 1000,
            )
        )

    # One reconciliation line per article. The hero block was missing from every
    # page type for months precisely because nothing ever reported what was
    # dropped — this makes structural loss observable instead of silent.
    logger.info(
        "resolve_outline_structure: content_type=%s used=%s skipped_empty=%s "
        "missing_required=%s extra_unknown=%s",
        content_type, [b.key for b in blocks], skipped_empty, skipped_required, extra,
    )
    return blocks


# Field names that carry an item's own heading. Used ONLY to unwrap "container"
# blocks for validation labels (see resolve_expected_headings) — deliberately
# tiny and generic, never consulted when rendering the prompt, so it cannot grow
# into the kind of per-schema registry this module replaced.
_ITEM_HEADING_FIELDS = ("heading", "title", "name", "question", "term", "label")

# Blocks that belong in the PROMPT but are not body H2s, so they must not be
# expected as section headings:
#   hero        -> becomes the title / introduction, not a "## Hero" heading
#   faq/faqs    -> already enforced via extract_outline_faqs; unwrapping them
#                  would also add one expected "section" per question
#   cta/final_cta -> already enforced by check_cta_presence
_NON_HEADING_BLOCKS = frozenset({"hero", "faq", "faqs", "cta", "final_cta"})


def _container_items(data: Any) -> list[dict] | None:
    """A block that is a *container of sections* rather than a section itself.

    e.g. blog's `structure` is `{"sections": [Section, ...]}` — its real H2s are
    the nested section headings, not the word "Structure".
    """
    if isinstance(data, list) and data and all(isinstance(i, dict) for i in data):
        return data
    if isinstance(data, dict) and len(data) == 1:
        inner = next(iter(data.values()))
        if isinstance(inner, list) and inner and all(isinstance(i, dict) for i in inner):
            return inner
    return None


def _item_heading(item: dict) -> tuple[str, dict] | None:
    """(heading, remaining fields) — the heading field is consumed, so the
    renderer doesn't repeat it as a bullet underneath its own heading."""
    for field in _ITEM_HEADING_FIELDS:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip(), {k: v for k, v in item.items() if k != field}
    return None


def unwrap_block(block: OutlineBlock) -> list[tuple[str, Any]]:
    """A block as the (heading, data) pairs it contributes to the article.

    Usually one pair — the block is itself a section. But a block that merely
    *wraps* a list of sections (blog's `structure` is `{"sections": [...]}`)
    contributes one pair per child, so the article gets real H2s instead of a
    literal "Structure" heading no article would ever contain.

    Shared by the prompt renderer and the validation heading list so the model
    is asked for exactly the headings validation looks for.
    """
    if block.key not in _NON_HEADING_BLOCKS:
        items = _container_items(block.data)
        if items:
            pairs = [r for item in items if (r := _item_heading(item))]
            if pairs:
                return pairs
    return [(block.heading, block.data)]


def resolve_expected_headings(blocks: list[OutlineBlock]) -> list[str]:
    """Headings the finished article should actually contain."""
    return [
        heading
        for block in blocks
        if block.key not in _NON_HEADING_BLOCKS
        for heading, _ in unwrap_block(block)
    ]


def resolve_required_headings(blocks: list[OutlineBlock]) -> list[str]:
    """The subset of expected headings whose schema field is non-Optional.

    Lets validation distinguish "the outline's optional FAQ block didn't make
    it" from "the article has no Solution section at all". A flat coverage
    percentage cannot tell those apart, so a landing page that dropped its
    Problem section scored 5/6 and passed with a warning.

    Only blocks that ARE a section contribute. A container block (blog's
    `structure`) yields one heading per child, and the children are individually
    optional even when the container itself is required — requiring every child
    heading verbatim would fail on any reasonable rewording.
    """
    return [
        block.heading
        for block in blocks
        if block.required
        and block.key not in _NON_HEADING_BLOCKS
        and _container_items(block.data) is None
    ]


def _render_value(value: Any, lines: list[str], indent: str, depth: int = 0) -> None:
    """Serialize approved values faithfully, by field name.

    Deliberately generic: it walks whatever the schema defines instead of
    consulting hand-maintained field-name tables, so a new schema field renders
    correctly with no registry update.
    """
    if depth > _MAX_DEPTH or _is_empty(value):
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            if _is_empty(sub):
                continue
            if isinstance(sub, (dict, list)):
                lines.append(f"{indent}- {humanize_key(key)}:")
                _render_value(sub, lines, indent + "  ", depth + 1)
            else:
                lines.append(f"{indent}- {humanize_key(key)}: {sub}")
    elif isinstance(value, list):
        for item in value:
            if _is_empty(item):
                continue
            if isinstance(item, dict):
                _render_value(item, lines, indent, depth + 1)
            else:
                lines.append(f"{indent}* {item}")
    else:
        lines.append(f"{indent}* {value}")


def format_structure_for_prompt(blocks: list[OutlineBlock], indent: str = "") -> str:
    """The approved structure as prompt text — every block, in schema order.

    Intentionally not truncated: the previous `blocks[:8]` cap silently dropped
    the tail of longer schemas (product-homepage has 13 structural blocks,
    sales-page 10).
    """
    lines: list[str] = []
    for block in blocks:
        for heading, data in unwrap_block(block):
            lines.append(f"{indent}## {heading}")
            _render_value(data, lines, indent + "  ")
    return "\n".join(lines)
