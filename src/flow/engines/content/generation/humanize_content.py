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

from src.flow.engines.content.generation.article_voice import format_voice_for_rewrite
from src.flow.engines.content.generation.brand_placement_policy import (
    BrandPlacementPolicy,
    build_brand_structural_injection,
    resolve_brand_placement_policy,
)
from src.flow.engines.content.generation.focus_keyword import resolve_focus_keyword
from src.flow.engines.content.generation.generation_brief import brief_for_stage
from src.flow.engines.content.generation.keyword_density import analyze_keyword_density
from src.flow.engines.content.generation.link_integrity import (
    normalize_url,
    present_urls,
    reconcile_link_lists,
    restore_lost_links,
)
from src.flow.engines.content.generation.onpage_seo import enforce_onpage_seo
from src.flow.engines.content.generation.repair_content import run_targeted_repair
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.section_rewrite import (
    INTRODUCTION,
    OPENING,
    SECTION,
    Part,
    brand_lines,
    join_article,
    keyphrase_plan,
    keyword_lines,
    rewrite_parts,
    secondary_plan,
    split_article,
    wanted_scale,
)
from src.flow.engines.content.generation.section_rewrite import words as count_words
from src.flow.engines.content.generation.validation import (
    apply_brand_exclusion,
    check_brand_placement_policy,
    check_brand_prominence,
    check_brand_url_accuracy,
    check_links_preserved,
    merge_link_inventory,
    protected_links,
)
from src.flow.engines.content.generation.word_count_utils import compute_word_target_band
from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.runaway import ainvoke_watched
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.prompts.human.humanize import get_humanize_prompt, get_section_rewrite_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

DEFAULT_WORD_TARGET = 3000
SECTION_MIN_FRACTION = (
    0.5  # a section is "too short" if under 50% of its proportional share of the target
)

# With fewer H2 sections than this, a body is rewritten whole: there is nothing to split.
MIN_SECTIONS_TO_SPLIT = 2

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
    # A high-intensity placement (a sales page, or a prominent mention the user
    # chose) asks for several mentions; "one approved mention" would undo it.
    approved = (
        "approved mentions"
        if policy["intensity"] in ("high", "maximal")
        else "one approved mention"
    )

    return (
        f'BRAND INTEGRATION — REQUIRED: this article carries {approved} of "{brand_name}". '
        "While rewriting for human tone, also make sure it is placed and weighted correctly for this "
        "content type — reposition or rewrite it if the current draft has it in the wrong place or as a "
        "weak, bolted-on name-drop; do not just leave it untouched if it doesn't comply.\n"
        f"- PLACEMENT: {placement_line}\n"
        f"- FORMAT GUARDRAIL: {policy['guardrail']}\n"
        "- Write it as strong, natural, specific copy — a real benefit or use-case woven into a full "
        f"sentence, never a bare name-drop.{link_clause}\n"
        f"{structural_injection}"
    )


def _build_keyword_instruction(
    *,
    content_payload: dict[str, Any],
    focus_keyword: str,
    content_type: str,
    secondary_keywords: list[str] | None = None,
) -> str:
    """Tell the rewrite exactly how much exact-phrase usage has to survive.

    Humanization is the single most likely place for the focus keyphrase to be
    lost: the pass is explicitly licensed to "rephrase every sentence", and the
    most natural way to make repeated phrasing read better is to swap the
    repeated phrase for synonyms — which is precisely the usage being measured.
    A generic "keep the keyword" note is too weak against that instruction, so
    this states the literal phrase and the count measured in the draft the model
    is being handed.
    """
    focus_keyword = (focus_keyword or "").strip()
    if not focus_keyword:
        return ""
    report = analyze_keyword_density(
        text=(
            f"{content_payload.get('introduction') or ''}"
            f"\n\n{content_payload.get('body_markdown') or ''}"
        ),
        keyphrase=focus_keyword,
        content_type=content_type,
    )
    policy = report["policy"]
    return (
        "FOCUS KEYPHRASE — MUST SURVIVE THIS REWRITE:\n"
        f'- The focus keyphrase is exactly: "{focus_keyword}".\n'
        f"- It currently appears {report['occurrences']} time(s) as an exact phrase. "
        f"Keep it between {policy['min_occurrences']} and {policy['max_occurrences']} "
        "exact-phrase uses after your rewrite.\n"
        "- Do NOT replace it with a synonym, reorder its words, or paraphrase it away "
        "while varying your phrasing — vary the sentences AROUND it instead.\n"
        "- If you expand or trim the article, scale its usage with the new length so it "
        "stays inside that range." + _secondary_keyword_lines(secondary_keywords)
    )


