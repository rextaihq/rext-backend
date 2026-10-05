"""Resolve the approved brand's placement rules into schema-level guidance.

The rules themselves live in `brand_placement_policy.py` and the structural
decision lives in `brand_slot.py`. This module owns neither — it is the adapter
that turns `content_type + brand approved?` into a `SchemaContext` the model
builder can fold into a generated content model, and it writes no rule text of
its own beyond the framing around values it reads from those two modules.

Why the schema and not just the prompt
--------------------------------------
The brand rules already reach the writer as prose, twice: the PRODUCT-LED
MENTION block in the human message and a shorter reinforcement in the system
prompt. Both remain, and remain the place the detailed rules are rendered.

What neither can do is travel WITH the field. The human message also carries
competitor insights, the full outline, keyword clusters, guidance blocks, key
facts, evidence, image suggestions, internal links, schema.org data and the
reference page content — on a long article an instruction in the middle of that
is measurably under-weighted by the time the model writes the section it governs.
A field description is re-read at the moment that field is decoded, and the
model docstring becomes the structured-output tool's own description. Same
rules, delivered where they are acted on.

Only the current content type's policy is ever resolved. The other 33 never
enter the schema, so this costs roughly a hundred tokens rather than the whole
table.
"""

from __future__ import annotations

import logging

from src.flow.engines.content.generation.brand_placement_policy import (
    BrandPlacementPolicy,
    build_brand_structural_injection,
    resolve_article_brand_policy,
    resolve_placement_instruction,
)
from src.flow.engines.content.generation.brand_slot import SLOT_BLOCK_KEYS
from src.flow.engines.content.generation.outline_structure import OutlineBlock
from src.flow.model.structure.contents.base import EMPTY_SCHEMA_CONTEXT, SchemaContext
from src.flow.model.structure.outlines import normalize_content_type

logger = logging.getLogger(__name__)


def _resolve_target_keys(
    promo: dict,
    blocks: list[OutlineBlock],
    policy: BrandPlacementPolicy,
) -> tuple[str, ...]:
    """Which generated field(s) must carry the brand.

    Reads the decision `apply_brand_slot_to_outline` already made, rather than
    re-deriving it — that dispatch is the single source of truth for where an
    approved brand mention belongs, and a second copy of it here would be free
    to drift from the outline the writer is actually looking at.

    The recorded keys are intersected with the blocks that survived into the
    model, because `build_structured_content_model` drops blocks that collide
    with typed base fields; a directive on a field that does not exist would be
    silently dropped by Pydantic.
    """
    available = {block.key for block in blocks}

    recorded = promo.get(SLOT_BLOCK_KEYS)
    if isinstance(recorded, (list, tuple)):
        matched = tuple(key for key in recorded if key in available)
        if matched:
            return matched
        if recorded:
            logger.info(
                "brand_schema_context: recorded slot blocks %s are not fields on this "
                "model; falling back to positional targeting.",
                list(recorded),
            )

    # No slot was recorded — either the outline shape didn't match at approval
    # time (apply_brand_slot_to_outline soft-fails) or this outline predates that
    # step. For a type whose policy wants the brand up top, the first resolved
    # block IS the opening/hero section, so target it; otherwise leave the
    # placement to the model-level directive and the prompt rather than guess a
    # body section, which would be a second placement decision.
    if policy["prefers_top"] and blocks:
        return (blocks[0].key,)
    return ()


def _field_directive(brand_name: str, policy: BrandPlacementPolicy, anchor: str) -> str:
    placement, forced = resolve_placement_instruction(policy)
    exception_note = (
        " (this content type normally carries no product promotion; it was approved "
        "for this specific article anyway)"
        if forced
        else ""
    )
    lines = [
        f"BRAND PLACEMENT — this section carries the user-approved mention of "
        f"{brand_name}{exception_note}.",
        f"PLACEMENT: {placement}",
        f"GUARDRAIL: {policy['guardrail']}",
    ]
    if anchor:
        lines.append(anchor.strip())
    return "\n".join(lines)


def _model_directive(
    brand_name: str,
    content_type: str,
    policy: BrandPlacementPolicy,
    anchor: str,
    target_keys: tuple[str, ...],
) -> str:
    placement, forced = resolve_placement_instruction(policy)
    lines = [
        f"BRAND INTEGRATION — {brand_name} — USER-APPROVED AND REQUIRED for this "
        f"{content_type}. The reader approved this promotion at the outline stage; it is "
        f"a required element of the output, not an optional flourish.",
        f"Intensity for this content type: {policy['intensity']}"
        + (
            " (approved as an exception to this format's normal no-promotion rule)"
            if forced
            else ""
        ),
        f"PLACEMENT: {placement}",
        f"GUARDRAIL: {policy['guardrail']}",
    ]
    if target_keys:
        fields = ", ".join(f"`{key}`" for key in target_keys)
        if policy.get("prominence") == "prominent":
            # The user chose several mentions: the slot holds one of them, and
            # the PLACEMENT above says where the others go.
            lines.append(
                f"One mention belongs in {fields}; the PLACEMENT above says where the others go."
            )
        else:
            lines.append(
                f"The mention belongs in {fields}. A well-written mention in the wrong field "
                f"is still a failure."
            )
    if anchor:
        lines.append(anchor.strip())
    return "\n".join(lines)


def resolve_brand_schema_context(
    outline: dict,
    content_type: str,
    blocks: list[OutlineBlock],
) -> SchemaContext:
    """Schema-level brand guidance for THIS article, or an empty context.

    The single gate: returns `EMPTY_SCHEMA_CONTEXT` whenever the brand was not
    approved (or was approved without a usable name), and an empty context
    contributes nothing to either the schema or the model cache key — so a
    brand-disabled run produces byte-identical output to one built before this
    module existed.
    """
    outline = outline or {}
    if not outline.get("promote_brand"):
        return EMPTY_SCHEMA_CONTEXT

    promo = outline.get("brand_voice_promotion") or {}
    brand_name = (promo.get("brand_name") or "").strip()
    if not brand_name:
        logger.info("brand_schema_context: promote_brand set but no brand_name; injecting nothing.")
        return EMPTY_SCHEMA_CONTEXT

    normalized = normalize_content_type(content_type)
    policy = resolve_article_brand_policy(normalized, outline)
    anchor = build_brand_structural_injection(normalized, brand_name, policy)
    target_keys = _resolve_target_keys(promo, blocks, policy)

    field_directive = _field_directive(brand_name, policy, anchor)
    context = SchemaContext(
        model_directive=_model_directive(
            brand_name,
            normalized,
            policy,
            anchor,
            target_keys,
        ),
        field_directives={key: field_directive for key in target_keys},
        # Everything that can change the injected text. Folded into the model
        # cache key by the builder, so a brand-approved model can never be handed
        # to a brand-disabled run of the same content type and block set.
        signature=(normalized, brand_name, policy["intensity"], target_keys),
    )

    logger.info(
        "brand_schema_context: content_type=%s brand=%r intensity=%s target_fields=%s",
        normalized,
        brand_name,
        policy["intensity"],
        list(target_keys),
    )
    return context
