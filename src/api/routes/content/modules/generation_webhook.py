"""
LangGraph run webhook — the only place a generation run that crashed is seen.

The frontend creates generation runs with
``webhook="/api/v1/content/generation/run-finished"``, so the LangGraph server
POSTs every finished run back into this app. The body is not trusted: the run
is re-read from LangGraph in-process, and only a run that really ended in
error notifies, and only the user who started it — at most once per run.

Completed runs are notified by the persist_content node instead, which knows
whether an article was actually saved (a run paused for review also ends as
"success").
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.notification.notification_model import Notification
from src.services.notification_helper import notify_now
from src.utils.logger import logger

router = APIRouter()

_FAILED_STATUSES = {"error", "timeout"}


@router.post("/generation/run-finished", include_in_schema=False)
async def generation_run_finished(request: Request, db: AsyncSession = Depends(get_async_db)):
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}
    thread_id = body.get("thread_id") if isinstance(body, dict) else None
    run_id = body.get("run_id") if isinstance(body, dict) else None
    if not thread_id or not run_id:
        return {"ok": True}

    from langgraph_sdk import get_client

    client = get_client()
    try:
        run = await client.runs.get(str(thread_id), str(run_id))
        if run.get("status") not in _FAILED_STATUSES:
            return {"ok": True}
        state = await client.threads.get_state(str(thread_id))
    except Exception:
        logger.warning("generation webhook: could not verify run %s", run_id, exc_info=True)
        return {"ok": True}

    already_sent = await db.scalar(
        select(Notification.id)
        .where(
            Notification.category == "gen_failed",
            Notification.payload["run_id"].astext == str(run_id),
        )
        .limit(1)
    )
    if already_sent:
        return {"ok": True}

    values = state.get("values") or {}
    serp = values.get("serp_payload") or {}
    user_id = serp.get("user_id") or values.get("user_id")
    if not user_id:
        return {"ok": True}

    title = (values.get("content") or {}).get("selected_topic") or serp.get("query")
    await notify_now(
        user_id=user_id,
        pref_flag="gen_failed",
        message=(
            f'"{title}" failed to generate. Open it to try again.'
            if title
            else "Content generation failed. Open it to try again."
        ),
        payload={"thread_id": str(thread_id), "run_id": str(run_id)},
        workspace_id=serp.get("workspace_id") or values.get("workspace_id"),
    )
    return {"ok": True}