def _secondary_keyword_lines(secondary_keywords: list[str] | None) -> str:
    """The other keywords the user approved: each kept at least once (FB2.18, rext-control#699)."""
    keywords = [k for k in (secondary_keywords or []) if isinstance(k, str) and k.strip()]
    if not keywords:
        return ""
    return (
        "\n- The user also approved these secondary keywords; keep each at least once, as "
        f"written where it reads naturally: {', '.join(keywords)}."
    )


def _build_reader_instruction(*, audience: Any, tone: Any) -> str:
    """Who the article is for and its tone, as the user set them at the outline (FB2.18):
    the rewrite was told neither, only the persona's voice and the brand voice."""
    if isinstance(audience, list):
        audience = ", ".join(str(a).strip() for a in audience if str(a).strip())
    audience = " ".join(str(audience or "").split())
    tone = " ".join(str(tone or "").split())
    lines = [
        f"- Written for: {audience}" if audience else "",
        f"- Tone: {tone}" if tone else "",
    ]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    return (
        "READER AND TONE — the user set these at the outline; keep the rewrite true to them:\n"
        + "\n".join(lines)
    )


def _build_prompt_data(
    *,
    content_payload: dict[str, Any],
    word_target: int = DEFAULT_WORD_TARGET,
    brand_context: dict[str, str] | None = None,
    content_type: str = "",
    focus_keyword: str = "",
    brand_policy: BrandPlacementPolicy | None = None,
    article_voice: dict[str, Any] | None = None,
    secondary_keywords: list[str] | None = None,
    audience: Any = None,
    tone: Any = None,
    excluded_brand: dict[str, str] | None = None,
    brief: str = "",
) -> dict[str, Any]:
    """What the rewrite is told beside the article.

    ``brief`` is the article's brief (generation_brief, stage "rewrite"): the reader, the tone,
    the length band, the keywords, the brand choice and the call to action, each said once and
    as the checks read them. With it, the instructions below say only what this pass has
    measured and what to do about it; without it (the brief could not be built) they state the
    reader, the tone and the secondary keywords themselves, as they did before the brief.
    """
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
    # Measured against the band the article is checked against, the one the brief states. An
    # article inside it is left at its length: asking for more whenever it was under the
    # target itself (not the band) pushed articles that passed over the maximum.
    deficit = total_target - total_words if total_words < total_min else 0
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
            f"LENGTH REQUIREMENT: Article has {total_words} words, under its range of {total_min}-{total_max}. "
            f"While rewriting, also EXPAND the content by about {deficit} words. {expand_note} "
            "Do not pad with filler — expand with substance."
        )
    elif excess > 0:
        # Aim for the middle of target..max, not the ceiling: trimming "roughly
        # the excess" routinely stopped a few words above the maximum.
        trim = total_words - round((total_target + total_max) / 2)
        length_instruction = (
            f"LENGTH REQUIREMENT: Article has {total_words} words, over its range of {total_min}-{total_max}. "
            f"While rewriting, also TRIM the content by roughly {trim} words — cut filler, redundant transitions, "
            "and repeated points. Keep every fact, citation, and link intact; tighten prose, don't remove substance. "
            f"A rewrite that comes back longer than {total_max} words has failed this requirement."
        )
    else:
        # A tone rewrite tends to compress. Stating the floor keeps an in-band
        # article in band instead of leaving it to be corrected afterwards.
        length_instruction = (
            f"Article has {total_words} words — within the {total_min}-{total_max} acceptable range. "
            f"Rewrite for human tone, and keep the result between {total_min} and {total_max} words: "
            "do not condense or drop content while rewriting."
        )

    brand_instruction = ""
    if brand_context:
        # The requirements spec's policy: the content type's, at the prominence
        # the user chose, the same one validation grades against.
        policy = brand_policy or resolve_brand_placement_policy(content_type)
        brand_instruction = _build_brand_instruction(
            brand_name=brand_context["brand_name"],
            brand_url=brand_context.get("brand_url", ""),
            content_type=content_type,
            policy=policy,
        )
    elif excluded_brand:
        # The user chose no mention (rext-control#700): a rewrite must not bring the brand in.
        brand_instruction = (
            # The brief states the rule and where it holds; this is what the pass does about it.
            f'BRAND EXCLUSION — the brief\'s brand line stands: if the draft names "{excluded_brand["brand_name"]}" '
            "or links to its site, rewrite that sentence without it, and bring it in nowhere."
            if brief
            else f'BRAND EXCLUSION — the user chose NO mention of "{excluded_brand["brand_name"]}": do not '
            "name it, or link to its site (the article's internal links stay), anywhere in the title, "
            "the introduction, the body, a heading or a call to action. If the draft names it, "
            "rewrite that sentence without it."
        )

    return {
        "title": content_payload.get("title") or "",
        "introduction": introduction,
        "body_markdown": body_markdown,
        "length_instruction": length_instruction,
        "voice_instruction": format_voice_for_rewrite(article_voice),
        "brand_instruction": brand_instruction,
        "reader_instruction": brief or _build_reader_instruction(audience=audience, tone=tone),
        "keyword_instruction": _build_keyword_instruction(
            content_payload=content_payload,
            focus_keyword=focus_keyword,
            content_type=content_type,
            # The brief lists them, once, as the check reads them.
            secondary_keywords=None if brief else secondary_keywords,
        ),
    }


