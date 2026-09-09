"""Humanization LangGraph node.

Extracted from the former HumanizeMiddleware (agent aafter_agent hook) into a
plain node so it runs only after validate_content/repair_content have passed
(or given up) — never unconditionally right after generation. Image-task
resolution stayed in generate_content (it needs the in-process asyncio Task,
which can't cross a graph-node boundary / checkpoint); this node deals purely
with serializable structured content, so it needs no counters at all.
"""

import logging
import re
from typing import Any

from pydantic import BaseModel

from src.flow.engines.content.generation.brand_placement_policy import (
    BrandPlacementPolicy,
    build_brand_structural_injection,
    resolve_brand_placement_policy,
)
from src.flow.engines.content.generation.repair_content import run_targeted_repair
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.validation import check_brand_placement_policy
from src.flow.engines.content.generation.word_count_utils import compute_word_target_band
from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

DEFAULT_WORD_TARGET = 3000
SECTION_MIN_FRACTION = (
    0.5  # a section is "too short" if under 50% of its proportional share of the target
)

HUMANIZED_FIELDS = {
    "introduction",
    "body_markdown",
}


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            return {}
    return {}


def _mention_present(text: str, brand_name: str) -> bool:
    return bool(brand_name) and brand_name.strip().lower() in (text or "").lower()


def _build_brand_instruction(
    *,
    brand_name: str,
    brand_url: str,
    content_type: str,
    policy: BrandPlacementPolicy,
) -> str:
    """Content-type-aware brand integration instruction for the humanize rewrite pass.

    Deliberately stronger than a plain "preserve this mention" note: it tells
    the model the correct WHERE/HOW for this content type (see
    brand_placement_policy.py) so humanization actively fixes a weak or
    misplaced mention instead of just leaving it wherever generation
    happened to put it.
    """
    link_clause = (
        f" Hyperlink it to {brand_url} exactly once — keep or restore that link on the brand name; "
        "never invent a different URL."
        if brand_url
        else " Mention it as plain text only — do not add a link."
    )
    placement_line = (
        policy["forced_fallback"]
        if policy["intensity"] == "none" and policy.get("forced_fallback")
        else policy["placement"]
    )
    structural_injection = build_brand_structural_injection(content_type, brand_name, policy)

    return (
        f'BRAND INTEGRATION — REQUIRED: this article carries one approved mention of "{brand_name}". '
        "While rewriting for human tone, also make sure it is placed and weighted correctly for this "
        "content type — reposition or rewrite it if the current draft has it in the wrong place or as a "
        "weak, bolted-on name-drop; do not just leave it untouched if it doesn't comply.\n"
        f"- PLACEMENT: {placement_line}\n"
        f"- FORMAT GUARDRAIL: {policy['guardrail']}\n"
        "- Write it as strong, natural, specific copy — a real benefit or use-case woven into a full "
        f"sentence, never a bare name-drop.{link_clause}\n"
        f"{structural_injection}"
    )


def _build_prompt_data(
    *,
    content_payload: dict[str, Any],
    word_target: int = DEFAULT_WORD_TARGET,
    brand_context: dict[str, str] | None = None,
    content_type: str = "",
) -> dict[str, Any]:
    introduction = content_payload.get("introduction") or ""
    body_markdown = content_payload.get("body_markdown") or ""
    total_words = len((introduction + " " + body_markdown).split())

    raw_sections = re.split(r"(?=^## )", body_markdown, flags=re.MULTILINE)
    section_bodies = [
        s.strip() for s in raw_sections if s.strip() and re.match(r"^## (.+)", s.strip())
    ]
    num_sections = len(section_bodies) or 1

    total_min, total_max = compute_word_target_band(word_target)
    total_target = word_target
    section_min = max(40, round((word_target / num_sections) * SECTION_MIN_FRACTION))
    deficit = total_target - total_words
    excess = total_words - total_max

    logger.info(
        "humanize_content: word count = %d / range %d-%d (section_min=%d, sections=%d)",
        total_words,
        total_min,
        total_max,
        section_min,
        num_sections,
    )

    if deficit > 0:
        short_headings = [
            re.match(r"^## (.+)", s).group(1)
            for s in section_bodies
            if len(s.split()) < section_min
        ]
        if short_headings:
            expand_note = (
                f"These sections are under {section_min} words — expand each one: "
                f"{', '.join(short_headings)}. "
                "Add a real example, step-by-step breakdown, common mistakes, or a persona anecdote to each."
            )
        else:
            expand_note = f"Add {deficit} more words spread across sections — deepen explanations with examples or anecdotes."

        length_instruction = (
            f"LENGTH REQUIREMENT: Article has {total_words} words. Target range is {total_target}-{total_max}. "
            f"While rewriting, also EXPAND the content by {deficit} words. {expand_note} "
            "Do not pad with filler — expand with substance."
        )
    elif excess > 0:
        length_instruction = (
            f"LENGTH REQUIREMENT: Article has {total_words} words. Target range is {total_target}-{total_max}. "
            f"While rewriting, also TRIM the content by roughly {excess} words — cut filler, redundant transitions, "
            "and repeated points. Keep every fact, citation, and link intact; tighten prose, don't remove substance."
        )
    else:
        length_instruction = (
            f"Article has {total_words} words — within the {total_target}-{total_max} target range. "
            "Rewrite for human tone only."
        )

    brand_instruction = ""
    if brand_context:
        policy = resolve_brand_placement_policy(content_type)
        brand_instruction = _build_brand_instruction(
            brand_name=brand_context["brand_name"],
            brand_url=brand_context.get("brand_url", ""),
            content_type=content_type,
            policy=policy,
        )

    return {
        "title": content_payload.get("title") or "",
        "introduction": introduction,
        "body_markdown": body_markdown,
        "length_instruction": length_instruction,
        "brand_instruction": brand_instruction,
    }


