import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from src.flow.model.llm_manager import topic_generation_model
from src.flow.model.structure.content_type_recommendation import ContentTypeRecommendation
from src.flow.model.structure.intent_suggestion import INTENT_TO_CONTENT_TYPES
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def _recommend_content_type(
    query: str, search_intent: str, candidates: list[str]
) -> tuple[str | None, str | None]:
    """Best-effort LLM pick of the best content type from `candidates`.

    Never raises — a failed/invalid recommendation just means no highlight is shown,
    the existing manual-selection flow is untouched either way.
    """
    if not query or not candidates:
        return None, None

    try:
        model = topic_generation_model().with_structured_output(ContentTypeRecommendation)
        messages = [
            SystemMessage(
                content=(
                    "You are helping someone with ZERO SEO or content-marketing background pick the "
                    "right article format for their topic. They do not know what these format names or "
                    "terms like 'search intent' technically mean — your job is to choose FOR them, the "
                    "way a knowledgeable friend would, not to make them evaluate jargon themselves.\n\n"
                    "From the candidate formats given, pick the ONE most likely to satisfy what people "
                    "are actually searching for AND realistic for a beginner to write well without "
                    "specialist skills or expensive research. Prefer the safer, more standard choice "
                    "over a niche or advanced format unless the topic clearly calls for it.\n\n"
                    "Then explain the pick in one short, plain-English sentence: no SEO jargon ('SERP', "
                    "'intent', 'conversion', 'funnel', etc). If you reference why people are searching, "
                    "say it in plain terms (e.g. 'people want to compare their options before buying' "
                    "instead of 'commercial intent')."
                )
            ),
            HumanMessage(
                content=(
                    f"Topic/keyword: {query}\n"
                    f"Why people are likely searching this (search intent): {search_intent}\n"
                    f"Candidate formats: {', '.join(candidates)}\n\n"
                    f"Pick the single best-fit format from the candidates above and explain why in "
                    f"plain language a complete beginner would understand."
                )
            ),
        ]
        result: ContentTypeRecommendation = model.invoke(messages)
        # Only trust it if it's actually one of the offered options.
        match = next(
            (c for c in candidates if c.lower() == result.recommended_content_type.strip().lower()),
            None,
        )
        if match:
            return match, result.reason
        logger.warning(
            "Content type recommendation %r not in candidate list, dropping it",
            result.recommended_content_type,
        )
    except Exception:
        logger.exception("Content type recommendation failed, continuing without it")

    return None, None


def content_type(state: REXT) -> REXT:
    logger.info("Starting content type selection")

    content_state = state.get("content", {})

    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    logger.info(f"serp_backlinks: {serp_backlinks}")

    search_intent = (
        serp_backlinks.get("main_intent") or state.get("final_intent_type") or "informational"
    )
    if search_intent == "unknown":
        search_intent = state.get("final_intent_type") or "informational"

    candidate_content_types = INTENT_TO_CONTENT_TYPES.get(search_intent.lower(), [])

    query = state.get("serp_normalized", {}).get("query") or state.get("serp_payload", {}).get(
        "query", ""
    )
    recommended_content_type, recommendation_reason = _recommend_content_type(
        query, search_intent, candidate_content_types
    )

    # show the intent and ask the user to select the content type
    selected_content_type = interrupt(
        {
            "instruction": "Select a content type",
            "search_intent": search_intent,
            "content_types": candidate_content_types,
            # Additive fields — existing "content_types" list is unchanged so current
            # frontend handling keeps working; UI can optionally highlight this pick.
            "recommended_content_type": recommended_content_type,
            "recommendation_reason": recommendation_reason,
            "type": "content_type",
        }
    )

    # Handle user selection (can be string or dict)
    final_selection = ""
    if isinstance(selected_content_type, str):
        final_selection = selected_content_type
    elif isinstance(selected_content_type, dict):
        final_selection = (
            selected_content_type.get("content_type")
            or selected_content_type.get("Selected Content Type")
            or ""
        )

    # Save the selected content type to the state
    content_state["content_type"] = final_selection or "article"

    logger.info(f"Content type selected: {content_state['content_type']}")

    return {"content": content_state}
