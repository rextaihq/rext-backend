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
text typed into ``?library=``), ends here with a message, and so does an item
whose keyword is longer than any title can be: nothing is charged for either.
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


def _refused(
    error_code: str = LIBRARY_ITEM_MISSING, message: str = LIBRARY_ITEM_MESSAGE
) -> Dict[str, Any]:
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(
            {
                "type": "run",
                "step": "run.failed",
                "error_code": error_code,
                "message": message,
            }
        )
    except Exception as exc:  # noqa: BLE001 - reporting never breaks the flow
        logger.warning("library item refusal stream emit failed: %s", exc)
    return {"content": {"error": message, "error_code": error_code}}


async def _announce_start(owner: str, workspace_id: str, query: str) -> None:
    """The "generation started" notification, sent once the item has loaded."""
    try:
        from uuid import UUID

        from src.services.notification_helper import notify_now

        await notify_now(
            user_id=UUID(owner),
            pref_flag="gen_started",
            message=f'Generating content for "{query}".',
            payload={"query": query},
            workspace_id=UUID(workspace_id),
        )
    except Exception as exc:  # noqa: BLE001 - a notification never breaks the run
        logger.warning("Library start notification failed: %s", type(exc).__name__)


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
            # The key embeds the searched keyword (or whatever was typed): never logged.
            logger.warning("A Library item could not be read: %s", type(exc).__name__)

    if not item or not item.get("original_query"):
        logger.info("Library start refused: the named item is not in this user's Library")
        return _refused()

    query = item["original_query"]

    # No title can contain a keyword this long, so the topic step would end the
    # run anyway: end it before the SERP and the charges, with the same message.
    from src.flow.engines.content.generation.seo_title_rules import keyphrase_fits_a_title

    if not keyphrase_fits_a_title(query):
        from src.flow.engines.content.generation.topic_generation import (
            KEYWORD_TOO_LONG_MESSAGE,
            TOPICS_FAILED_CODE,
        )

        logger.info("Library start refused: the item's keyword is longer than a title can be")
        return _refused(TOPICS_FAILED_CODE, KEYWORD_TOO_LONG_MESSAGE)

    # The research is for one market: its country, stored with items made since
    # E17; an older item takes the start's.
    country = item.get("country") or serp_payload.get("country")
    seo_state = item.get("seo_state") or {}
    intent = [i for i in (seo_state.get("intent") or []) if i]
    main_intent = intent[0] if intent else "informational"

    # A Library start costs what any article costs (coordinator, founder-delegated,
    # rext-control#368): the SERP stage, which it runs again, and the title step,
    # through the same charge points as the keyword analysis.
    from src.flow.engines.seo.fetch_dataforseo_backlinks import charge_serp_seo
    from src.flow.engines.seo.keyword_recomendation import charge_title_generation

    await charge_serp_seo(serp_payload.get("user_id"), serp_payload.get("workspace_id"))
    await charge_title_generation(serp_payload)
    await _announce_start(owner, workspace_id, query)

    return {
        # The stored keyword and market, not whatever the start carried.
        "serp_payload": {"query": query, "country": country},
        # A refusal earlier on this thread doesn't end this start.
        "content": {"error": None, "error_code": None},
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
                "selected_country": country,
                "recommendations": item.get("recommendations") or [],
                "error": None,
                "is_changed": False,
                "library_key": str(key),
            },
        },
    }


def library_item_router(state: REXT) -> str:
    """After loading: a fresh SERP for a found item, the end for a refused one.

    The load either refuses with an error code or clears it, so any code left
    in content is this start's refusal.
    """
    refused = bool((state.get("content") or {}).get("error_code"))
    return "end" if refused else "serp_engine"