def _merge_humanized(base: dict[str, Any], humanized: dict[str, Any]) -> dict[str, Any]:
    """``base`` with only the humanized prose fields taken from the model output."""
    merged = dict(base)
    for key in HUMANIZED_FIELDS:
        value = humanized.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        merged[key] = value
    return merged


def _lost_links(payload: dict[str, Any], protected: list[dict]) -> int:
    present = present_urls(payload)
    return sum(1 for r in protected if normalize_url(r.get("url", "")) not in present)


def _restore_links(payload: dict[str, Any], protected: list[dict], *, stage: str) -> dict[str, Any]:
    if not protected:
        return payload
    restored_payload, restored, missing = restore_lost_links(payload, protected)
    if restored or missing:
        logger.info(
            "humanize_content[%s]: links dropped by the rewrite — restored in place=%s, "
            "not restorable=%s",
            stage,
            [r.get("url") for r in restored],
            [r.get("url") for r in missing],
        )
    return restored_payload


def _repair_fixed(
    repaired: dict[str, Any],
    before: dict[str, Any],
    brand_failed: dict[str, Any] | None,
    brand_context: dict[str, str] | None,
    spec: dict,
    protected: list[dict],
) -> bool:
    """Accept the post-humanize repair only if it fixed something and broke nothing it guards."""
    lost_before, lost_after = _lost_links(before, protected), _lost_links(repaired, protected)
    if lost_after > lost_before:
        return False
    # Asked to move the brand's first mention earlier, the repair may add one there instead: a
    # Subtle article's one mention is then two, and the new first one has no link. The place
    # is fixed and the level the user chose is broken, with no repair after this one.
    for held in (check_brand_prominence, check_brand_url_accuracy):
        if held(before, spec)["passed"] and not held(repaired, spec)["passed"]:
            return False
    brand_fixed = False
    if brand_failed and brand_context:
        brand_name = brand_context["brand_name"]
        present = _mention_present(
            f"{repaired.get('introduction', '')}\n\n{repaired.get('body_markdown', '')}",
            brand_name,
        )
        brand_fixed = (
            present and check_brand_placement_policy(repaired, spec)["passed"]
            if brand_failed["name"] == "brand_placement_policy"
            else present
        )
        was_present = _mention_present(
            f"{before.get('introduction', '')}\n\n{before.get('body_markdown', '')}", brand_name
        )
        if was_present and not present:
            return False
    return brand_fixed or lost_after < lost_before


_PART_NAMES = {
    INTRODUCTION: (
        "the introduction (the paragraphs before the first heading). It has no heading: "
        "return paragraphs only."
    ),
    OPENING: (
        "what the body opens with, before its first heading. It has no heading of its own: "
        "add none."
    ),
}


def _section_name(part: Part, parts: list[Part], index: int) -> str:
    """What a section's part is called in its message: the section, or one sub-section of a
    long section, with the section it stands under."""
    if part.level == 2:
        return f'the section "{part.title}", with everything under it.'
    above = next((p.title for p in reversed(parts[:index]) if p.level == 2), "")
    return f'the sub-section "{part.title}"' + (f' of the section "{above}".' if above else ".")


