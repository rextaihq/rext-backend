"""
Server-side events for product analytics (rext-control task 712): who an event may
name, what it may carry, and how one is sent without holding up the work it reports.

What the backend knows happened (an account was made, a workspace created, credits
spent, a run started or ended) goes to PostHog once the work is committed. The
request itself is ``money_events.send_server_event``, the one sender. This module is
what stands in front of it for an event about a person:

- Who: an event carries the account's id only when the person's stored answer on
  usage analytics allows it (``allows_identity``). Otherwise it is anonymous.
- What: only the events and properties listed here (``EVENT_PROPERTIES``, the list
  on the task), and of those only numbers, booleans and short words. Never an
  email, a name, a keyword, a title, any text a person typed or the app generated,
  an error's message or a token: a property that isn't on the list is left out,
  whatever it holds.
- Whose: an event of the team's own account (an admin's, or one on the company's own
  domain) says ``internal: true``, the mark the team's browsers send, so the charts
  can leave both out. The boolean alone: never the address or a part of it.
- How: ``report_event`` reads the person's standing in a session of its own, so a
  failed read can't touch the caller's transaction, and never raises;
  ``send_soon`` starts it without waiting.
"""

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Coroutine, Dict, FrozenSet, Optional, Set

from sqlalchemy import case, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.subscriptions import (
    SubscriptionStatus,
    UserSubscription,
    subscription_grants_access,
)
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.services import money_events
from src.utils import loop_registry
from src.utils.logger import logger
from src.utils.loop_bridge import on_worker_thread
from src.utils.rbac_utils import ADMIN_HIERARCHY_THRESHOLD

GRANTED = "granted"
DENIED = "denied"
REGION_OTHER = "other"

# The longest a send may take, the read before it included: the sender's own limit and
# a little for the read.
REPORT_TIMEOUT_SECONDS = money_events.SEND_TIMEOUT_SECONDS + 2.0

# On every event about a person, as their subscription has them at that moment.
PLAN_PROPERTIES: FrozenSet[str] = frozenset({"plan", "plan_status", "billing_period"})

# The server-side events and each one's own properties (rext-control#712). An event
# that isn't here isn't sent; a property that isn't here is left out.
EVENT_PROPERTIES: Dict[str, FrozenSet[str]] = {
    "user_signed_up": frozenset({"method"}),
    "workspace_created": frozenset({"first_workspace"}),
    "credits_spent": frozenset({"action", "credits", "balance_after"}),
    "credits_low": frozenset({"balance", "threshold"}),
    "credits_out": frozenset({"action"}),
    "content_generation_started": frozenset({"from_library", "country"}),
    "content_generation_completed": frozenset(
        {"content_type", "word_count", "seconds", "writing_seconds", "repairs"}
    ),
    "content_generation_failed": frozenset({"stage", "reason", "seconds", "writing_seconds"}),
}

# A property's text is a word from a fixed list (an action, a plan, a country code):
# no spaces, nothing that could be an address, and short. The list of names above is
# the safeguard; this keeps a sentence out of a listed property.
_WORD = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def allows_identity(answer: Optional[str], region: Optional[str]) -> bool:
    """
    Whether an event may carry the account's id.

    Granted: yes. Denied: no. No answer yet: only outside the EEA, where usage
    analytics is on until refused. A region that isn't known counts as the EEA.
    """
    if answer == GRANTED:
        return True
    if answer == DENIED:
        return False
    return region == REGION_OTHER


def internal_domains() -> FrozenSet[str]:
    """The company's own email domains (``ANALYTICS_INTERNAL_DOMAINS``, comma-separated)."""
    listed = os.getenv("ANALYTICS_INTERNAL_DOMAINS", "revnix.com")
    return frozenset(
        domain.strip().lower().lstrip("@") for domain in listed.split(",") if domain.strip()
    )


def on_internal_domain(email: Optional[str]) -> bool:
    """Whether the address is on one of the company's own domains (not a subdomain of one)."""
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[1].strip().lower() in internal_domains()


def _value(member: Any) -> Any:
    return getattr(member, "value", member)


def plan_properties(subscription: Optional[UserSubscription]) -> Dict[str, Any]:
    """
    ``plan``, ``plan_status`` and ``billing_period`` as the subscription has them now.

    Empty without a subscription. The plan's name is read only when the plan is
    loaded already: nothing is queried from here.
    """
    if subscription is None:
        return {}
    properties: Dict[str, Any] = {}
    plan = subscription.__dict__.get("plan")
    if plan is not None and plan.name:
        properties["plan"] = plan.name
    if subscription.status is not None:
        properties["plan_status"] = _value(subscription.status)
    if subscription.billing_period is not None:
        properties["billing_period"] = _value(subscription.billing_period)
    return properties


@dataclass(frozen=True)
class EventContext:
    """What an event says about its person: whether it may name them, their plan, and
    whether the account is the team's own."""

    identified: bool = False
    plan: Dict[str, Any] = field(default_factory=dict)
    internal: bool = False


