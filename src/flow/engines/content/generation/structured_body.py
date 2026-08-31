"""Derive a structured body model for an article from its APPROVED OUTLINE.

The outline is the single source of truth for structure. Its per-content-type
Pydantic model already declares which blocks exist and which are mandatory (a
non-Optional field), and `resolve_outline_structure` already reconciles that
schema against the values the user actually approved. This module turns that
same block list into a Pydantic model for the *article*, so structure is
enforced by constrained decoding at generation time instead of being requested
in prose and pattern-matched afterwards.

Deriving rather than hand-writing is the point. Thirty-four hand-maintained
content models mirroring thirty-four outline models is exactly the duplication
that drifts: add a field to an outline schema and the content schema silently
falls behind. Here a new outline field flows through with no second edit, and
the two definitions cannot disagree because there is only one.

What this module does NOT touch, by design:
  * `body_markdown` remains the representation everything downstream reads —
    persistence, the WordPress publisher, EEAT/on-page/readability scoring, the
    API schemas, and every existing validator. It becomes derived rather than
    generated; its consumers see no change.
  * Facts, internal/outbound links, images, CTA, schema markup and SEO metadata
    stay on `BaseGeneratedContent` as they are today. Research results (Tavily)
    stay in `generation_meta`, out of the output schema entirely.
  * Brand placement, validation and repair keep using the existing policy and
    check functions. Structure being reliable makes those checks easier to
    satisfy; it does not replace them.

Nothing here is wired into generation yet — this is the additive groundwork.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field, create_model

from src.flow.engines.content.generation.outline_structure import (
    OutlineBlock,
    resolve_outline_structure,
)
from src.flow.model.structure.contents.base import ContentBlock, blocks_to_body_markdown

logger = logging.getLogger(__name__)

# Key recording the block keys a structured generation actually produced.
# Underscore-prefixed so Pydantic's extra="ignore" drops it at the first
# model_validate downstream — it describes how this payload was produced, not
# part of the content contract, and it must not reach the DB or the API.
STRUCTURED_BLOCKS_KEY = "_structured_block_keys"

# Cache keyed on the block signature, not just the content type: two articles of
# the same type can resolve to different block sets, because
# resolve_outline_structure skips blocks the approved outline left empty and
# appends any user-added ones. Rebuilding an identical model per article would
# also defeat Pydantic's own schema caching.
_MODEL_CACHE: dict[tuple, type[BaseModel]] = {}


def _model_key(content_type: str, blocks: list[OutlineBlock]) -> tuple:
    return (content_type, tuple((b.key, b.required) for b in blocks))


def _field_description(block: OutlineBlock) -> str:
    requirement = (
        "REQUIRED — this content type declares this section mandatory; it must be written."
        if block.required
        else "Optional — write it when the approved outline gives it content, otherwise leave null."
    )
    return (
        f"The '{block.heading}' section of the article. {requirement} "
        f"Cover what the approved outline specifies for this block, and give it a "
        f"reader-facing heading rather than the field name."
    )


def build_structured_body_model(
    outline: dict,
    content_type: str,
    blocks: Optional[list[OutlineBlock]] = None,
) -> Optional[type[BaseModel]]:
    """A Pydantic model whose fields are this article's approved sections.

    Required outline blocks become required `ContentBlock` fields; optional ones
    become `Optional[ContentBlock] = None`. Field order follows the outline's
    schema declaration order, which is the same order the generation prompt and
    `blocks_to_body_markdown` use — so the plan the model is given, the object it
    returns and the assembled article can never disagree about ordering.

    Returns None when the outline resolves to no structural blocks (an empty or
    unrecognised outline), so callers can fall back to today's prose generation
    rather than fail. Structure being underivable is a reason to degrade, not to
    break a production run.
    """
    resolved = blocks if blocks is not None else resolve_outline_structure(outline, content_type)
    if not resolved:
        logger.info(
            "build_structured_body_model: no structural blocks for content_type=%s; "
            "caller should fall back to unstructured generation.", content_type,
        )
        return None

    key = _model_key(content_type, resolved)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    fields: dict[str, tuple] = {}
    for block in resolved:
        description = _field_description(block)
        if block.required:
            fields[block.key] = (ContentBlock, Field(description=description))
        else:
            fields[block.key] = (Optional[ContentBlock], Field(default=None, description=description))

    model_name = "".join(part.title() for part in content_type.split("-")) + "StructuredBody"
    model = create_model(model_name, **fields)
    _MODEL_CACHE[key] = model

    logger.info(
        "build_structured_body_model: content_type=%s blocks=%s required=%s",
        content_type,
        [b.key for b in resolved],
        [b.key for b in resolved if b.required],
    )
    return model


def structured_body_to_markdown(
    structured_body: BaseModel,
    blocks: list[OutlineBlock],
) -> str:
    """Assemble a filled structured body into `body_markdown`, in block order.

    Order comes from `blocks` rather than the model's own field order so that a
    single source — the resolved outline — governs both what is asked for and how
    it is laid out.
    """
    ordered = [
        (block.key, getattr(structured_body, block.key, None))
        for block in blocks
    ]
    return blocks_to_body_markdown(ordered)


def describe_expected_blocks(blocks: list[OutlineBlock]) -> str:
    """Human-readable required/optional summary, for prompts and logs."""
    return ", ".join(
        f"{b.key}{'' if b.required else ' (optional)'}" for b in blocks
    )


# Structured generation is on for every content type. The escape hatch is an
# EXCLUSION list rather than an allow-list, so a type opts out explicitly and a
# newly added content type is structured by default rather than silently
# reverting to prose.
#
# Nothing is excluded today. The candidate if generation proves unreliable is
# `comparison`, which resolves to the most blocks of any type in a single
# structured response — watch its retry rate first. Excluding a type here
# restores exactly today's prose generation for it, with no other change.
STRUCTURED_BODY_EXCLUDED_TYPES: frozenset[str] = frozenset()


def uses_structured_body(content_type: str) -> bool:
    from src.flow.model.structure.outlines import normalize_content_type

    return normalize_content_type(content_type) not in STRUCTURED_BODY_EXCLUDED_TYPES


def build_structured_content_model(
    outline: dict,
    content_type: str,
    base_model: type[BaseModel],
    blocks: Optional[list[OutlineBlock]] = None,
) -> Optional[tuple[type[BaseModel], list[OutlineBlock]]]:
    """`<Type>GeneratedContent` extended with one field per approved section.

    The base model is kept whole rather than replaced: every existing field —
    facts, internal/outbound links, images, CTA, schema markup, SEO metadata —
    stays exactly as it is, because none of them are part of the structure
    problem. Only the article's prose gains typed shape.

    `body_markdown` is left declared but is assembled from the blocks after
    generation (see `assemble_structured_payload`), so the model is not asked to
    produce the same prose twice.

    Returns (model, blocks), or None when structure can't be derived — the caller
    then generates exactly as it does today.
    """
    resolved = blocks if blocks is not None else resolve_outline_structure(outline, content_type)
    if not resolved:
        return None

    # A block key that matches an existing base field would REPLACE that field's
    # type. `cta` and `images` collide on all 34 content types: the base model
    # declares them as a typed CTABlock and a list of ImageAltText, and turning
    # either into a prose ContentBlock would break check_cta_presence, the
    # placeholder-image stripper and the WordPress featured-image lookup. Those
    # already have dedicated typed fields carrying them, so they must never
    # become prose blocks — drop them from the structured set and let the base
    # model keep ownership.
    reserved = set(base_model.model_fields)
    collisions = [b.key for b in resolved if b.key in reserved]
    if collisions:
        resolved = [b for b in resolved if b.key not in reserved]
        logger.info(
            "build_structured_content_model: content_type=%s blocks already owned by typed "
            "base fields, left to the base model: %s", content_type, collisions,
        )
    if not resolved:
        logger.info(
            "build_structured_content_model: content_type=%s has no blocks left after "
            "collision filtering; using unstructured generation.", content_type,
        )
        return None

    key = ("content", base_model.__name__) + _model_key(content_type, resolved)[1:]
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached, resolved

    fields: dict[str, tuple] = {}
    for block in resolved:
        description = _field_description(block)
        if block.required:
            fields[block.key] = (ContentBlock, Field(description=description))
        else:
            fields[block.key] = (Optional[ContentBlock], Field(default=None, description=description))

    model_name = base_model.__name__ + "Structured"
    try:
        model = create_model(model_name, __base__=base_model, **fields)
    except Exception:
        # A block key colliding with an existing base field (or any other schema
        # conflict) must not take generation down — fall back to prose.
        logger.exception(
            "build_structured_content_model: could not extend %s for content_type=%s; "
            "falling back to unstructured generation.", base_model.__name__, content_type,
        )
        return None

    _MODEL_CACHE[key] = model
    logger.info(
        "build_structured_content_model: %s -> %s blocks=%s",
        base_model.__name__, model_name, describe_expected_blocks(resolved),
    )
    return model, resolved


def assemble_structured_payload(
    content_dict: dict,
    blocks: list[OutlineBlock],
) -> dict:
    """Collapse generated blocks into `body_markdown` and drop the block fields.

    After this, the payload has exactly the shape every downstream stage already
    expects — validation, repair, humanization, EEAT/on-page/readability scoring,
    persistence and the WordPress publisher all keep reading `body_markdown` and
    never learn that generation was structured. That is what makes the change
    backward-compatible.

    If the blocks produced nothing usable, any `body_markdown` the model happened
    to write is left in place rather than being replaced with an empty string.
    """
    ordered = []
    for block in blocks:
        raw = content_dict.get(block.key)
        if isinstance(raw, dict):
            try:
                ordered.append((block.key, ContentBlock(**raw)))
                continue
            except Exception:
                logger.warning("assemble_structured_payload: block %r malformed; skipping.", block.key)
        elif isinstance(raw, ContentBlock):
            ordered.append((block.key, raw))
            continue
        ordered.append((block.key, None))

    assembled = blocks_to_body_markdown(ordered)
    payload = {k: v for k, v in content_dict.items() if k not in {b.key for b in blocks}}

    written = [k for k, b in ordered if b is not None]
    missing_required = [b.key for b in blocks if b.required and b.key not in written]
    if missing_required:
        # Should be unreachable — these are required fields under constrained
        # decoding — but log rather than assume, so a provider that degrades to
        # best-effort output is visible instead of silent.
        logger.warning(
            "assemble_structured_payload: required block(s) absent after generation: %s",
            missing_required,
        )

    if assembled.strip():
        payload["body_markdown"] = assembled
    else:
        logger.warning("assemble_structured_payload: blocks produced no markdown; keeping model output.")

    # Record which sections were actually written, so validation can verify
    # section presence directly instead of pattern-matching headings.
    #
    # This matters because the two disagree by design: `expected_sections` holds
    # SCHEMA labels ("Problem", "Objection Handling"), while a structured block's
    # heading is deliberately reader-facing ("Buying Without Clarity") — emitting
    # the field name as a heading is the very defect ContentBlock.heading exists
    # to prevent. Left alone, check_required_sections would report every
    # structured article as missing its required sections.
    #
    # Underscore-prefixed and therefore dropped by Pydantic's extra="ignore" on
    # the first model_validate downstream, which is correct: after humanization
    # rewrites body_markdown freely, block provenance no longer holds and the
    # heading-based check should apply again.
    payload[STRUCTURED_BLOCKS_KEY] = written

    logger.info(
        "assemble_structured_payload: blocks_written=%s/%s body_chars=%s",
        len(written), len(blocks), len(assembled),
    )
    return payload
