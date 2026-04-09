import logging
from typing import Dict, Any, List
from src.flow.states.rext import REXT
from src.flow.model.structure.topics import SEOTopics
from src.flow.model.llm_manager import topic_generation_model
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime, timezone

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

    # ── Build model ───────────────────────────────────────────────
    model = topic_generation_model().with_structured_output(SEOTopics)
    current_year = datetime.now(timezone.utc).year

    messages = [
        SystemMessage(
            content=(
                f"You are a SEO expert. Generate 5 high-quality topics for {current_year}. "
                f"Focus on trends, ranking potential, and user value."
            )
        ),
        HumanMessage(content=f"Generate 5 topics for: {query} in {current_year}"),
    ]

    # ── Initial generation ────────────────────────────────────────
    results: SEOTopics = await model.ainvoke(messages)
    topics: List[str] = results.topics

    logger.info("Generated %d topics", len(topics))

    # ── Infinite loop until valid selection ───────────────────────
    while True:
        user_response = interrupt(
            {
                "type": "topic_selection",
                "instruction": "Select a topic or type 'regenerate'",
                "topics": topics,
                "allow_regenerate": True,
            }
        )

        # ── Explicit regenerate ───────────────────────────────
        if _is_regenerate_request(user_response):
            logger.info("User requested regeneration")
            
         
            feedback = ""

            feedback_response = interrupt(
                {
                    "type": "topic_regeneration_feedback",
                    "instruction": "Optional: How can I improve the topics? (Type 'none' or leave empty to skip)",
                    "allow_skip": True,
                }
            )
            if isinstance(feedback_response, dict):
                feedback = feedback_response.get("feedback", "").strip()
            elif isinstance(feedback_response, str):
                feedback = feedback_response.strip()
            
            # Check for skip keywords
            if feedback.lower() in {"none", "skip", "no", "n/a", ""}:
                logger.info("No feedback provided for regeneration")
                feedback = ""
        
            if feedback:
                logger.info(f"Adding user feedback to model prompt: {feedback}")
                messages.append(HumanMessage(content=f"User feedback for regeneration: {feedback}"))

            results = await model.ainvoke(messages)
            topics = results.topics
            continue

        # ── Extract topic ─────────────────────────────────────
        if isinstance(user_response, dict):
            selected_topic = (
                user_response.get("selected_topic")
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
            topics = results.topics
            continue

        # ✅ Valid topic → exit loop
        logger.info("User selected topic: %s", selected_topic)
        break

    return {
        "content": {
            "topics": topics,
            "selected_topic": selected_topic,
        }
    }