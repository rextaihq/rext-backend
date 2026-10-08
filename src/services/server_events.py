"""
Server-side events for product analytics (rext-control task 712).

What the backend knows happened, sent to PostHog from here once the work is
committed: an account was made, a workspace created, credits spent, a run started
or ended. The dashboard sends its own events for what a person does on screen;
anything a decision or the revenue depends on is counted from these
(``source: "server"``).

Who: an event carries the account's id only when the person's stored answer on
usage analytics allows it (``allows_identity``). Otherwise it is anonymous: an id
of its own, and no person made for it.

What: names and numbers. Never an email, a name, a keyword, a title, any text a
person typed or the app generated, an error's message or a token. Callers pass the
properties listed on the task; ``send_server_event`` also drops any value that
isn't a number, a boolean or a short word, so a sentence can't leave by mistake.

Nothing is sent unless POSTHOG_PROJECT_KEY is set (the project's public key, the
one the dashboard uses; staging has none). A failure to send is logged and never
reaches the caller.
"""

import asyncio
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Coroutine, Dict, Optional, Set

import httpx
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.models.subscription_models.subscriptions import (
    SubscriptionStatus,
    UserSubscription,
    subscription_grants_access,
)
from src.api.models.user_models.users import Users
from src.utils import loop_registry
from src.utils.logger import logger

DEFAULT_HOST = "https://eu.i.posthog.com"
SEND_TIMEOUT_SECONDS = 3.0

GRANTED = "granted"
DENIED = "denied"
REGION_OTHER = "other"

# A property's text is a word from a fixed list (an action, a plan, a country code):
# no spaces, nothing that could be an address, and short.
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
    """What an event says about its person: whether it may name them, and their plan."""

    identified: bool = False
    plan: Dict[str, Any] = field(default_factory=dict)


async def event_context(db: AsyncSession, user_id: Any) -> EventContext:
    """
    One person's standing for an event, in two reads. Never raises: without it an
    event is anonymous and says nothing of a plan.

    For callers with an async session. Read it after the work's own commit, or
    before it and outside its transaction's fate: this must not fail the work.
    """
    try:
        answer = (
            await db.execute(
                select(Users.analytics_consent, Users.analytics_region).where(Users.id == user_id)
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
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        logger.warning(
            "Server event context not read",
            extra={"error": type(error).__name__},
        )
        return EventContext()
    identified = answer is not None and allows_identity(
        answer.analytics_consent, answer.analytics_region
    )
    return EventContext(identified=identified, plan=plan_properties(subscription))


def _sendable(properties: Dict[str, Any]) -> Dict[str, Any]:
    """Numbers, booleans and short words; anything else is left out, and its name logged."""
    kept: Dict[str, Any] = {}
    dropped = []
    for name, value in properties.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float)) or (isinstance(value, str) and _WORD.match(value)):
            kept[name] = value
        else:
            dropped.append(name)
    if dropped:
        logger.warning("Server event properties left out", extra={"properties": sorted(dropped)})
    return kept


def _event_uuid(name: str, key: str) -> str:
    """The same event for the same thing is the same event, however often it is sent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rext-server-event:{name}:{key}"))


async def send_server_event(
    name: str,
    properties: Optional[Dict[str, Any]] = None,
    *,
    key: str,
    user_id: Optional[Any] = None,
    workspace_id: Optional[Any] = None,
    identified: bool = False,
    plan: Optional[Dict[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """
    Send one event. True when PostHog took it; never raises, and waits on nothing
    but its one request (three seconds at most), so it can follow any commit.

    Args:
        name: The event's name, from the list on the task.
        properties: Its own properties: numbers, booleans and short words.
        key: What makes this event this one (a row's id, a run's thread id); the
            event's own id is derived from the name and the key, so a retry sends
            the same event again. PostHog keeps one of two that also agree on the
            time: pass ``occurred_at`` for an event that may be sent twice.
        user_id: The account. Sent as the distinct id only with ``identified``.
        workspace_id: The workspace, where there is one.
        identified: Whether the person's answer allows their id (``allows_identity``,
            or ``event_context(...).identified``).
        plan: ``plan_properties(...)`` or ``event_context(...).plan``.
        occurred_at: When it happened, if not now.
        client: An httpx client to send with; one is opened for the call otherwise.
    """
    project_key = os.getenv("POSTHOG_PROJECT_KEY")
    if not project_key:
        return False
    try:
        event_uuid = _event_uuid(name, key)
        sent = _sendable({**(plan or {}), **(properties or {})})
        if workspace_id is not None:
            sent["workspace_id"] = str(workspace_id)
        sent["surface"] = "app"
        sent["source"] = "server"
        sent["environment"] = os.getenv("ENVIRONMENT", "development").lower()
        if identified and user_id is not None:
            distinct_id = str(user_id)
        else:
            # No person is made or updated for it.
            distinct_id = event_uuid
            sent["$process_person_profile"] = False
        body: Dict[str, Any] = {
            "api_key": project_key,
            "event": name,
            "distinct_id": distinct_id,
            "uuid": event_uuid,
            "properties": sent,
        }
        if occurred_at is not None:
            body["timestamp"] = occurred_at.isoformat()
        host = (os.getenv("POSTHOG_HOST") or DEFAULT_HOST).rstrip("/")
        if client is not None:
            response = await client.post(f"{host}/i/v0/e/", json=body)
        else:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as own:
                response = await own.post(f"{host}/i/v0/e/", json=body)
        if response.status_code >= 400:
            logger.warning(
                "Server event not accepted",
                extra={"event": name, "status": response.status_code},
            )
            return False
        return True
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        logger.warning(
            "Server event not sent",
            extra={"event": name, "error": type(error).__name__},
        )
        return False


# Sends started by send_soon on the running loop: a task nobody holds can be collected
# before it ends.
_in_flight: Set["asyncio.Task[Any]"] = set()


def send_soon(sending: Coroutine[Any, Any, Any]) -> None:
    """
    Start a send and don't wait for it. Never raises.

    For a caller that must not be held up by analytics (a charge inside a run, a
    graph node). The send runs on the server's own loop when the caller is on
    another one: a node's loop can end before a request does, and the database
    pool belongs to the server's. With no loop at all, nothing is sent.
    """
    try:
        main_loop = loop_registry.get()
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if main_loop is not None and main_loop is not running and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(sending, main_loop)
        elif running is not None:
            task = running.create_task(sending)
            _in_flight.add(task)
            task.add_done_callback(_in_flight.discard)
        else:
            sending.close()
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        sending.close()
        logger.warning("Server event not started", extra={"error": type(error).__name__})
