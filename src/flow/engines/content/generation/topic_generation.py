"""Topic/title generation with a hard SEO contract.

Two rules are non-negotiable and are enforced deterministically after the
model, never by trusting the prompt alone:

* Every title contains the EXACT focus keyphrase the user entered.
* Every title is in its script's range: 50-59 characters for Latin and other narrow scripts
  (up to the keyphrase plus 20, never over 75), 20-30 Chinese, Japanese or Korean characters,
  or 38-55 Thai ones (``seo_title_rules.title_range``, measured by ``title_width``).
* Every title reads as the selected content type, for the selected intent.

The enforcement ladder is: strong system prompt + schema guidance -> LLM
repair pass for the titles that still violate -> deterministic repair
(``seo_title_rules.repair_title``) -> drop only that title. A violation can
never crash the flow and can never silently reach the user, and a failed
regeneration never destroys a previously valid topic set.

THIS NODE IS THE ONLY PLACE A TITLE IS EVER REPAIRED. Every title issue --
keyphrase, length, content-type fit, on-page SEO -- is resolved here, before
the user is asked to choose. Once the user selects one, that exact string is
the article's final title: outline, content generation, repair, humanization
and validation all treat it as read-only and revert any drift back to it (see
``onpage_seo.enforce_onpage_seo``).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from src.flow.engines.content.generation.focus_keyword import (
    FOCUS_KEYWORD_STATE_KEY,
    resolve_focus_keyword,
)
from src.flow.engines.content.generation.seo_title_rules import (
    TITLE_MAX_CHARS_CEILING,
    keyphrase_fits_a_title,
    keyphrase_spellings,
    keyphrase_title,
    normalize_title,
    recase_keyphrase,
    repair_title,
    title_is_valid,
    title_length_terms,
    title_violations,
)
from src.flow.engines.content.generation.title_articles import fix_title_articles
from src.flow.engines.serp.serp_evidence import build_serp_titles
from src.flow.model.llm_manager import topic_generation_model
from src.flow.model.runaway import ainvoke_watched
from src.flow.model.structure.topics import SEOTopic, SEOTopics
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

_REGENERATE_ACTIONS = {"regenerate_topics", "regenerate", "regen"}

# A run whose topic step yields no titles ends here, with this message, instead
# of skipping the title gate into an empty outline (rext-control#359: a refused
# model key did exactly that).
TOPICS_FAILED_CODE = "topic_generation_failed"
TOPICS_FAILED_MESSAGE = (
    "Title ideas could not be written for this keyword just now. Please try again in a few minutes."
)
# Every title must contain the keyphrase and stay within TITLE_MAX_CHARS_CEILING, so a
# longer keyphrase can never produce one: the user has to shorten it.
KEYWORD_TOO_LONG_MESSAGE = (
    f"This keyword is longer than a title can be ({TITLE_MAX_CHARS_CEILING} characters), "
    "so no title can contain it. Try a shorter keyword."
)


# Endings a model reaches for to fill a title to its minimum length (staging, 2026-10-07:
# "How to start a podcast on YouTube: Essential Tips Here"). Named in both title prompts (G65).
_FILLER_EXAMPLES = '"Essential Tips Here", "Read This Now", "All You Need", "Learn More Today"'


def _topics_failed(message: str = TOPICS_FAILED_MESSAGE) -> Dict[str, Any]:
    # The keyphrase is cleared, not pinned: `content` deep-merges, and a pinned
    # phrase outranks the keyword chosen next (resolve_focus_keyword), so a
    # shorter keyword picked after this message would still fail on it. None
    # also clears one an earlier failed attempt on the thread pinned.
    return {
        "content": {
            "topics": [],
            "selected_topic": "",
            "error": message,
            "error_code": TOPICS_FAILED_CODE,
            FOCUS_KEYWORD_STATE_KEY: None,
        }
    }


# The title set the gate shows, and a request for a new one, kept in `content`
# between generate_topics (the model) and topic_generation (the gate). LangGraph
# runs a node again from its start when the user's answer resumes it, so a model
# call in the gate's own node ran again on every answer, and the set it made in
# place of the one shown was the one kept (rext-control#330).
TOPIC_SET_KEY = "topic_set"
# None, or the user's feedback for a new set ("" for none).
TOPIC_REGENERATE_KEY = "topic_regenerate"


def topics_router(state: REXT) -> str:
    """After topic generation: on to the title gate, or to the end when it failed."""
    failed = (state.get("content") or {}).get("error_code") == TOPICS_FAILED_CODE
    return "topics_failed" if failed else "topic_generation"


def topic_gate_router(state: REXT) -> str:
    """After the title gate: a new set of titles, or on to clustering."""
    regenerate = (state.get("content") or {}).get(TOPIC_REGENERATE_KEY)
    return "generate_topics" if regenerate is not None else "keyword_clustering"


async def topics_failed(state: REXT) -> Dict[str, Any]:
    """Terminal node for a run whose topic step produced no titles.

    Like rext.no_serp_data, the message reaches the user as a custom stream
    event (type "run", step "run.failed") and as content.error in the thread
    state. Operators see the failure through the logger.error calls above,
    which the served app turns into throttled error-log rows.
    """
    message = (state.get("content") or {}).get("error") or TOPICS_FAILED_MESSAGE
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(
            {
                "type": "run",
                "step": "run.failed",
                "error_code": TOPICS_FAILED_CODE,
                "message": message,
            }
        )
    except Exception as exc:  # noqa: BLE001 - reporting never breaks the flow
        logger.warning("topics_failed stream emit failed: %s", exc)

    from src.services.generation_events import INTERNAL, REFUSED, TITLES, announce_failed

    # A keyword too long for any title is the person's to change; no titles from the model
    # is ours.
    announce_failed(
        state, stage=TITLES, reason=REFUSED if message == KEYWORD_TOO_LONG_MESSAGE else INTERNAL
    )
    return {}


# A topic set must still be usable after invalid titles are dropped. Below this
# the set is treated as a failed generation. On the first generation one title is
# enough to go on: a long keyphrase leaves room for few, and stopping the run is
# worse than a short picker (G69, rext-control #585). A regeneration needs two, as
# before, or the caller keeps the previous valid set rather than shrink it.
_MIN_USABLE_TOPICS = 1
_MIN_USABLE_REGENERATED_TOPICS = 2


def _is_regenerate_request(response: Any) -> bool:
    """Check if user explicitly asked to regenerate."""
    if isinstance(response, dict):
        action = (response.get("action") or "").strip().lower()

        if action in _REGENERATE_ACTIONS:
            return True

        if response.get("regenerate_topics"):
            return True

    if isinstance(response, str):
        value = response.strip().lower()

        for action in _REGENERATE_ACTIONS:
            if value.startswith(action):
                return True

    return False


def _invalid_title_indexes(parsed: SEOTopics, keyphrase: str) -> List[int]:
    """Indexes of titles violating the length rule or missing the keyphrase."""
    return [
        index
        for index, topic in enumerate(parsed.topics)
        if not title_is_valid(topic.title, keyphrase)
    ]


def _validate_topic_structure(parsed: SEOTopics) -> SEOTopics:
    """
    Normalize safe structural properties without rejecting the complete result.

    This function deliberately does not enforce the title contract by raising,
    because a single invalid title must never break the flow -- that is handled
    by the repair ladder in ``_generate_and_validate_topics``.
    """
    for topic in parsed.topics:
        topic.title = normalize_title(topic.title)

    recommended_indexes = [index for index, topic in enumerate(parsed.topics) if topic.recommended]

    # Ensure exactly one recommendation without failing the flow.
    if len(recommended_indexes) > 1:
        logger.warning(
            "Model returned %d recommended topics. Keeping the first.",
            len(recommended_indexes),
        )

        first_index = recommended_indexes[0]

        for index, topic in enumerate(parsed.topics):
            topic.recommended = index == first_index

    elif len(recommended_indexes) == 0 and parsed.topics:
        logger.warning("Model returned no recommended topic. Using the first topic.")

        parsed.topics[0].recommended = True

    # Recommendation reason should only exist for the recommended topic.
    for topic in parsed.topics:
        if not topic.recommended:
            topic.recommendation_reason = None

    return parsed


async def _repair_invalid_titles(
    model: Any,
    parsed: SEOTopics,
    query: str,
    keyphrase: str,
) -> SEOTopics:
    """
    Ask the LLM to repair only titles that violate the title contract.

    No generic suffix is added by application code at this stage. The repair
    prompt explicitly tells the model not to introduce unsupported information.
    If repair fails or comes back still invalid, the original parsed response is
    returned unchanged and the deterministic net in the caller takes over.
    """
    invalid_indexes = _invalid_title_indexes(parsed, keyphrase)

    if not invalid_indexes:
        return parsed

    invalid_titles = [
        {
            "index": index,
            "title": parsed.topics[index].title,
            "length": len(parsed.topics[index].title),
            "problems": title_violations(parsed.topics[index].title, keyphrase),
        }
        for index in invalid_indexes
    ]

    logger.warning(
        "Found %d title(s) violating the SEO title contract.",
        len(invalid_indexes),
    )

    low, high, how = title_length_terms(keyphrase)
    repair_messages = [
        SystemMessage(
            content=(
                "You are repairing article titles for SEO.\n\n"
                "STRICT TITLE LENGTH REQUIREMENT:\n"
                f"Every repaired title MUST contain between {low} and "
                f"{high} characters inclusive.\n"
                f"{how}\n\n"
                "STRICT FOCUS KEYPHRASE REQUIREMENT:\n"
                f'Every repaired title MUST contain the exact focus keyphrase "{keyphrase}" '
                "word-for-word, in that order.\n"
                "Do NOT substitute a synonym, a singular/plural variant, an abbreviation, "
                "or a reworded version of it.\n"
                "Place it near the beginning when that reads naturally.\n\n"
                "SEO REQUIREMENTS:\n"
                "- Preserve the original topic and meaning.\n"
                "- Avoid keyword stuffing.\n"
                "- Keep the title natural and readable.\n"
                "- Do not add unsupported facts, statistics, dates, products, "
                "companies, people, rankings, or claims.\n"
                "- Do not use generic filler merely to increase character count: no ending "
                f"that would fit any title ({_FILLER_EXAMPLES}). Add who it is for, a number "
                "of steps or items, or the outcome instead (no year: none is given here).\n"
                "- Do not change the subject just to satisfy the character count.\n\n"
                "Only repair the supplied invalid titles. "
                "Do not modify titles that are already valid.\n\n"
                "Before returning each repaired title, internally count its "
                f"characters and verify the result is {low}-{high} "
                "characters and still contains the exact focus keyphrase."
            )
        ),
        HumanMessage(
            content=(
                f"Original user query: {query}\n"
                f"Exact focus keyphrase (must appear verbatim): {keyphrase}\n\n"
                f"Titles requiring repair:\n{invalid_titles}\n\n"
                "Return the same topic structure with the repaired titles."
            )
        ),
    ]

    try:
        repaired: SEOTopics = await ainvoke_watched(
            model, repair_messages, stage="titles", schema=SEOTopics
        )

        repaired = fix_title_articles(_validate_topic_structure(repaired), keyphrase)

        # We only replace titles for the original invalid indexes, and only when
        # the replacement actually complies. This prevents the repair call from
        # unexpectedly changing valid titles or other topic metadata, and stops
        # one still-broken repair from discarding the other successful ones.
        repaired_count = 0
        for index in invalid_indexes:
            if index >= len(repaired.topics):
                continue
            candidate = repaired.topics[index].title
            if title_is_valid(candidate, keyphrase):
                parsed.topics[index].title = candidate
                repaired_count += 1

        logger.info(
            "LLM title repair fixed %d of %d invalid title(s).",
            repaired_count,
            len(invalid_indexes),
        )

        return parsed

    except Exception:
        logger.exception("Title repair failed. Keeping the original parsed topic result.")
        return parsed


def _apply_deterministic_title_repair(parsed: SEOTopics, keyphrase: str) -> SEOTopics:
    """Last net: repair or drop every title still violating the contract.

    Deterministic so the outcome does not depend on a second model call
    succeeding. A title that cannot be brought into compliance is dropped
    rather than shown -- an invalid title must never reach the user.
    """
    kept = []

    for topic in parsed.topics:
        # The title as validation measures it (NFC, whitespace and quotes trimmed), so what the
        # picker shows is exactly what passed.
        topic.title = normalize_title(topic.title)
        if title_is_valid(topic.title, keyphrase):
            kept.append(topic)
            continue

        repaired = repair_title(topic.title, keyphrase)

        if repaired:
            logger.info(
                "Deterministically repaired title %r -> %r",
                topic.title,
                repaired,
            )
            topic.title = repaired
            kept.append(topic)
        else:
            logger.warning(
                "Dropping title %r -- cannot satisfy the SEO title contract (%s).",
                topic.title,
                title_violations(topic.title, keyphrase),
            )

    parsed.topics = kept
    return _validate_topic_structure(parsed) if kept else parsed


def _recase_keyphrase_in_titles(parsed: SEOTopics, keyphrase: str) -> None:
    """Each title writes the keyphrase in its own case (G49): the model copies the user's
    lowercase into a Title Case title ("Find the Best seo agency for small business")."""
    spellings = keyphrase_spellings([topic.title for topic in parsed.topics], keyphrase)
    for topic in parsed.topics:
        recased = recase_keyphrase(topic.title, keyphrase, spellings)
        if recased != topic.title and title_is_valid(recased, keyphrase):
            topic.title = recased


def _fix_articles_keeping_valid(parsed: SEOTopics, keyphrase: str) -> None:
    """The articles once more, after the last recasing: a repaired title's keyphrase may have
    changed case since the first pass ("a seo agency" is now "a SEO Agency"). Nothing checks the
    titles after this, so a change that would make a valid title invalid is taken back."""
    written = [topic.title for topic in parsed.topics]
    fix_title_articles(parsed, keyphrase)
    for topic, was in zip(parsed.topics, written):
        if (
            topic.title != was
            and title_is_valid(was, keyphrase)
            and not title_is_valid(topic.title, keyphrase)
        ):
            topic.title = was


async def _generate_and_validate_topics(
    model: Any,
    messages: List[Any],
    query: str,
    keyphrase: str,
    regenerating: bool = False,
) -> Optional[SEOTopics]:
    """
    Generate topics and apply the non-breaking SEO validation/repair layer.

    Important production behavior:
    - A title contract violation does not crash the flow.
    - The model is asked to repair invalid titles.
    - Anything still invalid is repaired deterministically, or dropped.
    - If too few usable topics survive, None is returned so the caller can
      preserve the previously valid topics.
    """
    try:
        results: SEOTopics = await ainvoke_watched(
            model, messages, stage="titles", schema=SEOTopics
        )

        # The keyphrase in each title's case first (G49), so the article is judged by the word as
        # the title will show it ("an SEO agency", where the model copied "seo"). Then "a" or "an"
        # (G65), right before the titles are checked, so one it lengthens past the limit goes
        # through the repairs like any other.
        results = _validate_topic_structure(results)
        _recase_keyphrase_in_titles(results, keyphrase)
        results = fix_title_articles(results, keyphrase)

        if not results.topics:
            logger.warning("Model returned no topics for query=%r.", query)
            return None

        if _invalid_title_indexes(results, keyphrase):
            results = await _repair_invalid_titles(
                model=model,
                parsed=results,
                query=query,
                keyphrase=keyphrase,
            )

        results = _apply_deterministic_title_repair(results, keyphrase)

        if not results.topics and not regenerating:
            # Every title was dropped: the keyphrase itself is offered as the one title
            # rather than ending the run (G69). A regeneration keeps the previous set.
            fallback = keyphrase_title(keyphrase)
            if fallback:
                logger.warning(
                    "No generated title survived for query=%r; offering the keyphrase.", query
                )
                results.topics = [SEOTopic(title=fallback, recommended=True)]

        _recase_keyphrase_in_titles(results, keyphrase)
        _fix_articles_keeping_valid(results, keyphrase)

        minimum = _MIN_USABLE_REGENERATED_TOPICS if regenerating else _MIN_USABLE_TOPICS
        if len(results.topics) < minimum:
            logger.warning(
                "Only %d usable title(s) survived validation for query=%r.",
                len(results.topics),
                query,
            )
            return None

        return results

    except Exception:
        logger.exception("Topic generation failed for query=%r.", query)

        return None


def _extract_topics(
    parsed: SEOTopics,
) -> Tuple[List[str], Optional[str], Optional[str]]:
    """
    Extract titles for the existing payload plus recommendation metadata.
    """
    titles = [topic.title for topic in parsed.topics]

    recommended_pick = next(
        (topic for topic in parsed.topics if topic.recommended),
        None,
    )

    recommended = recommended_pick.title if recommended_pick else (titles[0] if titles else None)

    reason = recommended_pick.recommendation_reason if recommended_pick else None

    return titles, recommended, reason


def _build_system_prompt(
    *,
    keyphrase: str,
    current_year: int,
    selected_intent: str,
    selected_content_type: str,
) -> str:
    """The title contract, stated once, with the run's own intent/type folded in.

    Intent and content type are named inside the contract rather than listed as
    trailing metadata: a title for a "comparison" with commercial intent is a
    materially different artefact from an "how-to guide" with informational
    intent, and stating that where the rules are read is what makes the
    generated topic specific to the selection instead of generic.
    """
    low, high, how = title_length_terms(keyphrase)
    return (
        "You are helping someone with ZERO SEO or content-marketing "
        "background choose what to write next.\n\n"
        f"Generate exactly 5 article topic ideas for {current_year} that fit the user's "
        "selected search intent and content type.\n\n"
        "==================================================\n"
        "STRICT FOCUS KEYPHRASE REQUIREMENT\n"
        "==================================================\n"
        f'THE EXACT FOCUS KEYPHRASE IS: "{keyphrase}"\n\n'
        "EVERY SINGLE TITLE MUST CONTAIN THIS EXACT PHRASE, WORD FOR WORD.\n"
        "- Use the phrase verbatim, in this exact word order.\n"
        "- Only its case may change: write it in the title's own case, capitalized like the "
        "rest of a Title Case title, with acronyms such as SEO in capitals.\n"
        "- Do NOT substitute a synonym, abbreviation, singular/plural variant, "
        "reordering, or any reworded version.\n"
        "- Do NOT invent, choose, or substitute a different focus keyword.\n"
        "- Place it near the beginning of the title whenever that reads naturally.\n"
        "- Use it once per title. Do not repeat it.\n"
        "- A title that does not contain this exact phrase is INVALID and will be rejected.\n\n"
        "==================================================\n"
        "STRICT SEO TITLE LENGTH REQUIREMENT\n"
        "==================================================\n"
        f"EVERY TITLE MUST BE BETWEEN {low} AND {high} "
        "CHARACTERS INCLUSIVE.\n\n"
        "This is a strict requirement.\n"
        f"- Minimum: {low} characters.\n"
        f"- Maximum: {high} characters.\n"
        f"- {how}\n"
        "- Count the final title before returning it.\n"
        "- If the first draft is outside the range, rewrite it before returning "
        "the final answer.\n\n"
        f"Do NOT add meaningless filler just to reach {low} characters. Filler is "
        "an ending that says nothing about the article and would fit any title: "
        f"{_FILLER_EXAMPLES}. To lengthen a title, add something specific to the "
        "topic instead: who it is for, a number of steps or items, the outcome, or the year.\n"
        f"Do NOT remove important meaning just to stay below {high} characters.\n"
        "The final title must be natural, readable, and useful.\n\n"
        "==================================================\n"
        "CONTENT TYPE AND SEARCH INTENT\n"
        "==================================================\n"
        f"Content type: {selected_content_type}\n"
        f"Search intent: {selected_intent}\n\n"
        f"Every title must read like a real {selected_content_type} that satisfies "
        f"{selected_intent} intent for this keyphrase.\n"
        "- The title must make it obvious what KIND of page this is.\n"
        f"- A '{selected_content_type}' title must promise what that format actually "
        "delivers -- do not produce a generic title that would fit any format.\n"
        "- Match the depth and angle to the intent: informational intent wants "
        "explanation and guidance, commercial intent wants evaluation and comparison, "
        "transactional intent wants action and offer, navigational intent wants a "
        "specific destination or brand.\n"
        "- Be specific about the SUBJECT: state exactly what kind of thing the article "
        "covers (for example agencies, tools, services, courses, templates) and keep "
        "that subject consistent with the keyphrase. The article body will be written "
        "to match the title's subject exactly, so a vague or mismatched subject "
        "produces the wrong article.\n\n"
        "==================================================\n"
        "SEO TITLE QUALITY\n"
        "==================================================\n"
        "- Avoid keyword stuffing.\n"
        "- Avoid unnecessary repetition.\n"
        "- Make every title clear and specific.\n"
        "- Make titles sound like something a real person would click or search.\n"
        "- Avoid excessive punctuation and special characters.\n"
        "- Do not use misleading clickbait.\n"
        "- Make the 5 titles meaningfully different angles, not rewordings of "
        "each other.\n\n"
        "==================================================\n"
        "ACCURACY / ANTI-HALLUCINATION\n"
        "==================================================\n"
        "Titles must be grounded in the user's query and provided context.\n"
        "Do NOT invent:\n"
        "- statistics\n"
        "- search volume\n"
        "- competition information\n"
        "- rankings\n"
        "- companies\n"
        "- products\n"
        "- people\n"
        "- dates\n"
        "- numerical claims\n"
        "- unsupported benefits\n"
        "- unsupported factual claims\n\n"
        "Do not claim something is 'best', '#1', 'guaranteed', 'most popular', or "
        "similar unless that claim is explicitly supported by the provided context.\n\n"
        "==================================================\n"
        "RECOMMENDATION\n"
        "==================================================\n"
        "Mark exactly ONE topic as recommended=True.\n"
        "All other topics must have recommended=False.\n"
        "The recommended topic must contain one short, plain-English "
        "recommendation_reason.\n"
        "All other recommendation_reason values must be null.\n"
        "Do not use SEO jargon in the recommendation reason.\n\n"
        "==================================================\n"
        "FINAL SELF-CHECK BEFORE RESPONSE\n"
        "==================================================\n"
        "Before returning the structured result, verify EVERY title:\n"
        f'1. Does it contain the exact phrase "{keyphrase}"?\n'
        f"2. Is it at least {low} characters?\n"
        f"3. Is it at most {high} characters?\n"
        f"4. Does it read like a {selected_content_type} for {selected_intent} intent?\n"
        "5. Is it readable and natural?\n"
        "6. Does it avoid keyword stuffing?\n"
        "7. Does it avoid unsupported claims?\n\n"
        "If any title fails one of these checks, rewrite that title before "
        "returning the final structured response.\n\n"
        "The application also performs a final deterministic validation after model "
        "output. A title mistake must NEVER be treated as a reason to crash the "
        "user's topic-generation flow."
    )


def _build_human_prompt(
    *,
    query: str,
    keyphrase: str,
    current_year: int,
    selected_intent: str,
    selected_content_type: str,
    related_topics: List[str],
    questions: List[str],
) -> str:
    """The run's own topic context, so titles are specific rather than generic."""
    topic_context = ""

    if related_topics:
        topic_context += "\nRelated topics people also search:\n" + "\n".join(
            f"- {item}" for item in related_topics[:8]
        )

    if questions:
        topic_context += "\nQuestions people ask about this:\n" + "\n".join(
            f"- {item}" for item in questions[:8]
        )

    if topic_context:
        topic_context = (
            f"\nTOPIC CONTEXT (use it to make the titles specific; do not treat any of "
            f"it as a verified fact):{topic_context}\n"
        )

    return (
        f"Generate exactly 5 topics for: {query}\n"
        f'Exact focus keyphrase that MUST appear verbatim in every title: "{keyphrase}"\n'
        f"Year: {current_year}\n"
        f"Search intent: {selected_intent}\n"
        f"Content type: {selected_content_type}\n"
        f"{topic_context}"
    )


