import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from src.flow.model.llm_manager import topic_generation_model
from src.flow.model.structure.topics import SEOTopics
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

_REGENERATE_ACTIONS = {"regenerate_topics", "regenerate", "regen"}


def _is_regenerate_request(response: Any) -> bool:
    """Check if user explicitly asked to regenerate."""
    if isinstance(response, dict):
        action = (response.get("action") or "").strip().lower()
        if action in _REGENERATE_ACTIONS:
            return True
        if response.get("regenerate_topics"):
            return True

    if isinstance(response, str):
        val = response.strip().lower()
        # BEST PRACTICE: Flexible matching (e.g. "regenerate. add keywords")
        for action in _REGENERATE_ACTIONS:
            if val.startswith(action):
                return True

    return False


async def topic_generation(state: REXT) -> Dict[str, Any]:
    logger.info("Starting topic generation")

    # ── Resolve query ─────────────────────────────────────────────
    normalized_result = state.get("serp_normalized", {})

    if normalized_result and normalized_result.get("error"):
        logger.warning(
            "Skipping topic generation due to upstream error: %s",
            normalized_result["error"],
        )
        return {"content": {"topics": [], "selected_topic": ""}}

    query = normalized_result.get("query")

    if not query:
        serp_payload = state.get("serp_payload", {})
        query = serp_payload.get("query", "")

    if not query:
        logger.warning("No query found")
        return {"content": {"topics": [], "selected_topic": ""}}

    # ── Resolve intent and content type selected in prior interrupts ──
    serp_backlinks = state.get("seo_result", {}).get("serp_backlinks", {})
    selected_intent = serp_backlinks.get("main_intent", "informational")
    selected_content_type = state.get("content", {}).get("content_type", "article")

    # ── Build model ───────────────────────────────────────────────
    model = topic_generation_model().with_structured_output(SEOTopics)
    current_year = datetime.now(timezone.utc).year

    messages = [
        SystemMessage(
            content=(
                f"You are helping someone with ZERO SEO or content-marketing background choose "
                f"what to write next. They cannot judge ranking potential, competition, or search "
                f"trends themselves — that evaluation is entirely on you.\n\n"
                f"Generate 5 article topic ideas for {current_year} that fit the user's selected "
                f"search intent and content type. Titles should read like something a real person "
                f"would search for or want to click — not internal SEO jargon.\n\n"
                f"Then mark exactly ONE topic as recommended=True: the single safest, highest-value "
                f"pick for someone who can't evaluate these themselves. Prefer the topic that is "
                f"realistic to write well without specialist research, has clear reader demand, and "
                f"isn't already dominated by large competitors. For that one topic, fill "
                f"recommendation_reason with one short, plain-English sentence explaining why — no "
                f"SEO jargon ('SERP', 'intent', 'keyword density', 'ranking potential', etc.); if a "
                f"concept is unavoidable, explain it in plain words in the same sentence. All other "
                f"topics: recommended=False, recommendation_reason=null."
            )
        ),
        HumanMessage(
            content=(
                f"Generate 5 topics for: {query} in {current_year}\n"
                f"Search intent: {selected_intent}\n"
                f"Content type: {selected_content_type}"
            )
        ),
    ]

    def _extract_topics(parsed: SEOTopics) -> tuple[List[str], Optional[str], Optional[str]]:
        """Titles for the existing payload, plus the recommended title and its plain-language reason (if any)."""
        titles = [t.title for t in parsed.topics]
        recommended_pick = next((t for t in parsed.topics if t.recommended), None)
        recommended = recommended_pick.title if recommended_pick else None
        reason = recommended_pick.recommendation_reason if recommended_pick else None
        return titles, recommended, reason

    # ── Initial generation ────────────────────────────────────────
    results: SEOTopics = await model.ainvoke(messages)
    topics, recommended_topic, recommendation_reason = _extract_topics(results)

    logger.info("Generated %d topics (recommended=%s)", len(topics), recommended_topic)

    # ── Infinite loop until valid selection ───────────────────────
    while True:
        user_response = interrupt(
            {
                "type": "topic",
                "instruction": "Select a topic",
                "topics": topics,
                # Additive fields — existing "topics" list is unchanged so current
                # frontend handling keeps working; UI can optionally highlight this.
                "recommended_topic": recommended_topic,
                "recommendation_reason": recommendation_reason,
                "allow_regenerate": True,
            }
        )

        # ── Explicit regenerate ───────────────────────────────
        if _is_regenerate_request(user_response):
            logger.info("User requested regeneration")

            # Extract feedback from the response (Single Interrupt Flow)
            feedback = ""
            if isinstance(user_response, dict):
                feedback = user_response.get("feedback", "").strip()
            elif isinstance(user_response, str):
                # Try to extract feedback from string like "regenerate. add fascinating keyword"
                val = user_response.strip()
                for action in _REGENERATE_ACTIONS:
                    if val.lower().startswith(action):
                        # Extract the part after the regenerate command
                        feedback = val[len(action) :].strip()
                        # Clean up punctuation like "." or ":" at the start
                        feedback = feedback.lstrip(".: ").strip()
                        break

            # Check for skip keywords in string-based feedback
            if feedback.lower() in {"none", "skip", "no", "n/a", ""}:
                feedback = ""

            if feedback:
                logger.info(f"Adding user feedback to model prompt: {feedback}")
                messages.append(HumanMessage(content=f"User feedback for regeneration: {feedback}"))

            results = await model.ainvoke(messages)
            topics, recommended_topic, recommendation_reason = _extract_topics(results)
            continue

        # ── Extract topic ─────────────────────────────────────
        if isinstance(user_response, dict):
            selected_topic = (
                user_response.get("Selected Topic")
                or user_response.get("selected_topic")
                or user_response.get("topic")
                or ""
            )
        else:
            selected_topic = str(user_response)

        selected_topic = selected_topic.strip()

        # ── Auto regenerate if empty ──────────────────────────
        if not selected_topic:
            logger.warning("Empty input → regenerating topics")

            results = await model.ainvoke(messages)
            topics, recommended_topic, recommendation_reason = _extract_topics(results)
            continue

        # ✅ Valid topic → exit loop
        logger.info("User selected topic: %s", selected_topic)
        break

    return {
        "content": {
            "topics": topics,
            "recommended_topic": recommended_topic,
            "selected_topic": selected_topic,
        }
    }
