"""Topic/title generation with a hard SEO contract.

Two rules are non-negotiable and are enforced deterministically after the
model, never by trusting the prompt alone:

* Every title contains the EXACT focus keyphrase the user entered.
* Every title is 50-59 characters inclusive.
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
    TITLE_MAX_CHARS,
    TITLE_MIN_CHARS,
    normalize_title,
    repair_title,
    title_is_valid,
    title_violations,
)
from src.flow.model.llm_manager import topic_generation_model
from src.flow.model.structure.topics import SEOTopics
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

_REGENERATE_ACTIONS = {"regenerate_topics", "regenerate", "regen"}

# A topic set must still be usable after invalid titles are dropped. Below this
# the set is treated as a failed generation so the caller keeps the previous
# valid one instead of showing the user a near-empty picker.
_MIN_USABLE_TOPICS = 2


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

    repair_messages = [
        SystemMessage(
            content=(
                "You are repairing article titles for SEO.\n\n"
                "STRICT TITLE LENGTH REQUIREMENT:\n"
                f"Every repaired title MUST contain between {TITLE_MIN_CHARS} and "
                f"{TITLE_MAX_CHARS} characters inclusive.\n"
                "Count spaces and punctuation as characters.\n\n"
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
                "- Do not use generic filler merely to increase character count.\n"
                "- Do not change the subject just to satisfy the character count.\n\n"
                "Only repair the supplied invalid titles. "
                "Do not modify titles that are already valid.\n\n"
                "Before returning each repaired title, internally count its "
                f"characters and verify the result is {TITLE_MIN_CHARS}-{TITLE_MAX_CHARS} "
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
        repaired: SEOTopics = await model.ainvoke(repair_messages)

        repaired = _validate_topic_structure(repaired)

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


async def _generate_and_validate_topics(
    model: Any,
    messages: List[Any],
    query: str,
    keyphrase: str,
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
        results: SEOTopics = await model.ainvoke(messages)

        results = _validate_topic_structure(results)

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

        if len(results.topics) < _MIN_USABLE_TOPICS:
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
        "- Do NOT substitute a synonym, abbreviation, singular/plural variant, "
        "reordering, or any reworded version.\n"
        "- Do NOT invent, choose, or substitute a different focus keyword.\n"
        "- Place it near the beginning of the title whenever that reads naturally.\n"
        "- Use it once per title. Do not repeat it.\n"
        "- A title that does not contain this exact phrase is INVALID and will be rejected.\n\n"
        "==================================================\n"
        "STRICT SEO TITLE LENGTH REQUIREMENT\n"
        "==================================================\n"
        f"EVERY TITLE MUST BE BETWEEN {TITLE_MIN_CHARS} AND {TITLE_MAX_CHARS} "
        "CHARACTERS INCLUSIVE.\n\n"
        "This is a strict requirement.\n"
        f"- Minimum: {TITLE_MIN_CHARS} characters.\n"
        f"- Maximum: {TITLE_MAX_CHARS} characters.\n"
        "- Count spaces as characters.\n"
        "- Count punctuation as characters.\n"
        "- Count the final title before returning it.\n"
        "- If the first draft is outside the range, rewrite it before returning "
        "the final answer.\n\n"
        f"Do NOT add meaningless filler just to reach {TITLE_MIN_CHARS} characters.\n"
        f"Do NOT remove important meaning just to stay below {TITLE_MAX_CHARS} characters.\n"
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
        f"2. Is it at least {TITLE_MIN_CHARS} characters?\n"
        f"3. Is it at most {TITLE_MAX_CHARS} characters?\n"
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


async def topic_generation(state: REXT) -> Dict[str, Any]:
    logger.info("Starting topic generation")

    # -- Resolve query -------------------------------------------------
    normalized_result = state.get("serp_normalized", {})

    if normalized_result and normalized_result.get("error"):
        logger.warning(
            "Skipping topic generation due to upstream error: %s",
            normalized_result["error"],
        )

        return {
            "content": {
                "topics": [],
                "selected_topic": "",
            }
        }

    query = normalized_result.get("query")

    if not query:
        serp_payload = state.get("serp_payload", {})
        query = serp_payload.get("query", "")

    if not query:
        logger.warning("No query found")

        return {
            "content": {
                "topics": [],
                "selected_topic": "",
            }
        }

    # -- Resolve the EXACT user-entered focus keyphrase -----------------
    #
    # This is the single source of truth for the rest of the pipeline: it is
    # pinned into content state below so outline, generation, repair,
    # humanization and validation all enforce the same phrase instead of each
    # re-deriving one (which is how the model's own invented keyphrase used to
    # take over downstream).
    keyphrase = resolve_focus_keyword(state) or normalize_title(query)

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

    # -- Initial generation --------------------------------------------
    results = await _generate_and_validate_topics(
        model=model,
        messages=messages,
        query=query,
        keyphrase=keyphrase,
    )

    if results is None:
        logger.error("Unable to generate a valid topic set for query=%r.", query)

        return {
            "content": {
                "topics": [],
                "selected_topic": "",
                FOCUS_KEYWORD_STATE_KEY: keyphrase,
            }
        }

    topics, recommended_topic, recommendation_reason = _extract_topics(results)

    logger.info(
        "Generated %d valid topics (recommended=%s)",
        len(topics),
        recommended_topic,
    )

    # -- Keep the last valid result for production safety ---------------
    last_valid_topics = topics
    last_valid_recommended = recommended_topic
    last_valid_reason = recommendation_reason

    # -- Infinite loop until valid selection ----------------------------
    while True:
        user_response = interrupt(
            {
                "type": "topic",
                "instruction": "Select a topic",
                "topics": last_valid_topics,
                "recommended_topic": last_valid_recommended,
                "recommendation_reason": last_valid_reason,
                "focus_keyphrase": keyphrase,
                "allow_regenerate": True,
            }
        )

        # -- Explicit regenerate ----------------------------------------
        if _is_regenerate_request(user_response):
            logger.info("User requested regeneration")

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

            if feedback.lower() in {
                "none",
                "skip",
                "no",
                "n/a",
                "",
            }:
                feedback = ""

            regeneration_messages = list(messages)

            if feedback:
                logger.info("Adding user feedback to model prompt: %s", feedback)

                regeneration_messages.append(
                    HumanMessage(
                        content=(
                            "User requested regeneration with the following feedback:\n\n"
                            f"{feedback}\n\n"
                            "Keep ALL strict requirements from the system prompt. In "
                            f"particular, every title must still contain the exact phrase "
                            f'"{keyphrase}" and be {TITLE_MIN_CHARS}-{TITLE_MAX_CHARS} '
                            "characters, and the anti-hallucination rules still apply. "
                            "User feedback can change the angle, wording or emphasis of a "
                            "title -- it can NEVER change or remove the focus keyphrase."
                        )
                    )
                )

            regenerated_results = await _generate_and_validate_topics(
                model=model,
                messages=regeneration_messages,
                query=query,
                keyphrase=keyphrase,
            )

            if regenerated_results is not None:
                (
                    last_valid_topics,
                    last_valid_recommended,
                    last_valid_reason,
                ) = _extract_topics(regenerated_results)

                logger.info("Topic regeneration succeeded with valid SEO titles.")
            else:
                # Critical production behavior:
                # Never destroy the user's existing valid topics because a
                # regeneration attempt failed.
                logger.warning("Topic regeneration failed. Keeping previous valid topics.")

            continue

        # -- Extract selected topic --------------------------------------
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

        # -- Auto regenerate if empty ------------------------------------
        if not selected_topic:
            logger.warning("Empty topic selection -> attempting regeneration.")

            regenerated_results = await _generate_and_validate_topics(
                model=model,
                messages=messages,
                query=query,
                keyphrase=keyphrase,
            )

            if regenerated_results is not None:
                (
                    last_valid_topics,
                    last_valid_recommended,
                    last_valid_reason,
                ) = _extract_topics(regenerated_results)

            else:
                logger.warning("Automatic regeneration failed. Keeping previous valid topics.")

            continue

        # -- Selection is FINAL from here on -----------------------------
        #
        # Every title offered in the picker has already been through the full
        # contract: exact focus keyphrase, 50-59 characters, content type and
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

        # -- Valid topic -> exit loop ------------------------------------
        logger.info("User selected topic (locked): %s", selected_topic)

        break

    return {
        "content": {
            "topics": last_valid_topics,
            "recommended_topic": last_valid_recommended,
            "selected_topic": selected_topic,
            FOCUS_KEYWORD_STATE_KEY: keyphrase,
        }
    }