def _topic_query(state: REXT) -> str:
    query = (state.get("serp_normalized") or {}).get("query")
    return query or (state.get("serp_payload") or {}).get("query", "")


def _regeneration_feedback(user_response: Any) -> str:
    """The user's words for a new set of titles ("" when they gave none)."""
    feedback = ""

    if isinstance(user_response, dict):
        feedback = (user_response.get("feedback", "") or "").strip()

    elif isinstance(user_response, str):
        value = user_response.strip()

        for action in _REGENERATE_ACTIONS:
            if value.lower().startswith(action):
                feedback = value[len(action) :].strip()
                feedback = feedback.lstrip(".: ").strip()
                break

    if feedback.lower() in {"none", "skip", "no", "n/a", ""}:
        feedback = ""

    return feedback


async def generate_topics(state: REXT) -> Dict[str, Any]:
    """The title step's model work, before its gate (topic_generation).

    The first set of titles, or a new one when the gate asked for it
    (content.topic_regenerate). The set waits in content.topic_set, so the
    answer that resumes the gate never repeats this call.
    """
    logger.info("Starting topic generation")

    feedback = (state.get("content") or {}).get(TOPIC_REGENERATE_KEY)
    regenerating = feedback is not None

    # -- Resolve query -------------------------------------------------
    normalized_result = state.get("serp_normalized", {})

    if normalized_result and normalized_result.get("error"):
        logger.warning(
            "Skipping topic generation due to upstream error: %s",
            normalized_result["error"],
        )

        return _topics_failed()

    query = _topic_query(state)

    if not query:
        logger.warning("No query found")

        return _topics_failed()

    # -- Resolve the EXACT user-entered focus keyphrase -----------------
    #
    # This is the single source of truth for the rest of the pipeline: it is
    # pinned into content state by the gate so outline, generation, repair,
    # humanization and validation all enforce the same phrase instead of each
    # re-deriving one (which is how the model's own invented keyphrase used to
    # take over downstream).
    keyphrase = resolve_focus_keyword(state) or normalize_title(query)

    if not keyphrase_fits_a_title(keyphrase):
        logger.warning(
            "Keyphrase of %d characters can fit no title of at most %d.",
            len(keyphrase),
            TITLE_MAX_CHARS_CEILING,
        )
        return _topics_failed(KEYWORD_TOO_LONG_MESSAGE)

    # -- Resolve intent and content type -------------------------------
    serp_backlinks = state.get("seo_result", {}).get("serp_backlinks", {})

    selected_intent = serp_backlinks.get("main_intent", "informational")

    selected_content_type = state.get("content", {}).get("content_type", "article")

    # -- Build model ---------------------------------------------------
    model = topic_generation_model().with_structured_output(SEOTopics)

    current_year = datetime.now(timezone.utc).year

    messages = [
        SystemMessage(
            content=_build_system_prompt(
                keyphrase=keyphrase,
                current_year=current_year,
                selected_intent=selected_intent,
                selected_content_type=selected_content_type,
            )
        ),
        HumanMessage(
            content=_build_human_prompt(
                query=query,
                keyphrase=keyphrase,
                current_year=current_year,
                selected_intent=selected_intent,
                selected_content_type=selected_content_type,
                related_topics=normalized_result.get("related_topics") or [],
                questions=normalized_result.get("questions") or [],
            )
        ),
    ]

    if feedback:
        logger.info("Adding user feedback to model prompt: %s", feedback)
        low, high, how = title_length_terms(keyphrase)

        messages.append(
            HumanMessage(
                content=(
                    "User requested regeneration with the following feedback:\n\n"
                    f"{feedback}\n\n"
                    "Keep ALL strict requirements from the system prompt. In "
                    f"particular, every title must still contain the exact phrase "
                    f'"{keyphrase}" and be {low}-{high} '
                    f"characters ({how}), and the anti-hallucination rules still apply. "
                    "User feedback can change the angle, wording or emphasis of a "
                    "title -- it can NEVER change or remove the focus keyphrase."
                )
            )
        )

    results = await _generate_and_validate_topics(
        model=model,
        messages=messages,
        query=query,
        keyphrase=keyphrase,
        regenerating=regenerating,
    )

    if results is None:
        if regenerating:
            # Critical production behavior:
            # Never destroy the user's existing valid topics because a
            # regeneration attempt failed: the gate shows the set it had.
            logger.warning("Topic regeneration failed. Keeping previous valid topics.")
            return {"content": {TOPIC_REGENERATE_KEY: None}}

        logger.error("Unable to generate a valid topic set for query=%r.", query)

        return _topics_failed()

    topics, recommended_topic, recommendation_reason = _extract_topics(results)

    logger.info(
        "Generated %d valid topics (recommended=%s)",
        len(topics),
        recommended_topic,
    )

    return {
        "content": {
            TOPIC_SET_KEY: {
                "topics": topics,
                "recommended_topic": recommended_topic,
                "recommendation_reason": recommendation_reason,
                "focus_keyphrase": keyphrase,
            },
            TOPIC_REGENERATE_KEY: None,
            # content deep-merges, and topics_router reads it next: an earlier
            # failed attempt on this thread would still end the run here.
            "error": None,
            "error_code": None,
        }
    }


