import logging
from typing import Dict, Any
from src.flow.states.rext import REXT
from src.flow.model.structure.topics import SEOTopics
from src.flow.model.llm_manager import topic_generation_model
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime, timezone
logger = logging.getLogger(__name__) 


async def topic_generation(state: REXT) -> Dict[str, Any]:
    """
    Generate SEO topics based on the user's query.
    
    Flow:
    1. Generate 5 SEO topics using LLM
    2. Interrupt to show topics to user for selection
    3. Save selected topic to state
    
    Uses the LLM to generate 5 relevant SEO topics for content creation.
    """
    logger.info("Starting topic generation")

    # Get the normalized query from SERP results or fallback to input payload
    normalized_result = state.get("serp_normalized", {})
    
    # Check for upstream errors — skip processing if prior node failed
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
        logger.warning("No query found in serp_normalized")
        return {"content": {"topics": [], "selected_topic": ""}}

    # Load the model with structured output
    model = topic_generation_model().with_structured_output(SEOTopics)
    current_year = datetime.now(timezone.utc).year
    # Use a LIST of messages, not a SET
    messages = [
    SystemMessage(
        content=(
            f"You are a SEO expert. Generate a high quality list of 5 topics related to the given topic. "
            f"Focus on topics that rank well in search engines, provide value to readers, and are relevant in {current_year}. "
            f"Prefer trends, latest strategies, and current best practices."
        )
    ),
    HumanMessage(
        content=f"Generate 5 topics for: {query} in {current_year}"
    )
]
    
    results: SEOTopics = await model.ainvoke(messages)
    topics = results.topics

    logger.info(f"Generated {len(topics)} topics")

    max_regenerations = 3
    regeneration_count = 0

    while True:
        # ========================================
        # INTERRUPT FOR USER SELECTION
        # ========================================
        user_selection = interrupt(
            {
                "instruction": "Select a topic for your content (or regenerate topics)",
                "type": "topic",
                "topics": topics,
                # Optional hint for clients that support actions (backward compatible).
                "actions": [{"action": "regenerate_topics", "label": "Regenerate Topics"}],
            }
        )

        # If user explicitly requests regeneration, re-run generation and re-interrupt.
        if isinstance(user_selection, dict):
            action = (user_selection.get("action") or "").strip().lower()
            regenerate_requested = bool(user_selection.get("regenerate_topics")) or action in {
                "regenerate_topics",
                "regenerate",
                "regen",
            }
            if regenerate_requested and regeneration_count < max_regenerations:
                regeneration_count += 1
                results = await model.ainvoke(messages)
                topics = results.topics
                logger.info(
                    "Regenerated topics (attempt %s/%s): %s topics",
                    regeneration_count,
                    max_regenerations,
                    len(topics),
                )
                continue

        # Handle user selection (can be index, string, or dict)
        selected_topic = ""

        if isinstance(user_selection, int):
            # User selected by index (1-5)
            if 1 <= user_selection <= len(topics):
                selected_topic = topics[user_selection - 1]
            else:
                selected_topic = topics[0]  # Default to first topic
        elif isinstance(user_selection, str):
            # User typed the topic directly or selected from list
            selected_topic = user_selection.strip()
            # If they typed a number as string
            if selected_topic.isdigit():
                idx = int(selected_topic)
                if 1 <= idx <= len(topics):
                    selected_topic = topics[idx - 1]
        elif isinstance(user_selection, dict):
            # User returned a dict with selection
            selected_topic = user_selection.get("selected_topic", "") or user_selection.get("topic", "")

        # Fallback to first topic if selection is empty
        if not selected_topic:
            selected_topic = topics[0] if topics else ""

        logger.info(f"User selected topic: {selected_topic}")
        break
    
    return {
        "content": {
            "topics": topics,
            "selected_topic": selected_topic
        }
    }
