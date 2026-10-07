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
from src.flow.model.structure.outlines.common import (
    DEFAULT_GUIDANCE_FIELDS,
    OutlineContract,
)

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
#
# It is also only the DEFAULT. A schema that subclasses `OutlineContract`
# declares its own `GUIDANCE_FIELDS` ClassVar and `_guidance_fields_for()`
# reads it from the model — so adding a guidance field to a schema no longer
# requires editing this module. Schemas not yet migrated fall back to this set,
# which is why it must stay a superset of what they use.
_GUIDANCE_FIELDS = DEFAULT_GUIDANCE_FIELDS | frozenset(
    {
        "seo",
        "search_intent",
        "key_facts",
        "facts",
        "image_suggestions",
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
    }
)

# Keys on the outline dict that are metadata, never structural blocks. Used
# only when scanning for user/LLM-added keys the Pydantic model doesn't know
# about, so an unrecognised *section* is preserved while ordinary metadata is
# not mistaken for one.
_NON_STRUCTURAL_KEYS = frozenset(
    {
        "title",
        "slug",
        "slug_suggestion",
        "focus_keyphrase",
        "keywords_to_include",
        "secondary_keywords",
        "target_audience",
        "tone",
        "target_word_count",
        "content_goal",
        "conversion_goal",
        "traffic_source",
        "campaign_name",
        "reading_time",
        "schema_type",
        "status",
        "rejected_reason",
        "brief",
        "lead_magnet",
        "visual_direction",
        "promote_brand",
        "brand_prominence",
        "brand_voice_promotion",
        "selected_persona_id",
        "persona_recommendations",
        "cluster_heading_map",
        "key_facts",
        "facts",
    }
)
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

    key: str  # schema field name, e.g. "hero"
    heading: str  # human label, e.g. "Hero"
    required: bool  # the schema field is non-Optional
    data: Any  # the approved values, verbatim from the outline dict
    order: int  # position in the schema's declaration order
    # Set only on a planned section expanded from a container block
    # (expand_section_containers): the container's key, the section's heading
    # level in the article, and its place among the container's sections.
    parent: str | None = None
    level: int = 2
    position: int = 0
    of: int = 0


# Acronyms that .title() would mangle ("Cta", "Faq") — these end up as headings
# in the prompt and, via _expected_sections, as the labels validation matches
# against, so they need to read correctly.
_ACRONYMS = {
    "cta": "CTA",
    "faq": "FAQ",
    "faqs": "FAQs",
    "seo": "SEO",
    "ux": "UX",
    "roi": "ROI",
    "eeat": "E-E-A-T",
    "url": "URL",
    "urls": "URLs",
    "api": "API",
    "paa": "PAA",
}


def humanize_key(key: str) -> str:
    return " ".join(_ACRONYMS.get(word, word.title()) for word in key.split("_"))


def is_cta_key(key: str) -> bool:
    """A field naming a call to action: `cta`, `primary_cta`, `final_cta`, `repeated_ctas`, `cta_text`."""
    return any(word in ("cta", "ctas") for word in str(key).lower().split("_"))


def _guidance_fields_for(model: Any) -> frozenset[str]:
    """Which fields this schema treats as guidance rather than sections.

    Asks the model first (`OutlineContract.GUIDANCE_FIELDS`), so a schema owns
    its own classification and this module stays closed for modification when a
    new schema field is added. Falls back to the module default for the schemas
    that have not been migrated onto `OutlineContract` yet.
    """
    if isinstance(model, type) and issubclass(model, OutlineContract):
        declared = getattr(model, "GUIDANCE_FIELDS", None)
        if declared:
            return frozenset(declared)
    return _GUIDANCE_FIELDS


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
    guidance_fields = _guidance_fields_for(model)
    blocks: list[OutlineBlock] = []
    skipped_required: list[str] = []
    skipped_empty: list[str] = []

    known_fields: set[str] = set()

    if model is not None:
        for order, (name, field) in enumerate(model.model_fields.items()):
            known_fields.add(name)
            if name in guidance_fields or not _is_structural(field.annotation):
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
        logger.warning(
            "resolve_outline_structure: no outline model for content_type=%r", content_type
        )

    # Keys the schema doesn't define — a user-added section, or LLM drift.
    # Kept and appended rather than dropped: silently discarding unrecognised
    # structure is precisely the failure this module exists to end.
    extra: list[str] = []
    for name, value in outline.items():
        if name in known_fields or name.startswith("_"):
            continue
        if name in _NON_STRUCTURAL_KEYS or name in guidance_fields:
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
        content_type,
        [b.key for b in blocks],
        skipped_empty,
        skipped_required,
        extra,
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


