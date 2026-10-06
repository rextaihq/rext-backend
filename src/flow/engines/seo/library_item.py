"""A run started from the keyword Library (E17, rext-control#368).

The Library holds what an earlier analysis found for a keyword (the keyword
step stores it in the LangGraph store under ``("library", <user>,
<workspace>)``; see keyword_recomendation.py): the metrics, the intent, the
recommendations and a summary of the SERP's top ten. A Library start names one
of those items by its store key; this node loads it into the run's state the
way the keyword step would have left it, and the run then takes a fresh SERP
(the stored summary has no competitor analysis, which the outline needs)
before content type, titles and outline. The keyword gate is not asked again.

A start that names no item, or one that is not in the caller's Library (free
text typed into ``?library=``), ends here with a message.
"""

import logging
from typing import Any, Dict

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

LIBRARY_ITEM_MISSING = "library_item_not_found"
LIBRARY_ITEM_MESSAGE = (
    "This keyword isn't in your Library. Search for it to research it, "
    "then start the article from there."
)


def _owner(state: REXT, config) -> str:
    """The signed-in user, as LangGraph's auth handler identified them.

    Only an in-process run (tests, local tools) has no authenticated user, and
    falls back to the run's own payload.
    """
    configurable = (config or {}).get("configurable") or {}
    return str(
        configurable.get("langgraph_auth_user_id")
        or (state.get("serp_payload") or {}).get("user_id")
        or ""
    )


def _refused() -> Dict[str, Any]:
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(
            {
                "type": "run",
                "step": "run.failed",
                "error_code": LIBRARY_ITEM_MISSING,
                "message": LIBRARY_ITEM_MESSAGE,
            }
        )
    except Exception as exc:  # noqa: BLE001 - reporting never breaks the flow
        logger.warning("library item refusal stream emit failed: %s", exc)
    return {"content": {"error": LIBRARY_ITEM_MESSAGE, "error_code": LIBRARY_ITEM_MISSING}}


async def load_library_item(state: REXT, config, *, runtime) -> Dict[str, Any]:
    serp_payload = state.get("serp_payload") or {}
    key = serp_payload.get("library_key")
    owner = _owner(state, config)
    workspace_id = str(serp_payload.get("workspace_id") or "")

    item = None
    if key and owner and workspace_id and runtime is not None and runtime.store is not None:
        try:
            found = await runtime.store.aget(("library", owner, workspace_id), str(key))
            item = found.value if found else None
        except Exception as exc:  # noqa: BLE001 - an unreadable item is refused like a missing one
            logger.warning("Library item %r could not be read: %s", key, exc)

    if not item or not item.get("original_query"):
        logger.info("Library start refused: no item %r in this user's Library", key)
        return _refused()

    query = item["original_query"]
    seo_state = item.get("seo_state") or {}
    intent = [i for i in (seo_state.get("intent") or []) if i]
    main_intent = intent[0] if intent else "informational"

    return {
        # The stored keyword, not whatever text the start carried.
        "serp_payload": {"query": query},
        "seo_result": {
            "intent_type": intent[-1] if intent else main_intent,
            "serp_backlinks": {
                "keyword": query,
                "search_volume": seo_state.get("volume"),
                "volume_status": seo_state.get("volume_status"),
                "keyword_difficulty": seo_state.get("keyword_difficulty"),
                "backlinks": seo_state.get("backlinks"),
                "referring_domains": seo_state.get("referring_domains"),
                "main_intent": main_intent,
            },
            "keyword_recommendations": {
                "original_title": query,
                "selected_keyword": query,
                "selected_country": serp_payload.get("country"),
                "recommendations": item.get("recommendations") or [],
                "error": None,
                "is_changed": False,
                "library_key": str(key),
            },
        },
    }


def library_item_router(state: REXT) -> str:
    """After loading: a fresh SERP for a found item, the end for a refused one."""
    refused = (state.get("content") or {}).get("error_code") == LIBRARY_ITEM_MISSING
    return "end" if refused else "serp_engine"