async def _rewrite_by_section(
    original_payload: dict[str, Any],
    parts: list[Part],
    *,
    spec: dict,
    outline: dict,
    content_type: str,
    word_target: int,
    article_voice: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """``original_payload`` with its introduction and body rewritten part by part, or None when
    no part's rewrite could be used (the caller keeps the article as drafted, as it does when
    the whole-article rewrite fails)."""
    prompt = get_section_rewrite_prompt()
    brief = brief_for_stage(spec, outline, stage="section")
    voice = format_voice_for_rewrite(article_voice)
    title = original_payload.get("title") or ""
    # The article's H2s: a long section's H3s, rewritten one by one, are not listed apart.
    sections = "\n".join(
        f"{number}. {part.title}"
        for number, part in enumerate((p for p in parts if p.kind == SECTION and p.level == 2), 1)
    )
    focus_keyphrase = spec.get("target_keyword") or ""
    uses = keyphrase_plan(
        parts,
        focus_keyphrase,
        content_type,
        wanted_scale(sum(count_words(part.text) for part in parts), word_target),
    )
    new_phrases = secondary_plan(parts, spec.get("secondary_keywords"))

    def messages_for(part: Part, index: int, low: int, high: int) -> list:
        return prompt.format_messages(
            voice_instruction=voice,
            brief=brief,
            title=title,
            sections=sections,
            which=_PART_NAMES.get(part.kind) or _section_name(part, parts, index),
            brand_instruction=brand_lines(
                part.text,
                brand_context=spec.get("brand_context"),
                excluded_brand=spec.get("excluded_brand"),
            ),
            keyword_instruction=keyword_lines(
                part.text,
                focus_keyphrase,
                spec.get("secondary_keywords"),
                wanted_uses=uses.get(index),
                new_phrases=new_phrases.get(index),
            ),
            words=count_words(part.text),
            low=low,
            high=high,
            text=part.text,
        )

    logger.info("humanize_content: rewriting %d parts, each on its own.", len(parts))
    try:
        rewritten, counts = await rewrite_parts(
            parts,
            model=load_humanize_model(),
            messages_for=messages_for,
            word_target=word_target,
            brand=spec.get("brand_context"),
            excluded=spec.get("excluded_brand"),
        )
    except Exception:
        logger.exception("humanize_content: the rewrite failed; keeping pre-humanize content.")
        return None
    logger.info(
        "humanize_content: %d of %d parts rewritten, %d kept as drafted; %d words became %d",
        counts["rewritten"],
        counts["parts"],
        counts["kept"],
        counts["words_before"],
        counts["words_after"],
    )
    if not counts["rewritten"]:
        logger.warning("humanize_content: no part's rewrite could be used; keeping the draft.")
        return None
    introduction, body = join_article(rewritten)
    return {**original_payload, "introduction": introduction, "body_markdown": body}


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
    selected_title = (content_state.get("selected_topic") or "").strip()
    focus_keyword = resolve_focus_keyword(state)
    generation_meta = content_state.get("generation_meta") or {}
    searched_results = generation_meta.get("searched_results") or []
    spec = build_requirements_spec(
        outline, content_type, focus_keyword, selected_title, generation_meta=generation_meta
    )
    brand_context = spec.get("brand_context")
    prompt_data = _build_prompt_data(
        content_payload=original_payload,
        word_target=word_target,
        brand_context=brand_context,
        content_type=content_type,
        focus_keyword=spec.get("target_keyword") or "",
        brand_policy=spec.get("brand_placement_policy"),
        article_voice=generation_meta.get("article_voice"),
        secondary_keywords=spec.get("secondary_keywords"),
        audience=outline.get("target_audience"),
        tone=outline.get("tone"),
        excluded_brand=spec.get("excluded_brand"),
        brief=brief_for_stage(spec, outline, stage="rewrite"),
    )
    # An article of several sections is rewritten one section at a time, each told its own
    # length (section_rewrite.py): told the whole article's, the model wrote to a length of
    # its own. A body with fewer than two H2s has nothing to split and is rewritten whole.
    parts = split_article(original_payload.get("introduction") or "", body_markdown)
    if sum(1 for part in parts if part.kind == SECTION and part.level == 2) >= (
        MIN_SECTIONS_TO_SPLIT
    ):
        merged_payload = await _rewrite_by_section(
            original_payload,
            parts,
            spec=spec,
            outline=outline,
            content_type=content_type,
            word_target=word_target,
            article_voice=generation_meta.get("article_voice"),
        )
        if merged_payload is None:
            return {}
    else:
        model = load_humanize_model().with_structured_output(schema)
        messages = get_humanize_prompt().format_messages(**prompt_data)

        logger.info("humanize_content: invoking humanization model.")
        try:
            humanized_obj = await ainvoke_watched(model, messages, stage="humanize")
        except Exception:
            logger.exception(
                "humanize_content: humanization model failed; keeping pre-humanize content."
            )
            return {}

        humanized_payload = _to_dict(humanized_obj)
        if not humanized_payload:
            logger.warning(
                "humanize_content: empty humanized payload; keeping pre-humanize content."
            )
            return {}

        merged_payload = _merge_humanized(original_payload, humanized_payload)

    # Humanization is told to keep every link, but not trusted blindly: a
    # protected link it dropped is put back on its anchor (or the sentence that
    # replaced its sentence) deterministically, before anything else reads the
    # payload. Only a link with nowhere to go is left to the repair below.
    protected = [
        r
        for r in merge_link_inventory(
            spec.get("link_inventory"),
            protected_links(original_payload, spec, searched_results),
        )
        if normalize_url(r.get("url", "")) in present_urls(original_payload)
    ]
    merged_payload = _restore_links(merged_payload, protected, stage="humanize")

    # Guarantee the user-approved brand mention both survived humanization AND
    # still complies with this content type's placement policy — the rewrite
    # pass above (via _build_brand_instruction) is told where it belongs, but
    # isn't trusted blindly. Verify deterministically: first presence (it may
    # have been dropped entirely), then position (it may have merely drifted
    # into the wrong place — e.g. into the introduction for a body-only type,
    # or buried past the hero window for a prefers_top type). A protected link
    # that could not be restored deterministically is repaired in the SAME call:
    # two sequential repairs on humanized prose risk the second undoing the first.
    failed_checks: list[dict[str, Any]] = []
    brand_failed: dict[str, Any] | None = None
    if brand_context:
        brand_name = brand_context["brand_name"]
        combined_text = (
            f"{merged_payload.get('introduction', '')}\n\n{merged_payload.get('body_markdown', '')}"
        )
        if not _mention_present(combined_text, brand_name):
            brand_failed = {
                "name": "brand_presence",
                "passed": False,
                "severity": "blocking",
                "detail": f"Approved brand mention '{brand_name}' is missing after humanization.",
            }
        else:
            placement_result = check_brand_placement_policy(merged_payload, spec)
            if not placement_result["passed"]:
                brand_failed = placement_result
        if brand_failed:
            failed_checks.append(brand_failed)

    link_check = check_links_preserved(merged_payload, {**spec, "link_inventory": protected})
    if not link_check["passed"]:
        failed_checks.append(link_check)

    if failed_checks:
        logger.warning(
            "humanize_content: %s failed after humanization — attempting one targeted repair.",
            [(c["name"], c["detail"]) for c in failed_checks],
        )
        # Same repair implementation repair_content uses pre-humanize —
        # one repair prompt/pathway instead of two independently-worded
        # ones that could drift out of sync with each other.
        repaired = await run_targeted_repair(
            final_content=merged_payload,
            content_type=content_type,
            failed_checks=failed_checks,
            brand_context=brand_context,
            searched_results=searched_results,
            article_stage="post-humanization (tone finalized — preserve it)",
            protected=protected,
            brand_policy=spec.get("brand_placement_policy"),
            excluded_brand=spec.get("excluded_brand"),
            brief=brief_for_stage(spec, outline, stage="repair"),
        )
        if repaired is not None:
            # The repair returns every field: the brand choice's cleanup applies to it too.
            repaired = apply_brand_exclusion(repaired, spec, stage="humanize_content repair")
        if repaired is not None and _repair_fixed(
            repaired, merged_payload, brand_failed, brand_context, spec, protected
        ):
            merged_payload = repaired
            logger.info(
                "humanize_content: repaired %s successfully.", [c["name"] for c in failed_checks]
            )
        elif repaired is not None:
            logger.warning(
                "humanize_content: repair did not resolve %s without regressions — keeping "
                "content as-is.",
                [c["name"] for c in failed_checks],
            )
        else:
            logger.warning(
                "humanize_content: repair call failed — keeping content with unresolved %s.",
                [c["name"] for c in failed_checks],
            )

    # Match the link lists to the prose before re-validation, so the model's
    # internal-link fallback cannot append a dropped link as a bare line.
    merged_payload = reconcile_link_lists(original_payload, merged_payload)

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

    # Humanization is a free-form rewrite and it returns the full schema, so
    # the title, meta description and the keyphrase inside the introduction can
    # all regress here even though they were compliant going in. Re-assert them
    # deterministically rather than hoping the prompt held.
    merged_payload = enforce_onpage_seo(
        merged_payload,
        selected_title=selected_title,
        focus_keyphrase=focus_keyword,
        stage="humanize_content",
    )

    logger.info("humanize_content: content humanization applied successfully.")
    return {
        "content": {
            **content_state,
            "final_content": merged_payload,
            "generation_meta": {
                **generation_meta,
                # Everything protected going in stays the baseline that
                # final_validate_content checks against — including a link lost
                # before humanization that the repair loop could not place, so it
                # is still reported rather than silently forgotten here.
                "link_inventory": merge_link_inventory(
                    spec.get("link_inventory"),
                    protected,
                    protected_links(merged_payload, spec, searched_results),
                ),
            },
        }
    }
