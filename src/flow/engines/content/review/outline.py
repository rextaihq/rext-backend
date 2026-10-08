import logging

from langgraph.types import interrupt

from src.flow.engines.content.generation.brand_placement_policy import (
    BRAND_PROMINENCE_LEVELS,
    recommended_brand_prominence,
)
from src.flow.engines.content.generation.brand_slot import apply_brand_slot_to_outline
from src.flow.engines.content.generation.focus_keyword import (
    focus_keyword_from_outline,
    pin_focus_keyword,
    resolve_focus_keyword,
)
from src.flow.engines.content.review.outline_edits import (
    addable_lists,
    apply_section_edits,
    editable_sections,
)
from src.flow.engines.content.review.outline_parts import safe_gate_structure
from src.flow.engines.serp.serp_evidence import build_serp_titles
from src.flow.model.structure.outlines import WRITER_MAX_TARGET_WORDS, target_word_count_range
from src.flow.model.structure.outlines.render import normalize_outline
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

# The Sources view lists at most this many questions and related searches.
SOURCE_LIST_LIMIT = 10


def _distinct(values, limit: int = SOURCE_LIST_LIMIT) -> list[str]:
    """Non-empty strings, each once (ignoring case), in their order, at most `limit`."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values if isinstance(values, (list, tuple)) else []:
        if isinstance(value, str) and value.strip() and value.strip().lower() not in seen:
            seen.add(value.strip().lower())
            out.append(value.strip())
    return out[:limit]


def _search_sources(state: REXT) -> dict[str, list]:
    """What the outline was planned against, for the screen's Sources view: the
    top results, the questions people also ask, the related searches.

    Every run passes this gate, and the evidence is optional: a missing or
    malformed SERP (a failed lookup, an older run's state) gives empty lists and
    never stops the gate.
    """
    normalized = state.get("serp_normalized")
    normalized = normalized if isinstance(normalized, dict) else {}
    raw = state.get("serp_result")
    raw = raw if isinstance(raw, dict) else {}
    try:
        return {
            "serp_titles": build_serp_titles(normalized),
            "serp_questions": _distinct(normalized.get("questions")),
            # Google's own: the normalized related_topics are backfilled with the
            # model's suggested keywords when the search shows none (competitor.py).
            "related_searches": _distinct(raw.get("related_searches")),
        }
    except Exception:
        logger.warning("Outline gate: the search evidence could not be read", exc_info=True)
        return {"serp_titles": [], "serp_questions": [], "related_searches": []}


# The keywords a user may send back at approval: plain phrases, deduplicated, a sensible number.
_MAX_KEYWORDS = 20
_MAX_KEYWORD_CHARS = 80


def _clean_keywords(value, *focus_keywords: str) -> list[str] | None:
    """The approved secondary keywords, or None when the payload has none (keep the outline's).

    The focus keyphrase is left out here (`focus_keywords`: the run's own, and the one an older
    outline's model chose, which the screen showed as the primary): the run's own is pinned back
    in front afterwards, whole, whatever its length. A phrase over the limit is dropped, not
    cut: half a phrase is not a keyword."""
    if not isinstance(value, list):
        return None
    cleaned: list[str] = []
    seen: set[str] = {phrase.casefold() for phrase in focus_keywords if phrase}
    for item in value:
        if not isinstance(item, str):
            continue
        phrase = " ".join(item.split())
        if not phrase or len(phrase) > _MAX_KEYWORD_CHARS or phrase.casefold() in seen:
            continue
        seen.add(phrase.casefold())
        cleaned.append(phrase)
    return cleaned[:_MAX_KEYWORDS]


def _run_focus_keyword(state: REXT) -> str:
    """The run's own focus keyphrase (the user's query), or "" when the state can't be read:
    like the search evidence, an odd state never stops the gate."""
    try:
        return resolve_focus_keyword(state)
    except Exception:
        logger.warning("Outline gate: the run's focus keyword could not be read", exc_info=True)
        return ""


def _removed_keywords(outline: dict, kept: list[str], *focus_keywords: str) -> list[str]:
    """The outline's keywords the user took out. The writer's cluster notes still list them,
    so generation needs their names to leave them out (content_generation.py).

    A phrase that is part of one that stays ("content calendar" inside the focus keyphrase
    "content calendar template") is not listed: the writer can't avoid it and use the other.
    Part of it as whole words: "AI" is not part of "email marketing"."""
    staying = [phrase.casefold().split() for phrase in (*focus_keywords, *kept) if phrase]
    return [
        phrase
        for phrase in _distinct(outline.get("keywords_to_include"), _MAX_KEYWORDS * 2)
        if not any(_words_inside(phrase.casefold().split(), other) for other in staying)
    ]


def _words_inside(words: list[str], other: list[str]) -> bool:
    """Whether `words` runs somewhere inside `other`, word for word."""
    span = len(words)
    return any(other[i : i + span] == words for i in range(len(other) - span + 1))


def review_outline(state: REXT):
    """Interrupt workflow for human approval of the generated outline.

    Presents the outline to the user via LangGraph's ``interrupt()``
    mechanism. Handles approve/reject/regenerate actions.

    ``reject`` and ``regenerate`` are equivalent — the graph always loops
    back to ``generate_outline`` on anything other than approval (see
    ``src.flow.engines.router.outline.outline_router``), so both actions set
    ``status = "rejected"`` and stash the caller's feedback in
    ``rejected_reason`` for the next generation pass to prioritize.
    ``regenerate`` accepts feedback inline in the same interrupt response
    (one round trip); ``reject`` with no reason triggers a second interrupt
    asking for one, for backward compatibility with the existing UI flow.

    Args:
        state: REXT state containing ``content.outline``.

    Returns:
        dict: State update with ``content.outline.status`` set to
        ``"approved"`` or ``"rejected"`` with reason.
    """
    content_state = state.get("content", {})
    outline_dict = dict(content_state.get("outline", {}) or {})
    content_type = content_state.get("content_type", "")
    promotion_recommended = bool(
        (outline_dict.get("brand_voice_promotion") or {}).get("recommended", False)
    )
    seo_result = state.get("seo_result", {})
    keyword_clusters = seo_result.get("keyword_clusters", [])

    # Ensure cluster mapping is available in the outline dict for the frontend
    cluster_heading_map = content_state.get("cluster_heading_map") or outline_dict.get(
        "cluster_heading_map",
        {},
    )
    logger.info(f"Cluster heading map for outline review: {cluster_heading_map}")
    if cluster_heading_map:
        outline_dict["cluster_heading_map"] = cluster_heading_map

    # 1. Interrupt for human approval
    logger.info("Interrupting for human review of outline...")
    review_result = interrupt(
        {
            "type": "outline_review",
            "data": outline_dict,
            "clusters": keyword_clusters,
            "internal_links": outline_dict.get("internal_links", []),
            "brand_voice_promotion": outline_dict.get("brand_voice_promotion"),
            # The level the screen preselects (prominent, subtle or none);
            # approval may send `brand_prominence` back.
            "recommended_brand_prominence": recommended_brand_prominence(
                content_type, promotion_recommended
            ),
            "persona_recommendations": outline_dict.get("persona_recommendations", []),
            # The sections the user may reorder, rename or remove; approval can
            # send them back as `sections` (see outline_edits.py).
            "editable_sections": editable_sections(outline_dict, content_type),
            # The lists a new section may be added to (a row with "new": true).
            "section_additions": addable_lists(outline_dict, content_type),
            # Every part the article is written under, in order, for the screen to list
            # whole: the lists above in their place among the parts that are only read
            # (outline_parts.py; the dashboard's side is revnix/rext-control#814).
            "structure": safe_gate_structure(outline_dict, content_type),
            # serp_titles, serp_questions and related_searches, for Sources.
            **_search_sources(state),
            "instruction": (
                "Please approve the outline, or reject/regenerate it with "
                "feedback on what should change — your feedback will be "
                "prioritized in the next version."
            ),
        }
    )

    # 2. Handle review result
    if isinstance(review_result, str):
        action = review_result.lower()
        review_data = {}
    elif isinstance(review_result, dict):
        action = review_result.get("action", "").lower()
        review_data = review_result
    else:
        action = ""
        review_data = {}
    #
    if action == "approve":
        logger.info("Outline approved by human")

        # Extract updated tone, audience, and word count if provided
        updated_tone = review_data.get("tone")
        updated_audience = review_data.get("target_audience")
        updated_word_count = review_data.get("target_word_count")
        if updated_word_count is not None:
            try:
                updated_word_count = int(updated_word_count)
            except (TypeError, ValueError):
                logger.warning(f"Ignoring invalid target_word_count: {updated_word_count}")
                updated_word_count = None
            else:
                shortest, longest = target_word_count_range(content_type)
                if not (shortest <= updated_word_count <= longest):
                    logger.warning(
                        "Ignoring target_word_count %s: %s takes %s to %s",
                        updated_word_count,
                        content_type or "this content type",
                        shortest,
                        longest,
                    )
                    updated_word_count = None
                elif updated_word_count > WRITER_MAX_TARGET_WORDS:
                    # Inside the type's range (a white paper goes to 15,000) but more than the
                    # writer can return in one response: the most it can write, not a cut-off one.
                    logger.warning(
                        "target_word_count %s is more than the writer can return: using %s",
                        updated_word_count,
                        WRITER_MAX_TARGET_WORDS,
                    )
                    updated_word_count = WRITER_MAX_TARGET_WORDS

        # Use user-selected internal links if provided, else keep all
        selected_links = review_data.get("selected_internal_links")
        if selected_links is not None:
            internal_links = selected_links
            logger.info(f"User selected {len(internal_links)} internal link(s)")
        else:
            internal_links = outline_dict.get("internal_links", [])

        # Brand promotion decision — user can override the recommendation. A
        # prominence level (prominent, subtle, none) decides promote_brand and
        # is kept on the outline for every stage that places the brand
        # (brand_placement_policy.resolve_article_brand_policy). Without one,
        # promote_brand alone keeps the content type's own placement.
        brand_prominence = review_data.get("brand_prominence")
        if brand_prominence in BRAND_PROMINENCE_LEVELS:
            promote_brand = brand_prominence != "none"
        else:
            if brand_prominence is not None:
                logger.warning(
                    f"[BrandPromo] ignoring unknown brand_prominence {brand_prominence!r}"
                )
            brand_prominence = None
            promote_brand = bool(review_data.get("promote_brand", promotion_recommended))
        logger.info(f"[BrandPromo] promote_brand={promote_brand} prominence={brand_prominence}")

        # Author persona — the user can keep the recommendation, pick another, or
        # clear it entirely. The key being PRESENT is what makes it a decision:
        # an explicit null means "write with no author persona", and falling back
        # to the recommendation there is exactly what made deselecting impossible.
        if "selected_persona_id" in review_data:
            updated_persona_id = review_data.get("selected_persona_id")
            selected_persona_id = (
                updated_persona_id.strip()
                if isinstance(updated_persona_id, str) and updated_persona_id.strip()
                else None
            )
        else:
            selected_persona_id = outline_dict.get("selected_persona_id")
        logger.info(f"[Persona] selected_persona_id={selected_persona_id}")

        # The user's order, headings and removals, applied to the outline itself
        # so the writer and the validator follow them. The display projection
        # is rebuilt below, once every sidebar edit is in.
        edited_outline = apply_section_edits(
            outline_dict, content_type, review_data.get("sections")
        )
        display_changed = edited_outline is not outline_dict

        outline_update = {
            **edited_outline,
            "internal_links": internal_links,
            "promote_brand": promote_brand,
            "brand_prominence": brand_prominence,
            "selected_persona_id": selected_persona_id,
            "rejected_reason": "",
            "status": "approved",
        }

        if updated_tone:
            outline_update["tone"] = updated_tone
            display_changed = True
        if updated_audience:
            outline_update["target_audience"] = updated_audience
            display_changed = True
        # The keywords the user kept, added or removed in the sidebar (FB2.18,
        # rext-control#699). The focus keyphrase is the run's own (the user's query,
        # not a phrase an older outline's model chose) and still leads the list.
        outline_focus = focus_keyword_from_outline(outline_update)
        focus_keyword = outline_focus
        if isinstance(review_data.get("keywords_to_include"), list):
            focus_keyword = _run_focus_keyword(state) or outline_focus
        updated_keywords = _clean_keywords(
            review_data.get("keywords_to_include"), focus_keyword, outline_focus
        )
        if updated_keywords is not None:
            outline_update["removed_keywords"] = _removed_keywords(
                outline_dict, updated_keywords, focus_keyword, outline_focus
            )
            outline_update["keywords_to_include"] = updated_keywords
            pin_focus_keyword(outline_update, focus_keyword)
            display_changed = True
        if updated_word_count is not None:
            outline_update["target_word_count"] = updated_word_count
            display_changed = True

            # Rescale per-section word budgets to match the new total so the
            # outline stays internally consistent — otherwise sections keep the
            # word budget of the original (unedited) target, and downstream
            # generation is handed a section scope sized for a different total.
            sections = outline_update.get("sections")
            if isinstance(sections, list) and sections:
                old_total = sum(s.get("suggested_word_count") or 0 for s in sections)
                if old_total:
                    ratio = updated_word_count / old_total
                    outline_update["sections"] = [
                        {
                            **s,
                            "suggested_word_count": max(
                                50, round(s["suggested_word_count"] * ratio)
                            ),
                        }
                        if s.get("suggested_word_count")
                        else s
                        for s in sections
                    ]

        # The dashboard reads `_render`: one approved outline, whichever copy is read.
        if display_changed and "_render" in outline_update:
            outline_update["_render"] = normalize_outline(outline_update, content_type)

        logger.info(
            "Tone: %s, Audience: %s, Target Word Count: %s approved by human",
            updated_tone,
            updated_audience,
            updated_word_count,
        )

        # Give the approved promotion a real slot in the plan, now that we know
        # it was approved. The outline was generated BEFORE this decision existed,
        # so without this the writer model reads a structure with nowhere for the
        # brand to go while being told to feature it — and resolves that by
        # dropping the mention wherever it likes, usually mid-body or in the
        # closing paragraph. Applied last so it sees the final, user-edited
        # structure. Soft-fails to an unchanged outline.
        # A subtle mention is one aside, not a featured entry: no slot.
        if promote_brand and brand_prominence != "subtle":
            outline_update = apply_brand_slot_to_outline(outline_update, content_type)

        # The article's writing starts here, for the analytics events' `writing_seconds`.
        from src.services.generation_events import writing_began

        writing_began()
        return {
            "content": {
                **content_state,
                "outline": outline_update,
            }
        }

    if action in ("reject", "regenerate"):
        # "regenerate" carries feedback inline in the same interrupt response
        # (one round trip); "reject" may omit it and get asked separately below.
        raw_feedback = review_data.get("feedback") or review_data.get("reason")
        reject_reason = raw_feedback.strip() if isinstance(raw_feedback, str) else None
        reject_reason = reject_reason or None

        if not reject_reason and action == "reject":
            # If reason wasn't provided in the first interrupt, ask for it
            reject_response = interrupt(
                {
                    "type": "outline_reject",
                    "instruction": (
                        "What would you like changed? This feedback will be "
                        "prioritized when the outline is regenerated."
                    ),
                }
            )
            if isinstance(reject_response, str):
                reject_reason = reject_response
            elif isinstance(reject_response, dict):
                reject_reason = (
                    reject_response.get("feedback")
                    or reject_response.get("reason")
                    or "No reason provided"
                )
            else:
                reject_reason = "No reason provided"

        reject_reason = reject_reason or "No reason provided"

        logger.info(f"Outline rejected/regeneration requested: {reject_reason}")
        return {
            "content": {
                **content_state,
                "outline": {
                    **outline_dict,
                    "rejected_reason": reject_reason,
                    "status": "rejected",
                },
            }
        }

    return {}
