"""A run started from the keyword Library (E17, rext-control#368).

The Library holds what an earlier analysis found for a keyword (the keyword
step stores it in the LangGraph store under ``("library", <user>,
<workspace>)``; see keyword_recomendation.py): the metrics, the intent, the
recommendations and a summary of the SERP's top ten. A Library start names one
of those items by its store key; this node loads it into the run's state the
way the keyword step would have left it. The keyword gate is not asked again.

The analysis also keeps the search results the later steps read (the SERP's
results, questions, related topics, intent signals and competitors) beside the
item, under ``("library_research", <user>, <workspace>)`` and the same key: the
dashboard downloads every Library item's value, so they are not in the item.
A start within ``LIBRARY_RESEARCH_FRESH_FOR`` of the analysis restores them and
goes straight to its charges, without reading the search results again or
paying for them twice; an older start, or an item analysed before they were
kept, takes a fresh SERP first (founder, 2026-10-07, E24 rext-control#496).

A start that names no item, or one that is not in the caller's Library (free
text typed into ``?library=``), ends here with a message, and so does an item
whose keyword is longer than any title can be: nothing is charged for either.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

LIBRARY_ITEM_MISSING = "library_item_not_found"
LIBRARY_START_UNPAID = "insufficient_credits"
LIBRARY_ITEM_MESSAGE = (
    "This keyword isn't in your Library. Search for it to research it, "
    "then start the article from there."
)

# How long an analysis's search results stand in for a fresh SERP (founder,
# 2026-10-07): a keyword's top ten rarely moves much within a week.
LIBRARY_RESEARCH_FRESH_FOR = timedelta(days=7)

# What the SERP step leaves in serp_normalized that a later step reads (content
# type, titles, keyword groups, outline, drafting); the rest is not kept.
_RESEARCH_SERP_KEYS = (
    "query",
    "normalize_results",
    "related_topics",
    "questions",
    "features",
    "intent_matched_signals",
)


def library_research_namespace(user_id: Any, workspace_id: Any) -> tuple:
    """Where an analysis's search results are kept, beside its Library item."""
    return ("library_research", str(user_id), str(workspace_id))


def research_snapshot(state: REXT, analysed_at: str) -> Dict[str, Any]:
    """The search results a later step reads, as the SERP step left them in the run."""
    serp_normalized = state.get("serp_normalized") or {}
    return {
        "analysed_at": analysed_at,
        "serp_normalized": {
            key: serp_normalized[key] for key in _RESEARCH_SERP_KEYS if key in serp_normalized
        },
        "competitors": list(state.get("competitors") or []),
        "final_intent_type": state.get("final_intent_type"),
        "related_searches": list((state.get("serp_result") or {}).get("related_searches") or []),
    }


def _analysed_at(value: Any) -> Optional[datetime]:
    try:
        when = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


async def _fresh_research(store, owner: str, workspace_id: str, key: str) -> Optional[dict]:
    """The item's kept search results, when they are recent enough to stand in for a SERP."""
    try:
        found = await store.aget(library_research_namespace(owner, workspace_id), str(key))
    except Exception as exc:  # noqa: BLE001 - unreadable research means a fresh SERP
        logger.warning("A Library item's research could not be read: %s", type(exc).__name__)
        return None
    research = found.value if found else None
    if not research or not (research.get("serp_normalized") or {}).get("normalize_results"):
        return None
    analysed_at = _analysed_at(research.get("analysed_at"))
    if analysed_at is None:
        return None
    age = datetime.now(timezone.utc) - analysed_at
    if age < timedelta(0) or age > LIBRARY_RESEARCH_FRESH_FOR:
        return None
    return research


