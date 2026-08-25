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

from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.prompts.human.brand_repair import get_brand_repair_prompt
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.states.rext import REXT
from src.flow.engines.content.generation.word_count_utils import compute_word_target_band

logger = logging.getLogger(__name__)

DEFAULT_WORD_TARGET = 3000
SECTION_MIN_FRACTION = 0.5  # a section is "too short" if under 50% of its proportional share of the target

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


def _extract_brand_context(outline: dict[str, Any]) -> dict[str, str] | None:
    """Pull brand promotion info out of the outline, if the user approved a mention."""
    if not outline.get("promote_brand"):
        return None
    promo = outline.get("brand_voice_promotion") or {}
    brand_name = (promo.get("brand_name") or "").strip()
    if not brand_name:
        return None
    return {
        "brand_name": brand_name,
        "brand_url": (promo.get("brand_url") or "").strip(),
        "about": promo.get("about") or "",
        "selling_position": promo.get("selling_position") or "",
    }


def _build_prompt_data(
    *,
    content_payload: dict[str, Any],
    word_target: int = DEFAULT_WORD_TARGET,
    brand_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    introduction = content_payload.get("introduction") or ""
    body_markdown = content_payload.get("body_markdown") or ""
    total_words = len((introduction + " " + body_markdown).split())

    raw_sections = re.split(r'(?=^## )', body_markdown, flags=re.MULTILINE)
    section_bodies = [
        s.strip() for s in raw_sections
        if s.strip() and re.match(r'^## (.+)', s.strip())
    ]
    num_sections = len(section_bodies) or 1

    total_min, total_max = compute_word_target_band(word_target)
    total_target = word_target
    section_min = max(40, round((word_target / num_sections) * SECTION_MIN_FRACTION))
    deficit = total_target - total_words
    excess = total_words - total_max

    logger.info(
        "humanize_content: word count = %d / range %d-%d (section_min=%d, sections=%d)",
        total_words, total_min, total_max, section_min, num_sections,
    )

    if deficit > 0:
        short_headings = [
            re.match(r'^## (.+)', s).group(1)
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

    brand_preservation_instruction = ""
    if brand_context:
        brand_name = brand_context["brand_name"]
        link_clause = (
            f" It is hyperlinked to {brand_context['brand_url']} — keep that link intact and attached to the brand name."
            if brand_context.get("brand_url")
            else " It is plain text with no link — do not add one."
        )
        brand_preservation_instruction = (
            f"BRAND MENTION — DO NOT DELETE OR RELOCATE: this article contains exactly one approved, "
            f'required product mention of "{brand_name}", woven into a body-section paragraph as a short '
            f"explanatory aside.{link_clause} Keep it in the same section, attached to the same surrounding "
            f"sentence — do NOT delete it as a 'generic line', do NOT move it into the introduction, and do "
            f"NOT turn it into a standalone closing sentence or CTA at the end of the article. If you rewrite "
            f'the sentence around it, keep "{brand_name}"{" and its link" if brand_context.get("brand_url") else ""} '
            f"and its explanatory clause intact."
        )

    return {
        "title": content_payload.get("title") or "",
        "introduction": introduction,
        "body_markdown": body_markdown,
        "length_instruction": length_instruction,
        "brand_preservation_instruction": brand_preservation_instruction,
    }


async def repair_missing_brand_mention(
    *, payload: dict[str, Any], brand_context: dict[str, str], schema: type[BaseModel],
) -> dict[str, Any] | None:
    """Surgically reinsert a missing brand mention via a narrow, single-purpose edit call.

    Deliberately uses a different (non-rewriting) prompt than humanization —
    re-running the same broad rewrite risks dropping the mention again.
    """
    about = brand_context.get("about") or ""
    selling_position = brand_context.get("selling_position") or ""
    brand_url = brand_context.get("brand_url") or ""

    prompt_data = {
        "brand_name": brand_context["brand_name"],
        "about_line": f"About: {about}\n" if about else "",
        "selling_position_line": f"Selling position: {selling_position}\n" if selling_position else "",
        "url_line": f"URL (hyperlink the mention with this exact URL): {brand_url}\n" if brand_url else "URL: none — mention as plain text, do not invent a URL.\n",
        "title": payload.get("title") or "",
        "introduction": payload.get("introduction") or "",
        "body_markdown": payload.get("body_markdown") or "",
    }

    try:
        model = load_humanize_model().with_structured_output(schema)
        messages = get_brand_repair_prompt().format_messages(**prompt_data)
        repaired_obj = await model.ainvoke(messages)
    except Exception:
        logger.exception("humanize_content: brand repair model call failed.")
        return None

    repaired_payload = _to_dict(repaired_obj)
    if not repaired_payload:
        return None

    combined_text = f"{repaired_payload.get('introduction', '')}\n\n{repaired_payload.get('body_markdown', '')}"
    if not _mention_present(combined_text, brand_context["brand_name"]):
        logger.warning("humanize_content: repair pass still did not include the brand mention.")
        return None

    merged = dict(payload)
    for key in HUMANIZED_FIELDS:
        value = repaired_payload.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value
    return merged


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
    brand_context = _extract_brand_context(outline)
    prompt_data = _build_prompt_data(
        content_payload=original_payload, word_target=word_target, brand_context=brand_context,
    )
    model = load_humanize_model().with_structured_output(schema)
    messages = get_humanize_prompt().format_messages(**prompt_data)

    logger.info("humanize_content: invoking humanization model.")
    try:
        humanized_obj = await model.ainvoke(messages)
    except Exception:
        logger.exception("humanize_content: humanization model failed; keeping pre-humanize content.")
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

    # Guarantee the user-approved brand mention survived humanization — the
    # rewrite pass above has no awareness of it, so it can silently drop or
    # relocate it. Verify deterministically and do one surgical repair pass
    # if it's missing, rather than trusting the rewrite prompt alone.
    if brand_context:
        combined_text = f"{merged_payload.get('introduction', '')}\n\n{merged_payload.get('body_markdown', '')}"
        if not _mention_present(combined_text, brand_context["brand_name"]):
            logger.warning(
                "humanize_content: brand mention '%s' missing after humanization — attempting repair.",
                brand_context["brand_name"],
            )
            repaired = await repair_missing_brand_mention(
                payload=merged_payload, brand_context=brand_context, schema=schema,
            )
            if repaired:
                merged_payload = repaired
                logger.info("humanize_content: brand mention repaired successfully.")
            else:
                logger.warning(
                    "humanize_content: brand mention repair failed — final content will be missing "
                    "the approved '%s' mention.", brand_context["brand_name"],
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
        logger.exception("humanize_content: post-humanize re-validation failed; using merged payload as-is.")

    logger.info("humanize_content: content humanization applied successfully.")
    return {
        "content": {
            **content_state,
            "final_content": merged_payload,
        }
    }
