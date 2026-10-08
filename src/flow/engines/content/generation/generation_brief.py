"""One brief for one article: what the article is, said once and the same at every stage.

The writer's system prompt, the writer's human message and the rewrite each rebuilt their own
sentences about the same facts (the reader, the tone, the length, the keywords, the brand
choice) from the outline and the run's state. They were brought into agreement one fix at a
time; nothing kept them there (FB2.21, rext-control#702, P1).

The checks already read one object, the requirements spec. The brief is read from that spec
wherever the spec holds the fact, so what a stage is told cannot differ from what the article
is checked against, and from the approved outline for the two facts the spec does not hold
(the reader and the tone).

This module is the brief as data and its one wording. The rewrite and the repair read it
(humanize_content, repair_content); the writer comes next, after a comparison on real articles.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict

from src.flow.engines.content.generation.requirements_spec import (
    RequirementsSpec,
    brand_kept_out_of_cta,
    brand_named_in,
)
from src.flow.engines.content.generation.word_count_utils import compute_word_target_band

logger = logging.getLogger(__name__)

Stage = Literal["writer", "rewrite", "repair"]

# What the article does under each brand choice, in the words the outline screen shows beside
# the option (rext-admin, outline-brief.tsx) and the checks hold the article to.
BRAND_CHOICE_LINES: dict[str, str] = {
    "prominent": "named in the opening and in the closing call to action, with what it offers",
    "subtle": (
        "one natural mention early in the body; never in the title, a heading or the call to action"
    ),
    "none": (
        "not named and not linked anywhere: the title, the body, the call to action or the meta "
        "tags"
    ),
}

# What each stage is doing with the brief, the only line that differs between stages.
_STAGE_LINES: dict[str, str] = {
    "writer": "Write the article this brief describes.",
    "rewrite": "The article below was written to this brief. Rewrite its words; the brief stands.",
    "repair": "The article below was written to this brief. Fix the listed issues; the brief stands.",
}


class GenerationBrief(TypedDict):
    title: str
    content_type: str
    readers: list[str]
    tone: str
    target_words: int
    min_words: int
    max_words: int
    focus_keyphrase: str
    secondary_keywords: list[str]
    # "prominent", "subtle" or "none" when the user chose at the outline; "mention" for an
    # approved mention with no level (an older run); "" when no brand is known.
    brand_choice: str
    brand_name: str
    call_to_action: str
    call_to_action_links: bool
    # The brand the approved call to action names though the choice keeps it out of one ("" when
    # it names none): the article then carries its intent in new words, never its text.
    call_to_action_without: str


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _readers(outline: dict) -> list[str]:
    audience = outline.get("target_audience") or outline.get("audience") or []
    if isinstance(audience, str):
        audience = audience.split(",")
    if not isinstance(audience, list):
        return []
    # Every reader the outline holds: a bound, if one is wanted, belongs at the outline gate,
    # where the user would see it.
    return [_text(reader) for reader in audience if _text(reader)]


def _brand(spec: RequirementsSpec, outline: dict) -> tuple[str, str]:
    """(the choice, the brand's name). The name is empty when no brand is known."""
    promotion = outline.get("brand_voice_promotion") or {}
    name = _text((spec.get("brand_context") or {}).get("brand_name") or promotion.get("brand_name"))
    if not name:
        return "", ""
    level = outline.get("brand_prominence")
    if level in BRAND_CHOICE_LINES:
        # "None" with a title or keyphrase that is the brand's own name is not an exclusion:
        # the spec says so, and the brief says nothing about the brand then.
        if level == "none" and not spec.get("excluded_brand"):
            return "", name
        return level, name
    return ("mention", name) if spec.get("brand_context") else ("", name)


def build_generation_brief(spec: RequirementsSpec, outline: dict | None) -> GenerationBrief:
    """The article's brief, from the spec the article is checked against and its outline."""
    outline = outline or {}
    target = int(spec.get("target_word_count") or 0)
    low, high = compute_word_target_band(target)
    choice, brand_name = _brand(spec, outline)
    call_to_action = _text((spec.get("outline_cta") or {}).get("text"))
    # "None" and "Subtle" keep the brand out of the call to action, which then has no link. The
    # spec decides (it is what the cleanup and the checks read), a keyphrase that is the
    # brand's own included: the brief then has no brand line, and still a brand-free call to action.
    brand_free = bool(call_to_action) and bool(spec.get("cta_without_link"))
    kept_out = brand_kept_out_of_cta(outline) if brand_free else ""
    return GenerationBrief(
        title=_text(spec.get("selected_title")),
        content_type=_text(spec.get("content_type")),
        readers=_readers(outline),
        tone=_text(outline.get("tone")),
        target_words=target,
        min_words=low,
        max_words=high,
        focus_keyphrase=_text(spec.get("target_keyword")),
        # Every one the spec holds, since every one is checked: a stage is never held to a
        # keyword it was not told.
        secondary_keywords=[
            _text(keyword) for keyword in spec.get("secondary_keywords") or [] if _text(keyword)
        ],
        brand_choice=choice,
        brand_name=brand_name if choice else "",
        call_to_action=call_to_action,
        call_to_action_links=bool(call_to_action) and not brand_free,
        call_to_action_without=kept_out if brand_named_in(call_to_action, kept_out) else "",
    )


def render_generation_brief(brief: GenerationBrief, *, stage: Stage) -> str:
    """The brief in words. The same lines at every stage, but for two: the stage's own line, and
    the length, which a repair is not given. A repair keeps the article at the length it has
    (the rewrite that follows owns the length), and the target beside that would be a second
    length to obey."""
    lines = [
        "========================",
        "THE ARTICLE'S BRIEF",
        "========================",
        _STAGE_LINES[stage],
        f'- Title (fixed, the user chose it): "{brief["title"]}"' if brief["title"] else "",
        f"- Content type: {brief['content_type']}" if brief["content_type"] else "",
        f"- Written for: {', '.join(brief['readers'])}" if brief["readers"] else "",
        f"- Tone: {brief['tone']}" if brief["tone"] else "",
        (
            f"- Length: about {brief['target_words']} words; the introduction and the body "
            f"together between {brief['min_words']} and {brief['max_words']}"
        )
        if brief["target_words"] and stage != "repair"
        else "",
        f'- Focus keyphrase (exact wording): "{brief["focus_keyphrase"]}"'
        if brief["focus_keyphrase"]
        else "",
        f"- Secondary keywords (each at least once): {', '.join(brief['secondary_keywords'])}"
        if brief["secondary_keywords"]
        else "",
        _brand_line(brief),
        _call_to_action_line(brief),
    ]
    return "\n".join(line for line in lines if line)


def _brand_line(brief: GenerationBrief) -> str:
    choice, name = brief["brand_choice"], brief["brand_name"]
    if not choice:
        return ""
    if choice == "mention":
        return f"- Brand: {name}, mentioned where this kind of article places it"
    line = f"- Brand: {name}, {choice}: {BRAND_CHOICE_LINES[choice]}"
    if choice == "none":
        # As the writer is told: the links the user approved are theirs, wherever they point.
        line += ". The internal links the user approved stay, with their exact addresses"
    return line


def _call_to_action_line(brief: GenerationBrief) -> str:
    text = brief["call_to_action"]
    if not text:
        return ""
    if brief["call_to_action_without"]:
        # Quoting it as the text to use would ask for the name and for its absence at once.
        return (
            f'- Call to action: the same intent as the outline\'s ("{text}"), in new words '
            f"without {brief['call_to_action_without']}, and with no link"
        )
    return f'- Call to action: "{text}"' + (
        "" if brief["call_to_action_links"] else " (with no link)"
    )


def brief_for_stage(spec: RequirementsSpec, outline: dict | None, *, stage: Stage) -> str:
    """The article's brief as ``stage`` reads it, from the spec it is checked against. Empty when
    it can't be built: a stage then says what it said before the brief, never nothing wrong."""
    try:
        return render_generation_brief(build_generation_brief(spec, outline), stage=stage)
    except Exception:  # noqa: BLE001 - a prompt helper must not take a run down
        logger.warning("The article's brief could not be built for %s", stage, exc_info=True)
        return ""
