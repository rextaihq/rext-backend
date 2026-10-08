import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from src.flow.engines.serp.serp_evidence import build_serp_evidence
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


# The model's pick for the content-type gate, kept in `content` by
# recommend_content_type so the gate itself never calls the model: LangGraph
# runs a node again from its start when the user's answer resumes it
# (rext-control#330).
CONTENT_TYPE_PICK_KEY = "content_type_pick"


# The article types any keyword can become, offered after the intent's own types whatever the
# intent was read as (rext-control#815). The intent is the search provider's label for the
# keyword, and one wrong label left a customer with no article type at all: "remote team
# onboarding" was read as navigational and offered only a brand's own pages.
ARTICLE_TYPES_FOR_ANY_INTENT = ("blog", "how-to-guide", "explainer")


def offered_content_types(intent_types: list[str]) -> list[str]:
    """The types the gate offers: the intent's own, in their order, then the article types
    that are not among them. The dashboard leads with the recommended type and the intent's
    common ones and folds the rest under "more", so a keyword read rightly looks as before."""
    return [*intent_types, *(t for t in ARTICLE_TYPES_FOR_ANY_INTENT if t not in intent_types)]


def intent_of_choice(chosen: str, intent: str) -> str:
    """The intent the rest of the run is written for, once the customer has chosen a type.

    A type of the keyword's own intent leaves it. A type of another intent (an article for a
    keyword read as navigational) is the customer saying what the page is, and that type's
    intent takes over: left at "navigational", the titles are asked to name a destination or
    a brand for what is to be a blog. A choice no intent lists (free text) leaves it."""
    intent = (intent or "").strip().lower()
    chosen = (chosen or "").strip().lower()
    if chosen in INTENT_TO_CONTENT_TYPES.get(intent, []):
        return intent
    return next(
        (name for name, types in INTENT_TO_CONTENT_TYPES.items() if chosen in types), intent
    )


def recommended_among(
    intent_types: list[str], serp_evidence: dict | None, results_read_as: str | None = None
) -> list[str]:
    """The types the recommendation is made among: the intent's own, and the article types
    where what the search shows says the keyword is an article's.

    The intent is the search provider's label for the keyword. Two readings of our own stand
    beside it: the format most of the top results share, and the intent read from those
    results (``results_read_as``, the run's `final_intent_type`). "remote team onboarding"
    was labelled navigational while its results read as informational, and the pick, made
    among a brand's pages, was "documentation".

    * The results read as informational and the label says otherwise: the three article
      types join.
    * The results lead with a how-to or an explainer format: that type joins.

    With neither, the intent's own alone, as before: a brand's own name, whose results read
    as navigational too, keeps its site pages."""
    leading = ((serp_evidence or {}).get("dominant_format") or {}).get("content_types") or []
    read_as_articles = (results_read_as or "").strip().lower() == "informational"
    return [
        *intent_types,
        *(
            t
            for t in ARTICLE_TYPES_FOR_ANY_INTENT
            if t not in intent_types and (read_as_articles or t in leading)
        ),
    ]


def intent_for_the_pick(search_intent: str, results_read_as: str | None) -> str:
    """What the recommendation is told of the intent: the label, and what the results read as
    when the two disagree, so the pick weighs both and not the label alone."""
    read_as = (results_read_as or "").strip().lower()
    label = (search_intent or "").strip().lower()
    if not read_as or read_as in ("unknown", label):
        return search_intent
    return f"{search_intent} by the keyword's data, but the top search results read as {read_as}"


def _gate_inputs(state: REXT) -> tuple[str, list[str], str]:
    """The search intent, the formats that intent is written as (the recommendation is made
    among these) and the query, from the state."""
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
    return search_intent, candidate_content_types, query


def recommend_content_type(state: REXT) -> REXT:
    """The content-type gate's model call, made once before the gate opens."""
    logger.info("Starting content type selection")

    search_intent, candidate_content_types, query = _gate_inputs(state)
    # Our own reading of the top results, kept beside the provider's label for the keyword.
    results_read_as = state.get("final_intent_type")
    recommended_content_type, recommendation_reason = _recommend_content_type(
        query,
        intent_for_the_pick(search_intent, results_read_as),
        recommended_among(
            candidate_content_types,
            build_serp_evidence(state.get("serp_normalized")),
            results_read_as,
        ),
    )
    return {
        "content": {
            CONTENT_TYPE_PICK_KEY: {
                "recommended_content_type": recommended_content_type,
                "recommendation_reason": recommendation_reason,
            }
        }
    }


def content_type(state: REXT) -> REXT:
    """The content-type gate: the formats, with the pick recommend_content_type
    made, and the user's choice. A run paused here before the pick was kept in
    the state resumes with no pick, which only the answer's replay reads."""
    pick = (state.get("content") or {}).get(CONTENT_TYPE_PICK_KEY) or {}
    search_intent, candidate_content_types, _query = _gate_inputs(state)

    # show the intent and ask the user to select the content type
    selected_content_type = interrupt(
        {
            "instruction": "Select a content type",
            "search_intent": search_intent,
            # The intent's own types first, then the article types any keyword can become.
            "content_types": offered_content_types(candidate_content_types),
            # Additive fields — existing "content_types" list is unchanged so current
            # frontend handling keeps working; UI can optionally highlight this pick.
            "recommended_content_type": pick.get("recommended_content_type"),
            "recommendation_reason": pick.get("recommendation_reason"),
            # What the SERP shows: its dominant format, the People-Also-Ask
            # count and the AI Overview flag (None when the run has no SERP).
            "serp_evidence": build_serp_evidence(state.get("serp_normalized")),
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

    content_type_selected = final_selection or "article"
    logger.info(f"Content type selected: {content_type_selected}")

    update: dict = {"content": {"content_type": content_type_selected}}
    intent = intent_of_choice(content_type_selected, search_intent)
    if intent != search_intent.strip().lower():
        # Written into the run as the keyword step writes an intent the customer picked
        # there: the titles and the outline read it from here.
        logger.info(
            "Content type %s is not one of %s intent: the run goes on as %s",
            content_type_selected,
            search_intent,
            intent,
        )
        seo_result = state.get("seo_result") or {}
        update["seo_result"] = {
            "intent_type": intent,
            "serp_backlinks": {**(seo_result.get("serp_backlinks") or {}), "main_intent": intent},
        }
    return update