def item_heading_field(item: dict) -> str | None:
    """The field that carries this item's own heading, as `_item_heading` reads it."""
    for field in _ITEM_HEADING_FIELDS:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return field
    return None


def section_containers(blocks: list[OutlineBlock]) -> list[tuple[str, list[dict]]]:
    """The lists of sections in the approved structure, with their path in the outline dict.

    These are the containers `unwrap_block` turns into one heading per item, so
    the rows a reviewer reorders or renames are exactly the headings the article
    is written and checked against. The path is "<field>" for a list and
    "<field>.<key>" for a one-key wrapper (blog's `content_structure.sections`).
    """
    containers = []
    for block in blocks:
        if block.key in _NON_HEADING_BLOCKS:
            continue
        items = _container_items(block.data)
        if not items or not any(item_heading_field(item) for item in items):
            continue
        path = block.key
        if isinstance(block.data, dict):
            path = f"{block.key}.{next(iter(block.data))}"
        containers.append((path, items))
    return containers


# A guard on the writer's schema, far above any real outline: only lists of
# sections expand (lists of entries never do), and a pillar page's can be long.
MAX_EXPANDED_SECTIONS = 40


def _item_level(item: dict) -> int:
    """The section's heading level: 2, 3 or 4 ("H2"-"H4"; a pillar section may be an H4)."""
    level = str(item.get("heading_level") or "").strip().upper().removeprefix("H")
    return int(level) if level in {"2", "3", "4"} else 2


def _planned_children(
    block: OutlineBlock, reserved: frozenset[str] = frozenset()
) -> list[OutlineBlock]:
    """A container block's planned sections, one block each, in the approved order.

    Only a list of sections: items with their own `heading` (blog's and
    pillar-content's `structure.sections`). Lists of entries keyed by a name, a
    term or a question (tools, products, glossary terms) are the content of one
    section, and a container a typed field of the content model owns
    (`reserved`: how-to-guide's `steps`) is written through that field.
    """
    if block.key in _NON_HEADING_BLOCKS or block.key in reserved:
        return []
    items = _container_items(block.data)
    if not items:
        return []
    titled = [(item, "heading") for item in items if item_heading_field(item) == "heading"]
    if not titled or len(titled) != len(items) or len(titled) > MAX_EXPANDED_SECTIONS:
        return []
    return [
        OutlineBlock(
            key=f"{block.key}_{position}",
            heading=item[field].strip(),
            required=block.required,
            data=item,
            order=block.order,
            parent=block.key,
            level=_item_level(item),
            position=position,
            of=len(titled),
        )
        for position, (item, field) in enumerate(titled, 1)
    ]


def expand_section_containers(
    blocks: list[OutlineBlock], reserved: frozenset[str] = frozenset()
) -> list[OutlineBlock]:
    """The writer's sections: each container block replaced by its planned sections.

    Blog's whole body is one block (`structure`, a list of sections). Given one
    field for it, the writer wrote one heading with the planned sections folded
    under it as H3s, so a four-section outline came back as two H2s
    (rext-control#329). Expanded, every planned section is a field of its own,
    in the approved order, so it can't be merged away or reordered.
    """
    expanded: list[OutlineBlock] = []
    for block in blocks:
        expanded.extend(_planned_children(block, reserved) or [block])
    return expanded


def planned_sections(
    blocks: list[OutlineBlock], reserved: frozenset[str] = frozenset()
) -> list[OutlineBlock]:
    """Every section the approved outline plans inside a container, in order."""
    return [child for block in blocks for child in _planned_children(block, reserved)]


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


# Outline bookkeeping that must never reach the writer. These fields exist to
# let the pipeline SIZE and ORDER the article, not to instruct the person
# writing it.
#
# `suggested_word_count` is the case that matters: `generate_outline` sums it
# into `target_word_count`, which is the single number the reviewer approves and
# generation enforces (`max_word_count = target + 15%`). Rendering the per-section
# figure as well handed the writer a second, competing budget — a quota per
# section on top of the approved total — which is not what was approved.
_PROMPT_SUPPRESSED_FIELDS = frozenset(
    {
        "suggested_word_count",
    }
)


