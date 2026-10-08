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

import os
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select

from src.api.cache.redis_client import cache
from src.api.database.async_database import get_async_db_context
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.server_events import report_event
from src.utils.logger import logger

SIGNUP_METHODS = ("credentials", "google", "github", "invitation")

# An account that is out of credits stays "out" until a charge goes through again:
# the runs refused meanwhile are one crossing, not one each. Kept in Redis for as
# long as a billing period and a few days.
_OUT_MARK_SECONDS = 40 * 24 * 60 * 60


def configured() -> bool:
    """Whether analytics is switched on here (the project's key is set)."""
    return bool(os.getenv("POSTHOG_PROJECT_KEY"))


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
            key=str(user_id),
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
            # Every workspace the account ever made, the deleted ones too: a second
            # workspace after the first was deleted is not a first.
            made = (
                await db.execute(
                    select(func.count())
                    .select_from(WorkspaceModel)
                    .where(WorkspaceModel.user_id == user_id)
                )
            ).scalar_one()
        await report_event(
            "workspace_created",
            {"first_workspace": made <= 1},
            key=str(workspace_id),
            occurred_at=occurred_at,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        _failed("workspace_created", error)


def _out_mark(owner_id: UUID) -> str:
    return f"analytics:credits_out:{owner_id}"


async def _owner_of(user_id: UUID, workspace_id: Optional[UUID]) -> UUID:
    """Whose credits a run in this workspace spends: the workspace's owner."""
    # credit_manager calls this module, so it is imported here and not at the top.
    from src.utils.credit_manager import resolve_credit_owner_id

    async with get_async_db_context() as db:
        return await resolve_credit_owner_id(db, user_id, workspace_id)


async def credits_charged(
    user_id: UUID,
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

    The events are about the account whose credits were spent (the workspace's
    owner), which is whose plan and whose answer on analytics they carry. A charge
    has no id of its own, so each event's key is made here, once: nothing sends a
    charge's event twice.
    """
    if not configured():
        return
    try:
        owner_id = await _owner_of(user_id, workspace_id)
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
            await cache.set(_out_mark(owner_id), 1, ttl=_OUT_MARK_SECONDS)
            await report_event("credits_out", {"action": action}, key=uuid.uuid4().hex, **about)
        else:
            # Credits again (a reset, a new plan, an admin's addition) and a charge went
            # through: the next time it runs out is a new crossing.
            await cache.delete(_out_mark(owner_id))
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        _failed("credits_spent", error)


async def credits_refused(
    user_id: UUID, workspace_id: Optional[UUID], *, action: str, occurred_at: datetime
) -> None:
    """
    A run was refused for lack of credits: ``credits_out``, once per crossing.

    The charge that emptied the balance has said it already (``credits_charged``),
    and so has an earlier refusal: the account is marked out until a charge goes
    through again. Without Redis the mark can't be kept and every refusal is sent.
    """
    if not configured():
        return
    try:
        owner_id = await _owner_of(user_id, workspace_id)
        if await cache.get(_out_mark(owner_id)) is not None:
            return
        await cache.set(_out_mark(owner_id), 1, ttl=_OUT_MARK_SECONDS)
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