async def read_event_context(db: AsyncSession, user_id: Any) -> EventContext:
    """One person's standing for an event, in two reads on the given session."""
    # An admin's or a super admin's account: a system role, held outside any workspace.
    # A customer's roles (owner, admin of their own workspace) are below that level.
    is_admin = exists().where(
        UserRole.user_id == Users.id,
        UserRole.workspace_id.is_(None),
        UserRole.role_id == Role.id,
        Role.hierarchy_level >= ADMIN_HIERARCHY_THRESHOLD,
    )
    answer = (
        await db.execute(
            select(
                Users.analytics_consent,
                Users.analytics_region,
                Users.email,
                is_admin.label("is_admin"),
            ).where(Users.id == user_id)
        )
    ).first()
    # The subscription the person is on now, as SubscriptionService.get_subscription_by_user
    # picks it (an active one first, then the newest that still grants access).
    active_first = case((UserSubscription.status == SubscriptionStatus.ACTIVE, 1), else_=0)
    subscription = (
        await db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(UserSubscription.user_id == user_id, subscription_grants_access())
            .order_by(active_first.desc(), UserSubscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    identified = answer is not None and allows_identity(
        answer.analytics_consent, answer.analytics_region
    )
    internal = answer is not None and (bool(answer.is_admin) or on_internal_domain(answer.email))
    return EventContext(
        identified=identified, plan=plan_properties(subscription), internal=internal
    )


async def event_context(user_id: Any) -> EventContext:
    """
    One person's standing for an event, read in a session of its own: a read that
    fails can't leave the caller's transaction aborted. Never raises: without it an
    event is anonymous and says nothing of a plan.
    """
    try:
        async with get_async_db_context() as db:
            return await read_event_context(db, user_id)
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        logger.warning("Server event context not read", extra={"error": type(error).__name__})
        return EventContext()


def sendable(name: str, properties: Dict[str, Any]) -> Dict[str, Any]:
    """
    The properties this event may carry: the listed ones, as numbers, booleans or
    short words. Anything else is left out, and its name (never its value) logged.
    """
    allowed = EVENT_PROPERTIES.get(name, frozenset()) | PLAN_PROPERTIES
    kept: Dict[str, Any] = {}
    dropped = []
    for key, value in properties.items():
        if value is None:
            continue
        simple = isinstance(value, (bool, int, float)) or (
            isinstance(value, str) and bool(_WORD.match(value))
        )
        if key in allowed and simple:
            kept[key] = value
        else:
            dropped.append(key)
    if dropped:
        logger.warning(
            "Server event properties left out",
            extra={"event": name, "properties": sorted(dropped)},
        )
    return kept


async def report_event(
    name: str,
    properties: Optional[Dict[str, Any]] = None,
    *,
    key: str,
    occurred_at: datetime,
    user_id: Optional[Any] = None,
    workspace_id: Optional[Any] = None,
    context: Optional[EventContext] = None,
) -> bool:
    """
    Send one listed event about a person. True when PostHog took it; never raises,
    and takes ``REPORT_TIMEOUT_SECONDS`` at most.

    Args:
        name: The event's name, one of ``EVENT_PROPERTIES``.
        properties: Its own properties, from the same list.
        key: What makes this event this one (a row's id, a run's thread id). The
            event's own id is made from the name and the key.
        occurred_at: When it happened, read once where it happened. PostHog keeps one
            of two events only when their id and their time are both the same, so a
            retry must send the time it sent before, not the moment of the retry.
        user_id: The account. Its id is sent only when its stored answer allows it.
        workspace_id: The workspace, where there is one. Sent only with the account's
            id: an anonymous event names no workspace either.
        context: The person's standing, for a caller that has read it already (code
            on a sync session, with ``allows_identity`` and ``plan_properties``);
            read here otherwise.
    """
    if name not in EVENT_PROPERTIES:
        logger.warning("Server event not on the list", extra={"event": name})
        return False
    if not os.getenv("POSTHOG_PROJECT_KEY"):
        return False
    try:
        return await asyncio.wait_for(
            _report(name, properties or {}, key, occurred_at, user_id, workspace_id, context),
            timeout=REPORT_TIMEOUT_SECONDS,
        )
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        logger.warning(
            "Server event not sent",
            extra={"event": name, "error": type(error).__name__},
        )
        return False


async def _report(
    name: str,
    properties: Dict[str, Any],
    key: str,
    occurred_at: datetime,
    user_id: Optional[Any],
    workspace_id: Optional[Any],
    context: Optional[EventContext],
) -> bool:
    if context is None:
        context = await event_context(user_id) if user_id is not None else EventContext()
    sent = sendable(name, {**context.plan, **properties})
    person_id = str(user_id) if context.identified and user_id is not None else None
    # A workspace's id is as steady as an account's: on an anonymous event it would tie
    # one person's events together, and to a named member's. Only a named event has it.
    if workspace_id is not None and person_id is not None:
        sent["workspace_id"] = str(workspace_id)
    # The team's own account, named or not: the mark names nobody. Left out for everyone
    # else, as the browser leaves it out.
    if context.internal:
        sent["internal"] = True
    return await money_events.send_server_event(
        name, sent, key=key, person_id=person_id, occurred_at=occurred_at
    )


# Sends started by send_soon on the running loop: a task nobody holds can be collected
# before it ends.
_in_flight: Set["asyncio.Task[Any]"] = set()


def send_soon(sending: Coroutine[Any, Any, Any]) -> None:
    """
    Start a send and don't wait for it. Never raises.

    For a caller that must not be held up by analytics (a charge inside a run, a
    graph node). The send runs on the server's own loop when the caller is on
    another one: a node's loop can end before a request does, and the database
    pool belongs to the server's. With no loop of the server's to run on (none at all, or
    a run's own loop before the server's is registered), nothing is sent.
    """
    try:
        main_loop = loop_registry.get()
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if main_loop is not None and main_loop is not running and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(sending, main_loop)
        elif running is not None and (running is main_loop or not on_worker_thread()):
            task = running.create_task(sending)
            _in_flight.add(task)
            task.add_done_callback(_in_flight.discard)
        else:
            # No loop of the server's to send on: none at all, or a run's own loop on one of
            # the runtime's job threads before the main loop is registered. It is dropped, never sent
            # from there: its read of the person would use the pool from another loop
            # (rext-control#858).
            sending.close()
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        sending.close()
        logger.warning("Server event not started", extra={"error": type(error).__name__})
