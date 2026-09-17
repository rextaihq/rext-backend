import json
import logging
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def persist_content(state: REXT, config: RunnableConfig) -> dict:
    """Auto-save the finished article to the Content library as a draft.

    Runs as the final node so a generation the user backgrounded (or never
    watched) still lands in the library without a manual Save. Idempotent by
    langgraph_thread_id — re-runs update the same row instead of duplicating.
    Any failure is logged and swallowed so persistence never breaks the run.
    """
    content_state = state.get("content") or {}
    final = content_state.get("final_content") or {}
    # The user-selected title is the single source of truth for what is saved.
    # final_content.title should already equal it (every mutating node re-locks
    # it), but persistence is the last write, so it reads the selection itself.
    title = content_state.get("selected_topic") or final.get("title")
    body_markdown = final.get("body_markdown")
    if not (title and body_markdown):
        logger.warning("persist_content: missing title/body; skipping save")
        return {}

    serp = state.get("serp_payload") or {}
    user_id = serp.get("user_id")
    workspace_id = serp.get("workspace_id")
    thread_id = (config.get("configurable") or {}).get("thread_id")
    if not (user_id and workspace_id and thread_id):
        logger.warning("persist_content: missing user/workspace/thread; skipping save")
        return {}

    try:
        workspace_uuid = UUID(str(workspace_id))
        user_uuid = UUID(str(user_id))
        thread_uuid = UUID(str(thread_id))
    except (TypeError, ValueError):
        logger.warning("persist_content: non-UUID user/workspace/thread; skipping save")
        return {}

    review = content_state.get("review") or {}
    on_page = (
        review.get("on_page_metrics") if isinstance(review.get("on_page_metrics"), dict) else {}
    )
    readability = (
        review.get("readability_metrics")
        if isinstance(review.get("readability_metrics"), dict)
        else {}
    )
    trust = review.get("trust_score") if isinstance(review.get("trust_score"), dict) else {}

    from src.api.database.async_database import get_pooled_langgraph_db_context
    from src.api.schema.content_schema import ContentCreate, ContentSEODataSchema

    # The pinned user query wins over anything on the payload. The previous
    # order put `primary_keyword` first, which is a model-written field, so a
    # model-invented phrase could still be persisted as the focus keyphrase even
    # after generate_content had corrected `focus_keyphrase` itself.
    from src.flow.engines.content.generation.focus_keyword import resolve_focus_keyword
    from src.services.content_service import ContentService
    from src.utils.loop_bridge import run_on_main_loop

    focus_keyphrase = (
        resolve_focus_keyword(state)
        or final.get("focus_keyphrase")
        or final.get("primary_keyword")
        or serp.get("query")
        or ""
    )

    seo_data = ContentSEODataSchema(
        meta_title=title,
        meta_description=final.get("meta_description") or "",
        focus_keyphrase=focus_keyphrase,
        # Measured deterministically by the quality gate / on-page scoring
        # (keyword_density.py). The column already existed and was never
        # populated, so the UI had no density to show.
        keyphrase_density=_as_float(final.get("keyphrase_density")),
        secondary_keywords=final.get("secondary_keywords") or [],
        seo_score=_as_float(on_page.get("seo_health_score")),
        readability_score=_as_float(
            readability.get("flesch_reading_ease") or readability.get("score")
        ),
        trust_score=_as_float(trust.get("score")),
        seo_details=json.dumps(on_page, default=str) if on_page else None,
    )

    category_val = final.get("category")
    if isinstance(category_val, list):
        category_val = ", ".join(str(c) for c in category_val if c)
    elif category_val:
        category_val = str(category_val)
    else:
        category_val = None

    payload = ContentCreate(
        title=title,
        status="draft",
        content_language="English",
        introduction=final.get("introduction") or final.get("meta_description") or "",
        body_markdown=body_markdown,
        body_html=final.get("body_html") or final.get("html_content") or "",
        tags=final.get("tags") or [],
        category=category_val,
        seo_data=seo_data,
        langgraph_thread_id=thread_uuid,
    )

    try:

        async def _persist():
            async with get_pooled_langgraph_db_context() as db:
                service = ContentService(db)
                return await service.create_content(workspace_uuid, user_uuid, payload)

        content = await run_on_main_loop(_persist())
        logger.info("persist_content: saved article %s for thread %s", content.id, thread_id)
    except Exception:
        logger.exception("persist_content: failed to save generated article")

    return {}