async def topic_generation(state: REXT) -> Dict[str, Any]:
    """The title gate: the set generate_topics wrote, and the user's choice.

    It calls no model, so the answer that resumes it costs nothing; a request
    for new titles, or an empty choice, goes back to generate_topics
    (topic_gate_router). A run paused here before the set was kept in the
    state resumes with an empty set, which only the answer's replay reads.
    """
    topic_set = (state.get("content") or {}).get(TOPIC_SET_KEY) or {}
    keyphrase = (
        topic_set.get("focus_keyphrase")
        or resolve_focus_keyword(state)
        or normalize_title(_topic_query(state))
    )

    user_response = interrupt(
        {
            "type": "topic",
            "instruction": "Select a title",
            "topics": topic_set.get("topics") or [],
            "recommended_topic": topic_set.get("recommended_topic"),
            "recommendation_reason": topic_set.get("recommendation_reason"),
            "focus_keyphrase": keyphrase,
            "allow_regenerate": True,
            # The SERP's top ten, for the side panel beside the candidates
            # (empty when the run has no SERP).
            "serp_titles": build_serp_titles(state.get("serp_normalized", {})),
        }
    )

    # -- Explicit regenerate --------------------------------------------
    if _is_regenerate_request(user_response):
        logger.info("User requested regeneration")
        return {"content": {TOPIC_REGENERATE_KEY: _regeneration_feedback(user_response)}}

    # -- Extract selected topic ------------------------------------------
    if isinstance(user_response, dict):
        selected_topic = (
            user_response.get("Selected Topic")
            or user_response.get("selected_topic")
            or user_response.get("topic")
            or ""
        )
    else:
        selected_topic = str(user_response)

    selected_topic = normalize_title(selected_topic)

    # -- Auto regenerate if empty ----------------------------------------
    if not selected_topic:
        logger.warning("Empty topic selection -> attempting regeneration.")
        return {"content": {TOPIC_REGENERATE_KEY: ""}}

    # -- Selection is FINAL from here on ---------------------------------
    #
    # Every title offered in the picker has already been through the full
    # contract: exact focus keyphrase, its length range, content type and
    # search intent. That is deliberately the ONLY place a title is ever
    # repaired. The moment the user picks one it is frozen: no outline,
    # generation, repair, humanization or validation stage may reword,
    # re-optimize, trim or "improve" it. So nothing is rewritten here
    # either -- a selection that deviates is logged for observability and
    # then used exactly as the user gave it.
    if not title_is_valid(selected_topic, keyphrase):
        logger.warning(
            "Selected topic %r does not satisfy the title contract (%s). Using it "
            "verbatim anyway -- a user-selected title is never rewritten.",
            selected_topic,
            title_violations(selected_topic, keyphrase),
        )

    logger.info("User selected topic (locked): %s", selected_topic)

    return {
        "content": {
            "topics": topic_set.get("topics") or [],
            "recommended_topic": topic_set.get("recommended_topic"),
            "selected_topic": selected_topic,
            FOCUS_KEYWORD_STATE_KEY: keyphrase,
            # content deep-merges, so an earlier failed attempt on this thread
            # would otherwise still route the run to topics_failed.
            "error": None,
            "error_code": None,
        }
    }