# A call to action is an instruction, never content to copy. Rendered like any other
# field ("- Primary CTA: Explore Features") the writer printed it into the article
# as a bold label line, so it is phrased as what to write instead: the CTA fields
# themselves, and the lines a CTA block carries beside them (reassurance text, an
# urgency message, a context line).
_CTA_BLOCK_HEADING = "Call to action (a closing paragraph, not a heading of its own)"
_CTA_GROUP_LINE = (
    "Calls to action, each written as a sentence or a link (never as a labelled line):"
)


def _cta_line(key: str, text: Any) -> str:
    if is_cta_key(key):
        return f'Invite the reader to "{text}" here, in a sentence or a link (never as a labelled line)'
    return (
        f"With the call to action, work in its {humanize_key(key).lower()} in your own words: "
        f'"{text}" (never as a labelled line)'
    )


def _cta_list_line(key: str) -> str:
    return (
        f"With the call to action, work in its {humanize_key(key).lower()} in your own words "
        "(never under a label):"
    )


def _render_value(
    value: Any, lines: list[str], indent: str, depth: int = 0, in_cta: bool = False
) -> None:
    """Serialize approved values faithfully, by field name.

    Deliberately generic: it walks whatever the schema defines instead of
    consulting hand-maintained field-name tables, so a new schema field renders
    correctly with no registry update. A call to action, and everything a CTA
    block holds (`in_cta`), is rendered as an instruction instead of a field.
    """
    if depth > _MAX_DEPTH or _is_empty(value):
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            if key in _PROMPT_SUPPRESSED_FIELDS:
                continue
            # A false flag is not an instruction. "Snippet Target: False" and
            # "Include Keyphrase In Heading: False" told the writer nothing and
            # padded every section of the plan; only the true ones carry intent.
            if sub is False:
                continue
            if _is_empty(sub):
                continue
            cta = in_cta or is_cta_key(key)
            if cta and not isinstance(sub, (dict, list)):
                lines.append(f"{indent}- {_cta_line(key, sub)}")
            elif cta and isinstance(sub, list) and all(isinstance(i, str) for i in sub):
                if is_cta_key(key):
                    lines.extend(f"{indent}- {_cta_line(key, item)}" for item in sub if item)
                else:
                    lines.append(f"{indent}- {_cta_list_line(key)}")
                    lines.extend(f"{indent}  * {item}" for item in sub if item)
            elif isinstance(sub, (dict, list)):
                lines.append(
                    f"{indent}- {_CTA_GROUP_LINE if is_cta_key(key) else humanize_key(key) + ':'}"
                )
                _render_value(sub, lines, indent + "  ", depth + 1, in_cta=cta)
            else:
                lines.append(f"{indent}- {humanize_key(key)}: {sub}")
    elif isinstance(value, list):
        for item in value:
            if _is_empty(item):
                continue
            if isinstance(item, dict):
                _render_value(item, lines, indent, depth + 1, in_cta=in_cta)
            else:
                lines.append(f"{indent}* {item}")
    else:
        lines.append(f"{indent}* {value}")


def section_plan_text(data: Any) -> str:
    """A planned section's own words (description, key points), for matching it in an article."""
    words: list[str] = []

    def collect(value: Any, depth: int = 0) -> None:
        if depth > _MAX_DEPTH:
            return
        if isinstance(value, dict):
            field = item_heading_field(value) if depth == 0 else None
            for key, sub in value.items():
                if key not in {field, "heading_level"} and key not in _PROMPT_SUPPRESSED_FIELDS:
                    collect(sub, depth + 1)
        elif isinstance(value, list):
            for item in value:
                collect(item, depth + 1)
        elif isinstance(value, str):
            words.append(value)

    collect(data)
    return " ".join(words)


def render_section_plan(data: Any) -> str:
    """A planned section's own plan (its description, key points, flags) as prompt lines."""
    lines: list[str] = []
    if isinstance(data, dict):
        field = item_heading_field(data)
        data = {k: v for k, v in data.items() if k not in {field, "heading_level"}}
    _render_value(data, lines, "")
    return "\n".join(lines)


