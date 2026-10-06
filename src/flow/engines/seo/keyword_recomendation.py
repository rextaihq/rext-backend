import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.types import interrupt

from src.flow.engines.content.generation.seo_title_rules import keyphrase_fits_a_title
from src.flow.engines.serp.normalization import has_organic_results
from src.flow.engines.serp.serp_evidence import build_serp_titles
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


async def charge_title_generation(serp_payload: dict) -> bool:
    """The title step's charge, taken when the keyword is kept.

    The one place it is charged: the keyword gate's answer that keeps the
    keyword, and a start from the keyword Library (library_item.py), whose
    keyword is kept by starting from it. False, with the credits.exhausted event
    emitted, when the balance can't cover it.
    """
    from src.utils.credit_manager import (
        STAGE_CREDITS,
        InsufficientCreditsError,
        _emit_credit_event,
        consume_stage_credits,
    )

    try:
        await consume_stage_credits(
            serp_payload.get("user_id"),
            STAGE_CREDITS["title_generation"],
            "title_generation",
            workspace_id=serp_payload.get("workspace_id"),
        )
    except InsufficientCreditsError as e:
        _emit_credit_event(e.available, e.stage, e.required, step="credits.exhausted")
        return False
    return True


# The Library key of the research save_keyword_research stored for this pass,
# kept in seo_result for the gate. The store write used to sit in the gate's own
# node, and LangGraph runs a node again from its start when the user's answer
# resumes it, so every kept keyword was saved to the Library twice
# (rext-control#330). None when this pass saved nothing: the gate is skipped.
KEYWORD_RESEARCH_KEY = "keyword_research_key"


def _keyword_gate_inputs(state: REXT) -> dict:
    """What the keyword gate shows, read from the state (no call, no write)."""
    serp_normalized = state.get("serp_normalized")
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})

    recommendations = serp_normalized.get("related_topics", []) if serp_normalized else []

    # 🔍 REINFORCEMENT: Use both API intent and Competitor consensus
    main_intent = serp_backlinks.get("main_intent", "informational").lower()
    recomended_intent = seo_result.get("intent_type", "informational").lower()
    if main_intent == "unknown":
        main_intent = recomended_intent

    # The volume is sent only with volume_status "ok"; otherwise it is None and
    # the status says why. Runs started before the status existed carry only
    # the number.
    volume_status = serp_backlinks.get("volume_status") or (
        "ok" if serp_backlinks.get("search_volume") is not None else "lookup_failed"
    )

    serp_payload = state.get("serp_payload")
    original_query = serp_payload.get("query", "") if serp_payload else ""
    keyword_clusters = seo_result.get("keyword_clusters", [])

    # Fallback: if no recommendations, derive them from top keyword clusters
    display_recommendations = list(recommendations)
    if not display_recommendations and keyword_clusters:
        seen = set()
        for cluster in keyword_clusters:
            for kw in cluster.get("keywords", []):
                word = kw.get("keyword", "").strip()
                if word and word.lower() != original_query.lower() and word not in seen:
                    display_recommendations.append(word)
                    seen.add(word)
                    if len(display_recommendations) >= 10:
                        break
            if len(display_recommendations) >= 10:
                break

    # Final fallback: ensure UI always has at least the original query
    if not display_recommendations and original_query:
        display_recommendations = [original_query]

    return {
        "serp_normalized": serp_normalized,
        "seo_result": seo_result,
        "serp_backlinks": serp_backlinks,
        "serp_payload": serp_payload,
        "recommendations": recommendations,
        "display_recommendations": display_recommendations,
        "keyword_clusters": keyword_clusters,
        "main_intent": main_intent,
        "original_query": original_query,
        "original_country": (serp_payload.get("country") or "") if serp_payload else "",
        "seo_state": {
            "keyword_difficulty": serp_backlinks.get("keyword_difficulty", 0),
            "intent": [main_intent, recomended_intent],
            "volume": serp_backlinks.get("search_volume") if volume_status == "ok" else None,
            "volume_status": volume_status,
            "backlinks": serp_backlinks.get("backlinks", 0),
            "referring_domains": serp_backlinks.get("referring_domains", 0),
        },
    }


