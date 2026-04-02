# import logging
# from typing import Dict, Any, List, Optional
# from src.flow.states.rext import REXT
# from src.flow.model.structure.topics import SEOTopics
# from src.flow.model.llm_manager import topic_generation_model
# from langgraph.types import interrupt
# from langchain_core.messages import SystemMessage, HumanMessage
# from datetime import datetime, timezone

# logger = logging.getLogger(__name__)

# _REGENERATE_ACTIONS = {"regenerate_topics", "regenerate", "regen"}


# def _is_regenerate_request(response: Any) -> bool:
#     """Return True if the user's interrupt response is a regeneration request."""
#     if isinstance(response, dict):
#         # Explicit action key
#         action = (response.get("action") or "").strip().lower()
#         if action in _REGENERATE_ACTIONS:
#             return True
#         # Legacy boolean flag
#         if response.get("regenerate_topics"):
#             return True
#     if isinstance(response, str) and response.strip().lower() in _REGENERATE_ACTIONS:
#         return True
#     return False


# def _resolve_selection(response: Any, topics: List[str]) -> Optional[str]:
#     """
#     Resolve the user's interrupt response to a selected topic string.

#     Accepts:
#     - int  : 1-based index into topics
#     - str  : direct topic text, or a numeric string treated as 1-based index
#     - dict : looks for keys  selected_topic | topic | index
    
#     Returns None if the response cannot be resolved to a valid topic.
#     """
#     if isinstance(response, int):
#         if 1 <= response <= len(topics):
#             return topics[response - 1]
#         return topics[0] if topics else None

#     if isinstance(response, str):
#         stripped = response.strip()
#         if stripped.isdigit():
#             idx = int(stripped)
#             if 1 <= idx <= len(topics):
#                 return topics[idx - 1]
#         return stripped if stripped else None

#     if isinstance(response, dict):
#         # dict may carry action + selection together
#         # e.g. {"action": "select", "selected_topic": "..."}
#         # or   {"action": "select", "index": 2}
#         topic_val = (
#             response.get("selected_topic")
#             or response.get("topic")
#         )
#         if topic_val:
#             return str(topic_val).strip() or None

#         index_val = response.get("index")
#         if index_val is not None:
#             try:
#                 idx = int(index_val)
#                 if 1 <= idx <= len(topics):
#                     return topics[idx - 1]
#             except (ValueError, TypeError):
#                 pass

#     return None


# async def topic_generation(state: REXT) -> Dict[str, Any]:
#     """
#     Generate SEO topics based on the user's query.

#     Flow
#     ----
#     1. Generate 5 SEO topics using the LLM.
#     2. Interrupt to show topics to the user.
#        • If the user requests regeneration (and limit not reached): regenerate and
#          interrupt again with the fresh list.
#        • If the user selects a topic (by index, text, or dict): exit the loop.
#     3. Return the generated topic list and the selected topic.

#     Interrupt payload shape
#     -----------------------
#     {
#         "type": "topic_selection",
#         "instruction": "Select a topic or choose to regenerate",
#         "topics": ["topic1", ...],          # always 5 items
#         "allow_regenerate": true,           # false when limit reached
#         "regeneration_count": 0,
#         "max_regenerations": 3,
#     }

#     Expected response shapes (any of):
#     - {"action": "regenerate"}
#     - {"action": "select", "index": 2}          # 1-based
#     - {"action": "select", "selected_topic": "..."}
#     - "Some topic text"
#     - 3  (integer, 1-based index)
#     """
#     logger.info("Starting topic generation")

#     # ── Resolve query ─────────────────────────────────────────────────────────
#     normalized_result = state.get("serp_normalized", {})

#     if normalized_result and normalized_result.get("error"):
#         logger.warning(
#             "Skipping topic generation due to upstream error: %s",
#             normalized_result["error"],
#         )
#         return {"content": {"topics": [], "selected_topic": ""}}

#     query = normalized_result.get("query")
#     if not query:
#         serp_payload = state.get("serp_payload", {})
#         query = serp_payload.get("query", "")

#     if not query:
#         logger.warning("No query found in serp_normalized or serp_payload")
#         return {"content": {"topics": [], "selected_topic": ""}}

#     # ── Build model ───────────────────────────────────────────────────────────
#     model = topic_generation_model().with_structured_output(SEOTopics)
#     current_year = datetime.now(timezone.utc).year

#     messages = [
#         SystemMessage(
#             content=(
#                 f"You are a SEO expert. Generate a high quality list of 5 topics related to the given topic. "
#                 f"Focus on topics that rank well in search engines, provide value to readers, and are relevant in {current_year}. "
#                 f"Prefer trends, latest strategies, and current best practices."
#             )
#         ),
#         HumanMessage(content=f"Generate 5 topics for: {query} in {current_year}"),
#     ]

#     # ── Initial generation ────────────────────────────────────────────────────
#     results: SEOTopics = await model.ainvoke(messages)
#     topics: List[str] = results.topics
#     logger.info("Generated %d topics", len(topics))

#     max_regenerations = 3
#     regeneration_count = 0

#     # ── Interrupt loop ────────────────────────────────────────────────────────
#     while True:
#         user_response = interrupt(
#             {
#                 "type": "topic_selection",
#                 "instruction": "Select a topic or choose to regenerate",
#                 "topics": topics,
#                 "allow_regenerate": regeneration_count < max_regenerations,
#                 "regeneration_count": regeneration_count,
#                 "max_regenerations": max_regenerations,
#             }
#         )

#         # ── Branch: regenerate ─────────────────────────────────────────────
#         if _is_regenerate_request(user_response):
#             if regeneration_count > max_regenerations:
#                 logger.warning(
#                     "Regeneration limit (%d) reached; ignoring regenerate request",
#                     max_regenerations,
#                 )
#                 # Fall through to selection resolution below
#             else:
#                 regeneration_count += 1
#                 results = await model.ainvoke(messages)
#                 topics = results.topics
#                 logger.info(
#                     "Regenerated topics (attempt %d/%d): %d topics",
#                     regeneration_count,
#                     max_regenerations,
#                     len(topics),
#                 )
#                 continue  # re-interrupt with fresh topics

#         # ── Branch: select ─────────────────────────────────────────────────
#         selected_topic = _resolve_selection(user_response, topics)

#         if not selected_topic:
#             # Absolute fallback — should rarely be reached
#             selected_topic = topics[0] if topics else ""
#             logger.warning(
#                 "Could not resolve topic selection from response %r; defaulting to first topic",
#                 user_response,
#             )

#         logger.info("User selected topic: %s", selected_topic)
#         break

#     return {
#         "content": {
#             "topics": topics,
#             "selected_topic": selected_topic,
#         }
#     }

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
        if response.strip().lower() in _REGENERATE_ACTIONS:
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