def format_structure_for_prompt(blocks: list[OutlineBlock], indent: str = "") -> str:
    """The approved structure as prompt text — every block, in schema order.

    Intentionally not truncated: the previous `blocks[:8]` cap silently dropped
    the tail of longer schemas (product-homepage has 13 structural blocks,
    sales-page 10).
    """
    lines: list[str] = []
    for block in blocks:
        for heading, data in unwrap_block(block):
            if is_cta_key(block.key):
                heading = _CTA_BLOCK_HEADING
            lines.append(f"{indent}## {heading}")
            if is_cta_key(block.key) and not isinstance(data, (dict, list)):
                lines.append(f"{indent}  - {_cta_line(block.key, data)}")
                continue
            _render_value(data, lines, indent + "  ", in_cta=is_cta_key(block.key))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Guidance blocks
# ---------------------------------------------------------------------------
#
# The mirror image of resolve_outline_structure(): the fields it deliberately
# SKIPS are resolved here instead. Without this they were generated by the
# outline model, shown to the human for approval, and then silently dropped —
# `eeat`, `engagement`, `topic_cluster` and `references` had zero readers
# anywhere in the pipeline, so a reviewer could approve E-E-A-T signals and a
# reference list that provably could not affect the article.
#
# They are rendered as WRITING INSTRUCTIONS, never as sections, which is the
# distinction that put them in the guidance set to begin with.

# How to act on each guidance block. Only an instruction line — the values
# themselves are rendered generically by _render_value — so this never becomes a
# structural registry. A key with no entry still renders, under its own label.
_GUIDANCE_DIRECTIVES: dict[str, str] = {
    "eeat": (
        "Weave these E-E-A-T signals into the prose. Do not list them or write a "
        "section about them — demonstrate them: first-hand detail for experience, "
        "precision for expertise, sourcing for authority, and stated limits for trust."
    ),
    "engagement": (
        "Place each of these concretely, in the section where it lands best. "
        "A statistic needs its source; an analogy belongs where the concept is "
        "first explained."
    ),
    "topic_cluster": (
        "Cover these supporting topics and use this semantic vocabulary naturally "
        "throughout, so the article reads as topically complete rather than thin."
    ),
    "search_intent": (
        "Satisfy this intent explicitly and early — the reader's goal must be met "
        "in the opening screenful, not deferred to the conclusion."
    ),
    "seo": (
        "Use these variants and secondary terms naturally. Never repeat the focus "
        "keyphrase mechanically; vary phrasing the way a human writer would."
    ),
    "references": (
        "Cite these sources inline, at the exact sentence making the claim they "
        "support. Never append them as a bare list at the end."
    ),
    "ux": "Apply this to formatting, paragraph length, and scannability.",
}


# Guidance fields that content_generation already injects through a dedicated,
# more specific prompt block: LINKS TO EMBED, KEY FACTS TO INCLUDE IN CONTENT,
# IMAGE PLACEMENT GUIDE. Those blocks carry enforcement language this generic
# renderer cannot, so they win.
_SEPARATELY_INJECTED = frozenset(
    {
        "internal_links",
        "internal_linking",
        "key_facts",
        "facts",
        "image_suggestions",
    }
)


def resolve_guidance_blocks(outline: dict, content_type: str) -> list[OutlineBlock]:
    """The approved planning fields that shape writing but are not sections.

    Same reconciliation as `resolve_outline_structure`, over the complementary
    set of fields, so neither can silently swallow a field the other skipped.
    """
    outline = outline or {}
    model = get_outline_model(content_type)
    if model is None:
        return []

    guidance_fields = _guidance_fields_for(model)
    blocks: list[OutlineBlock] = []

    for order, (name, field) in enumerate(model.model_fields.items()):
        if name not in guidance_fields or not _is_structural(field.annotation):
            continue
        # Injected through their own dedicated prompt blocks; rendering them
        # here too would double-instruct the writer.
        if name in _SEPARATELY_INJECTED:
            continue
        value = outline.get(name)
        if _is_empty(value):
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

    logger.info(
        "resolve_guidance_blocks: content_type=%s used=%s",
        content_type,
        [b.key for b in blocks],
    )
    return blocks


def format_guidance_for_prompt(blocks: list[OutlineBlock]) -> str:
    """The approved guidance as prompt text. Empty string when there is none."""
    if not blocks:
        return ""

    lines = [
        "========================",
        "WRITING GUIDANCE (approved in the outline — apply, do NOT write sections about)",
        "========================",
    ]
    for block in blocks:
        lines.append(f"{block.heading}:")
        directive = _GUIDANCE_DIRECTIVES.get(block.key)
        if directive:
            lines.append(f"  ({directive})")
        _render_value(block.data, lines, "  ")
    return "\n".join(lines)
