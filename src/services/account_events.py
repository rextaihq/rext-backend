"""
What an account does, told to product analytics (rext-control task 712): it was
made, it made a workspace, it spent credits, it ran low on them or out.

Each is sent with ``server_events.report_event`` once the work is committed, so an
event is never sent for work that was rolled back. None of them raises: a caller
hands one to a background task, or to ``server_events.send_soon``, and forgets it.
Each takes the time the thing happened from its caller, read once where it
happened.

The names and properties are the list on the task (``server_events.EVENT_PROPERTIES``).
Nothing else is sent: no email, no name, no workspace name or address.
"""

import hashlib
import os
import uuid
from datetime import datetime
from typing import Any, Callable, Coroutine, Optional
from uuid import UUID

from sqlalchemy import func, select

from src.api.cache.redis_client import cache
from src.api.database.async_database import get_async_db_context
from src.api.models.audit_models.audit_logs import AuditLog
from src.services.server_events import report_event, send_soon
from src.utils.logger import logger

SIGNUP_METHODS = ("credentials", "google", "github", "invitation")
# The audit action the workspace route records for a creation.
WORKSPACE_CREATED = "workspace.create"

# An account that is out of credits stays "out" until a charge goes through again:
# the runs refused meanwhile are one crossing, not one each. Kept in Redis for as
# long as a billing period and a few days.
_OUT_MARK_SECONDS = 40 * 24 * 60 * 60


def configured() -> bool:
    """Whether analytics is switched on here (the project's key is set)."""
    return bool(os.getenv("POSTHOG_PROJECT_KEY"))


async def start(event: Callable[..., Coroutine[Any, Any, None]], *args: Any) -> None:
    """
    For a route's background task: start one of the events below and don't wait for it.

    Background tasks run one after the other once the response is sent (so after the
    route's commit); an event awaited there would hold up the tasks queued behind it,
    the verification email among them.
    """
    send_soon(event(*args))


def _key(kind: str, thing: Any) -> str:
    """An event's key for a thing with an id: the same for the same thing, and not the
    id itself, since the sender names the key when it logs a send that failed."""
    return hashlib.sha256(f"{kind}:{thing}".encode()).hexdigest()[:32]


def _failed(name: str, error: Exception) -> None:
    logger.warning(
        "Account event not sent",
        extra={"event": name, "error": type(error).__name__},
    )


async def user_signed_up(user_id: UUID, method: Optional[str], occurred_at: datetime) -> None:
    """The account's row is committed. ``method``: how it was made (SIGNUP_METHODS)."""
    if not configured():
        return
    try:
        known = method.lower() if isinstance(method, str) else None
        await report_event(
            "user_signed_up",
            {"method": known if known in SIGNUP_METHODS else None},
            key=_key("user_signed_up", user_id),
            occurred_at=occurred_at,
            user_id=user_id,
        )
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        _failed("user_signed_up", error)


async def workspace_created(user_id: UUID, workspace_id: UUID, occurred_at: datetime) -> None:
    """The workspace's row is committed. Says whether it is the account's first."""
    if not configured():
        return
    try:
        async with get_async_db_context() as db:
            # Every workspace this account ever made, from the audit log's record of each
            # creation (written with it, and kept for a year): the workspaces it owns now
            # would miss one it deleted or handed over, and count one handed to it.
            made = (
                await db.execute(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.user_id == user_id, AuditLog.action == WORKSPACE_CREATED)
                )
            ).scalar_one()
        await report_event(
            "workspace_created",
            {"first_workspace": made <= 1},
            key=_key("workspace_created", workspace_id),
            occurred_at=occurred_at,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        _failed("workspace_created", error)


def _out_mark(owner_id: UUID) -> str:
    return f"analytics:credits_out:{owner_id}"


async def _claim_out(owner_id: UUID) -> bool:
    """Mark the account out of credits. True for the one caller that set the mark:
    of several runs refused at once, one tells it. Without Redis there is no mark to
    set, and every caller is told yes."""
    if not cache.is_enabled() or cache.redis is None:
        return True
    return bool(await cache.redis.set(_out_mark(owner_id), "1", nx=True, ex=_OUT_MARK_SECONDS))


async def _owner_of(user_id: UUID, workspace_id: Optional[UUID]) -> UUID:
    """Whose credits a run in this workspace spends: the workspace's owner."""
    # credit_manager calls this module, so it is imported here and not at the top.
    from src.utils.credit_manager import resolve_credit_owner_id

    async with get_async_db_context() as db:
        return await resolve_credit_owner_id(db, user_id, workspace_id)


async def credits_charged(
    owner_id: UUID,
    workspace_id: Optional[UUID],
    *,
    action: str,
    credits: int,
    balance_after: int,
    low_threshold: int,
    occurred_at: datetime,
) -> None:
    """
    A billed charge is committed: ``credits_spent``, and with it ``credits_low`` when
    this charge took the balance below ``low_threshold`` (one article's cost), or
    ``credits_out`` when it left nothing.

    ``owner_id`` is the account that was charged, as the charge itself resolved it
    (the workspace's owner): the events carry its plan and its answer on analytics,
    whoever owns the workspace by the time they are sent. A charge has no id of its
    own, so each event's key is made here, once: nothing sends a charge's event twice.
    """
    if not configured():
        return
    try:
        about = {"occurred_at": occurred_at, "user_id": owner_id, "workspace_id": workspace_id}
        await report_event(
            "credits_spent",
            {"action": action, "credits": credits, "balance_after": balance_after},
            key=uuid.uuid4().hex,
            **about,
        )
        if balance_after < low_threshold <= balance_after + credits:
            await report_event(
                "credits_low",
                {"balance": balance_after, "threshold": low_threshold},
                key=uuid.uuid4().hex,
                **about,
            )
        if balance_after <= 0:
            if await _claim_out(owner_id):
                await report_event("credits_out", {"action": action}, key=uuid.uuid4().hex, **about)
        else:
            # Credits again (a reset, a new plan, an admin's addition) and a charge went
            # through: the next time it runs out is a new crossing.
            await cache.delete(_out_mark(owner_id))
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        _failed("credits_spent", error)


async def credits_refused(
    user_id: UUID,
    workspace_id: Optional[UUID],
    *,
    action: str,
    occurred_at: datetime,
    owner_id: Optional[UUID] = None,
) -> None:
    """
    A run was refused for lack of credits: ``credits_out``, once per crossing.

    The charge that emptied the balance has said it already (``credits_charged``),
    and so has an earlier refusal: the account is marked out until a charge goes
    through again, and of several refusals at once only the one that set the mark
    tells it. ``owner_id`` is the account the refused charge resolved, when there was
    one; a run refused before it starts has none, and the owner is read here.
    """
    if not configured():
        return
    try:
        if owner_id is None:
            owner_id = await _owner_of(user_id, workspace_id)
        if not await _claim_out(owner_id):
            return
        await report_event(
            "credits_out",
            {"action": action},
            key=uuid.uuid4().hex,
            occurred_at=occurred_at,
            user_id=owner_id,
            workspace_id=workspace_id,
        )
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        _failed("credits_out", error)