async def save_keyword_research(state: REXT, config, *, runtime) -> Any:
    """
    The keyword gate's write, made once before the gate opens: this pass's
    research saved to the user's keyword Library, with a unique key per run to
    keep its history.
    """
    inputs = _keyword_gate_inputs(state)
    seo_result = inputs["seo_result"]
    serp_normalized = inputs["serp_normalized"]

    logger.info(f"recommendations: {inputs['recommendations']}")
    logger.info(f"competitors: {state.get('competitors', [])}")
    logger.info(f"seo_result: {seo_result}")
    logger.info(f"serp_backlinks: {inputs['serp_backlinks']}")

    serp_payload = inputs["serp_payload"]
    store = runtime.store
    user_id = serp_payload.get("user_id") if serp_payload else None
    workspace_id = serp_payload.get("workspace_id") if serp_payload else None

    print(f"   user_id: {user_id}")
    print(f"   workspace_id: {workspace_id}")

    if not user_id or not workspace_id:
        print("❌ Missing user_id or workspace_id")
        return {"seo_result": {KEYWORD_RESEARCH_KEY: None}}

    # Structured namespace for privacy and better search via prefix
    namespace = ("library", str(user_id), str(workspace_id))
    print(f"   namespace: {namespace}")

    original_query = inputs["original_query"]

    print(f"   original_query: {original_query}")
    print(f"   recommendations: {inputs['recommendations']}")

    # No organic results: the search engine has none for this keyword, or the
    # SERP lookup failed. The main graph already ends such a run before this
    # engine; should one get here anyway, it still ends (keyword_router sends
    # it to no_serp_data) instead of going on without a keyword gate.
    if not has_organic_results(state):
        serp_status = (state.get("serp_result") or {}).get("serp_status")
        if serp_status != "no_results":
            serp_status = "lookup_failed"
        logger.info(f"No SERP results ({serp_status}); ending the run")
        return {
            "seo_result": {
                **seo_result,
                KEYWORD_RESEARCH_KEY: None,
                "keyword_recommendations": {
                    "original_title": "",
                    "recommendations": [],
                    "patterns_found": {},
                    "seo_context": {},
                    "top_keywords_used": [],
                    "total_competitors_analyzed": 0,
                    "error": "No SERP data available",
                    "serp_status": serp_status,
                },
            }
        }

    # ✅ CREATE UNIQUE KEY FOR EACH RUN
    # Use timestamp + query to create unique keys
    timestamp = datetime.now(timezone.utc).isoformat()
    unique_key = f"library_{original_query}_{timestamp}"

    # Store the data
    try:
        # Enrich data with organic results and questions for better recommendation context
        top_organic = []
        if serp_normalized and serp_normalized.get("normalize_results"):
            # Store top 10 results with essential info
            for res in serp_normalized.get("normalize_results", [])[:10]:
                top_organic.append(
                    {
                        "title": res.get("title"),
                        "url": res.get("url"),
                        "snippet": res.get("snippet"),
                        "position": res.get("position"),
                    }
                )

        data_to_store = {
            "original_query": original_query,
            # The market the research is for: a Library start restores it.
            "country": inputs["original_country"],
            "recommendations": inputs["recommendations"],
            "questions": serp_normalized.get("questions", []) if serp_normalized else [],
            "related_topics": serp_normalized.get("related_topics", []) if serp_normalized else [],
            "top_organic_results": top_organic,
            "seo_state": inputs["seo_state"],
            "timestamp": timestamp,  # Include timestamp in value
        }

        # Store with unique key (keeps history)
        await store.aput(
            namespace=namespace,
            key=unique_key,
            value=data_to_store,
        )
        print(f"✅ Stored with unique key: {unique_key}")

    except Exception as e:
        logger.exception(f"Store error: {e}")
        print(f"❌ Store error: {e}")
        return {"seo_result": {KEYWORD_RESEARCH_KEY: None}}

    return {"seo_result": {KEYWORD_RESEARCH_KEY: unique_key}}