async def humanize_content(state: REXT) -> dict:
    """Rewrite introduction/body_markdown for human tone, after the quality gate has passed.

    Runs unconditionally exactly once per article (never mid-repair-loop) —
    the validate_content/repair_content loop is fully resolved (pass or
    give-up) before the graph routes here. Soft-fails on any error: keeps
    the pre-humanize content rather than blocking the pipeline.
    """
    content_state = state.get("content") or {}
    final_content = content_state.get("final_content") or {}
    content_type = content_state.get("content_type", "")
    outline = content_state.get("outline") or {}

    if not final_content:
        logger.debug("humanize_content: no final_content found; skipping.")
        return {}

    original_payload = dict(final_content)
    body_markdown = (original_payload.get("body_markdown") or "").strip()
    if not body_markdown:
        logger.info("humanize_content: body_markdown missing; skipping.")
        return {}

    schema = get_generated_content_model(content_type)
    if schema is None:
        logger.warning("humanize_content: no schema for content_type=%r; skipping.", content_type)
        return {}

    word_target = outline.get("target_word_count", DEFAULT_WORD_TARGET)
    spec = build_requirements_spec(outline, content_type)
    brand_context = spec.get("brand_context")
    prompt_data = _build_prompt_data(
        content_payload=original_payload,
        word_target=word_target,
        brand_context=brand_context,
        content_type=content_type,
    )
    model = load_humanize_model().with_structured_output(schema)
    messages = get_humanize_prompt().format_messages(**prompt_data)

    logger.info("humanize_content: invoking humanization model.")
    try:
        humanized_obj = await model.ainvoke(messages)
    except Exception:
        logger.exception(
            "humanize_content: humanization model failed; keeping pre-humanize content."
        )
        return {}

    humanized_payload = _to_dict(humanized_obj)
    if not humanized_payload:
        logger.warning("humanize_content: empty humanized payload; keeping pre-humanize content.")
        return {}

    merged_payload = dict(original_payload)
    for key in HUMANIZED_FIELDS:
        if key not in humanized_payload:
            continue
        value = humanized_payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        merged_payload[key] = value

    # Guarantee the user-approved brand mention both survived humanization AND
    # still complies with this content type's placement policy — the rewrite
    # pass above (via _build_brand_instruction) is told where it belongs, but
    # isn't trusted blindly. Verify deterministically: first presence (it may
    # have been dropped entirely), then position (it may have merely drifted
    # into the wrong place — e.g. into the introduction for a body-only type,
    # or buried past the hero window for a prefers_top type). Each failure
    # mode gets its own single surgical repair pass rather than re-running the
    # broad rewrite, which risks losing the mention again.
    if brand_context:
        brand_name = brand_context["brand_name"]
        combined_text = (
            f"{merged_payload.get('introduction', '')}\n\n{merged_payload.get('body_markdown', '')}"
        )
        failed_check: dict[str, Any] | None = None
        if not _mention_present(combined_text, brand_name):
            failed_check = {
                "name": "brand_presence",
                "passed": False,
                "severity": "blocking",
                "detail": f"Approved brand mention '{brand_name}' is missing after humanization.",
            }
        else:
            placement_result = check_brand_placement_policy(merged_payload, spec)
            if not placement_result["passed"]:
                failed_check = placement_result

        if failed_check:
            logger.warning(
                "humanize_content: brand check '%s' failed after humanization (%s) — attempting repair.",
                failed_check["name"],
                failed_check["detail"],
            )
            # Same repair implementation repair_content uses pre-humanize —
            # one repair prompt/pathway instead of two independently-worded
            # ones that could drift out of sync with each other.
            repaired = await run_targeted_repair(
                final_content=merged_payload,
                content_type=content_type,
                failed_checks=[failed_check],
                brand_context=brand_context,
                article_stage="post-humanization (tone finalized — preserve it)",
            )
            if repaired is not None:
                recheck_present = _mention_present(
                    f"{repaired.get('introduction', '')}\n\n{repaired.get('body_markdown', '')}",
                    brand_name,
                )
                recheck_placed = (
                    recheck_present and check_brand_placement_policy(repaired, spec)["passed"]
                )
                fixed = (
                    recheck_placed
                    if failed_check["name"] == "brand_placement_policy"
                    else recheck_present
                )
                if fixed:
                    merged_payload = repaired
                    logger.info("humanize_content: brand mention repaired successfully.")
                else:
                    logger.warning(
                        "humanize_content: brand repair did not resolve '%s' — keeping content as-is.",
                        failed_check["name"],
                    )
            else:
                logger.warning(
                    "humanize_content: brand repair call failed — keeping content with the "
                    "unresolved '%s' issue.",
                    failed_check["name"],
                )

    # Re-validate through the Pydantic model so enforce_internal_links_in_body
    # (and the other model_validators) re-apply — humanization can drop a link
    # that was previously woven in; this is the same deterministic safety net
    # that already runs on every construction of this model. model_dump()
    # only covers schema fields, so bookkeeping keys generate_content adds
    # outside the schema (status, rejected_reason) must be layered back on
    # top or model_validate's extra="ignore" default silently drops them.
    try:
        revalidated = schema.model_validate(merged_payload)
        merged_payload = {**merged_payload, **revalidated.model_dump()}
    except Exception:
        logger.exception(
            "humanize_content: post-humanize re-validation failed; using merged payload as-is."
        )

    logger.info("humanize_content: content humanization applied successfully.")
    return {
        "content": {
            **content_state,
            "final_content": merged_payload,
        }
    }