def _say_research(step: str, analysed_at: Optional[str]) -> None:
    """Tells the start screen whether the run reuses the analysis or reads the results again."""
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()({"type": "library", "step": step, "analysed_at": analysed_at})
    except Exception as exc:  # noqa: BLE001 - reporting never breaks the flow
        logger.warning("library research stream emit failed: %s", type(exc).__name__)


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
    state: REXT,
    error_code: str = LIBRARY_ITEM_MISSING,
    message: str = LIBRARY_ITEM_MESSAGE,
    *,
    stage: str | None = None,
    reason: str | None = None,
) -> Dict[str, Any]:
    """End the start with a message for the person. For the counts it is a refusal at the
    analysis unless the caller says otherwise."""
    from src.services.generation_events import ANALYSIS, REFUSED, announce_failed

    announce_failed(state, stage=stage or ANALYSIS, reason=reason or REFUSED)
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
    unreadable = False
    if key and owner and workspace_id and runtime is not None and runtime.store is not None:
        try:
            found = await runtime.store.aget(("library", owner, workspace_id), str(key))
            item = found.value if found else None
        except Exception as exc:  # noqa: BLE001 - an unreadable item is refused like a missing one
            # The key embeds the searched keyword (or whatever was typed): never logged.
            logger.warning("A Library item could not be read: %s", type(exc).__name__)
            unreadable = True

    if not item or not item.get("original_query"):
        logger.info("Library start refused: the named item is not in this user's Library")
        if unreadable:
            # The person reads the same message; in the counts a store that could not be read
            # is ours, not theirs.
            from src.services.generation_events import INTERNAL

            return _refused(state, reason=INTERNAL)
        return _refused(state)

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
        # The same refusal as a typed keyword's at the title step, counted at the same stage.
        from src.services.generation_events import TITLES

        return _refused(state, TOPICS_FAILED_CODE, KEYWORD_TOO_LONG_MESSAGE, stage=TITLES)

    # The research is for one market: its country, stored with items made since
    # E17; an older item takes the start's.
    country = item.get("country") or serp_payload.get("country")
    seo_state = item.get("seo_state") or {}
    intent = [i for i in (seo_state.get("intent") or []) if i]
    main_intent = intent[0] if intent else "informational"

    # Charged after this (charge_library_start): straight away when the
    # analysis's search results are fresh, else once a fresh SERP has results,
    # as the keyword analysis is, so a start whose search finds nothing costs nothing.
    await _announce_start(owner, workspace_id, query)
    from src.services.generation_events import announce_started

    announce_started(state, country=country)

    research = await _fresh_research(runtime.store, owner, workspace_id, str(key))
    if research:
        _say_research("library.research_reused", research["analysed_at"])
    else:
        _say_research("library.research_refreshed", item.get("timestamp"))

    update: Dict[str, Any] = {
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
                # Set when the start reuses the analysis's search results.
                "research_reused_at": research["analysed_at"] if research else None,
            },
        },
    }
    if research:
        # What the SERP step would have left (serp_engine), from the analysis.
        update["serp_normalized"] = research["serp_normalized"]
        update["competitors"] = research.get("competitors") or []
        update["final_intent_type"] = research.get("final_intent_type")
        update["serp_result"] = {
            "related_searches": research.get("related_searches") or [],
            "serp_status": "ok",
        }
        if research.get("final_intent_type"):
            update["seo_result"]["intent_type"] = research["final_intent_type"]
    return update


def research_reused(state: REXT) -> bool:
    """Whether this start reuses its analysis's search results (load_library_item)."""
    keyword_recs = (state.get("seo_result") or {}).get("keyword_recommendations") or {}
    return bool(keyword_recs.get("research_reused_at"))


async def charge_library_start(state: REXT) -> Dict[str, Any]:
    """A Library start's charges: the steps it runs again, before the content steps.

    The title step always (titles are written again), through the same charge
    point as the keyword analysis. The SERP stage only when the start read the
    search results again: then after that SERP, as in the analysis, so a search
    that finds nothing ends at no_serp_data uncharged. A start that reuses the
    analysis's results doesn't pay for them twice (founder, 2026-10-07, E24).
    """
    from src.flow.engines.seo.fetch_dataforseo_backlinks import charge_serp_seo
    from src.flow.engines.seo.keyword_recomendation import charge_title_generation

    serp_payload = state.get("serp_payload") or {}
    # The start's balance check (library_router) reserves nothing, so either
    # charge can still be refused; the run then ends there, before any paid
    # content step, rather than at a later credit gate.
    serp_paid = research_reused(state) or await charge_serp_seo(
        serp_payload.get("user_id"), serp_payload.get("workspace_id")
    )
    charged = serp_paid and await charge_title_generation(serp_payload)
    if not charged:
        logger.info("Library start ended: a charge was refused for want of credits")
        from src.services.generation_events import ANALYSIS, REFUSED, TITLES, announce_failed

        # Counted here, where it is known which charge it was: the search's is the
        # analysis's, the other the titles'. The run's end (insufficient_credits) says no more.
        announce_failed(state, stage=TITLES if serp_paid else ANALYSIS, reason=REFUSED)
        return {"content": {"error_code": LIBRARY_START_UNPAID}}
    return {}


def library_charge_router(state: REXT) -> str:
    """After the charges: the content steps, or the insufficient-credits end."""
    unpaid = (state.get("content") or {}).get("error_code") == LIBRARY_START_UNPAID
    return "insufficient_credits" if unpaid else "content_engine"


def library_item_router(state: REXT) -> str:
    """After loading: the end for a refused item; the charges for one whose
    analysis is fresh; a fresh SERP for any other.

    The load either refuses with an error code or clears it, so any code left
    in content is this start's refusal.
    """
    if (state.get("content") or {}).get("error_code"):
        return "end"
    return "charge_library_start" if research_reused(state) else "serp_engine"