def keyword_research_router(state: REXT) -> str:
    """After the Library write: the keyword gate, or the end when nothing was saved."""
    saved = (state.get("seo_result") or {}).get(KEYWORD_RESEARCH_KEY)
    return "keyword_recommendation" if saved else "end"


async def keyword_recommendation(state: REXT) -> Any:
    """
    The keyword gate: Google-like keyword recommendations and the user's
    choice. It makes no call and no write, so the answer that resumes it
    repeats nothing; the title step's charge is taken here, once, on the answer
    that keeps the keyword.
    """
    inputs = _keyword_gate_inputs(state)
    seo_result = inputs["seo_result"]
    serp_backlinks = inputs["serp_backlinks"]
    serp_payload = inputs["serp_payload"]
    main_intent = inputs["main_intent"]
    original_query = inputs["original_query"]
    original_country = inputs["original_country"]
    display_recommendations = inputs["display_recommendations"]

    user_selection = interrupt(
        {
            "instruction": "Select a keyword for your content",
            "type": "keyword Selection",
            "Primary Keyword": original_query,
            "Country": original_country,
            "Recommendations": display_recommendations,
            "Keyword Clusters": inputs["keyword_clusters"],
            "seo_state": inputs["seo_state"],
            # The SERP's top ten, for the side pane beside the keyword card, as the
            # title gate sends them (empty when the run has no SERP).
            "serp_titles": build_serp_titles(inputs["serp_normalized"]),
        }
    )

    # Extract primary keyword
    primary_keyword = (
        user_selection.strip()
        if isinstance(user_selection, str)
        else user_selection.get("Primary Keyword", "").strip()
        if isinstance(user_selection, dict)
        else original_query
    )

    # Extract user-selected intent from dropdown (falls back to consensus)
    selected_intent = (
        user_selection.get("intent", "").strip() if isinstance(user_selection, dict) else ""
    )
    if not selected_intent or selected_intent == "unknown":
        selected_intent = main_intent

    # The analysis is scoped to keyword + country: a change in either one means
    # everything derived from the previous pair (SERP, competitors, metrics,
    # recommendations) is stale and the analysis has to run again.
    selected_country = (
        (user_selection.get("country") or "").strip() if isinstance(user_selection, dict) else ""
    ) or original_country
    keyword_changed = primary_keyword.lower() != original_query.lower()
    country_changed = selected_country.lower() != original_country.lower()
    is_changed = keyword_changed or country_changed

    logger.info(
        f"Selected Keyword: {primary_keyword} Country: {selected_country} "
        f"Selected Intent: {selected_intent} (changed={is_changed})"
    )

    # Deduct title_generation credit once user confirms keyword and proceeds. A
    # changed keyword or country goes back to the analysis (keyword_router), which
    # bills its own SERP pass and asks again; topics are generated, and charged,
    # only after the answer that keeps the keyword. A keyword longer than any
    # title can be gets no titles (the topic step ends the run and says so),
    # so it is not charged for them.
    if not is_changed and not keyphrase_fits_a_title(primary_keyword):
        logger.info("Kept keyword is longer than a title can be: titles not charged")
    elif not is_changed:
        await charge_title_generation(serp_payload or {})

    return {
        "seo_result": {
            **seo_result,
            "intent_type": selected_intent,
            "serp_backlinks": {**serp_backlinks, "main_intent": selected_intent},
            # Clusters are derived from the SERP of the analysed keyword/country;
            # drop them on re-analysis so they can never feed the next pass.
            **({"keyword_clusters": []} if is_changed else {}),
            "keyword_recommendations": {
                "original_title": original_query,
                "selected_keyword": primary_keyword,
                "selected_country": selected_country,
                "recommendations": display_recommendations,
                "error": None,
                "is_changed": is_changed,
                "library_key": seo_result.get(KEYWORD_RESEARCH_KEY),
            },
        },
        "serp_payload": {
            **(serp_payload or {}),
            "query": primary_keyword,
            "country": selected_country,
        },
    }
