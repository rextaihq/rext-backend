"""
The writing pipeline's events for product analytics (rext-control task 712).

Three things no browser can vouch for: a run was accepted, an article was saved, a run
ended without one. Each is sent once from here, after the fact it reports, through the
server's one sender (server_events.py), so the counts are the pipeline's own:

* ``content_generation_started``: from the Library or a typed keyword, and the country.
* ``content_generation_completed``: the type, the words, the seconds since the run
  began (the person's time at the four steps included) and the repair passes.
* ``content_generation_failed``: the stage it ended in and a class of reason.

Never a keyword, a title, an outline or any text, and never an error's message: the
sender lets through only the properties on its list, as numbers, booleans and short
words, and nothing here hands it more. A send is started and not waited for
(``send_soon``): no run is held up by analytics, and none fails for it. Nothing is
sent, and nothing is read, without POSTHOG_PROJECT_KEY (staging and the tests have none).

What the server cannot see is not sent from here: a run the person cancels, and one
the runtime stops (a crash, its own time limit), end outside the graph's code.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from src.flow.states.countries import ISO_TO_COUNTRY
from src.services.server_events import report_event, send_soon

logger = logging.getLogger(__name__)

STARTED = "content_generation_started"
COMPLETED = "content_generation_completed"
FAILED = "content_generation_failed"

# Where a run ended, as the dashboard's steps name them.
ANALYSIS = "analysis"
TITLES = "titles"
OUTLINE = "outline"
ARTICLE = "article"

# Why, as a class. "cancelled" and "timeout" are on the list of names and are not sent
# from here (see the module's last paragraph).
REFUSED = "refused"
PROVIDER = "provider"
INTERNAL = "internal"

# Under the run's `content`: when the run began, set by the graph's first node.
RUN_STARTED_AT = "run_started_at"

_CODE_OF_COUNTRY = {name.lower(): code.upper() for code, name in ISO_TO_COUNTRY.items()}


def country_code(country: Any) -> Optional[str]:
    """The two-letter code of a run's country, which arrives as a code or as its name.
    None for "Global" and for a name the list doesn't have."""
    text = str(country or "").strip()
    if len(text) == 2 and text.lower() in ISO_TO_COUNTRY:
        return text.upper()
    return _CODE_OF_COUNTRY.get(text.lower())


def run_start_mark() -> dict:
    """What the graph's first node writes into the run's content: when it began."""
    return {RUN_STARTED_AT: datetime.now(timezone.utc).isoformat()}


def run_started_at(state: Any) -> Optional[datetime]:
    """When this run began, or None for a run older than the mark."""
    raw = ((state or {}).get("content") or {}).get(RUN_STARTED_AT)
    try:
        started = datetime.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return started


def _seconds(started: Optional[datetime], ended: datetime) -> Optional[int]:
    if started is None:
        return None
    return max(0, round((ended - started).total_seconds()))


def _thread_id() -> Optional[str]:
    """The run's thread, for a caller the graph hands no config (a router, a terminal node)."""
    try:
        from langgraph.config import get_config

        return str((get_config().get("configurable") or {}).get("thread_id") or "") or None
    except Exception:  # noqa: BLE001 - outside a run there is none
        return None


def _uuid(value: Any) -> Optional[UUID]:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _announce(
    name: str,
    properties: dict,
    state: Any,
    *,
    thread_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
) -> None:
    """Start one event's send and return at once. Never raises."""
    try:
        if not os.getenv("POSTHOG_PROJECT_KEY"):
            return
        serp = (state or {}).get("serp_payload") or {}
        user_id = _uuid(serp.get("user_id") or (state or {}).get("user_id"))
        workspace_id = _uuid(serp.get("workspace_id") or (state or {}).get("workspace_id"))
        started = run_started_at(state)
        # A thread can be started again: the run is the thread and when this run began.
        run = thread_id or _thread_id() or str(user_id or "")
        key = f"{run}:{started.isoformat() if started else ''}"
        sent = {name_: value for name_, value in properties.items() if value is not None}
        # The person's standing (may the event name them, their plan) is the sender's to read,
        # on the server's own loop.
        send_soon(
            report_event(
                name,
                sent,
                key=key,
                occurred_at=occurred_at or datetime.now(timezone.utc),
                user_id=user_id,
                workspace_id=workspace_id,
            )
        )
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        logger.warning("Generation event %s not started: %s", name, type(error).__name__)


def announce_started(state: Any, *, country: Any = None) -> None:
    """A run was accepted: its credits cover it and, for a Library start, its item loaded.

    ``country`` is given by a Library start, whose item's own country replaces the one the
    run was started with."""
    serp = (state or {}).get("serp_payload") or {}
    _announce(
        STARTED,
        {
            "from_library": bool(serp.get("is_library")),
            "country": country_code(country if country is not None else serp.get("country")),
        },
        state,
        # The same moment for a node that runs twice, so the two are one event.
        occurred_at=run_started_at(state),
    )


def announce_completed(
    state: Any,
    *,
    thread_id: str,
    content_type: Optional[str],
    word_count: int,
    saved_at: Optional[datetime] = None,
) -> None:
    """The article is saved. ``saved_at`` is the saved row's own time when it has one: a
    save that runs twice (it is idempotent by thread) is then the same event."""
    ended = saved_at or datetime.now(timezone.utc)
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=timezone.utc)
    review = ((state or {}).get("content") or {}).get("review") or {}
    repairs = review.get("repair_attempts")
    _announce(
        COMPLETED,
        {
            "content_type": content_type,
            "word_count": int(word_count),
            "seconds": _seconds(run_started_at(state), ended),
            "repairs": repairs if isinstance(repairs, int) and not isinstance(repairs, bool) else 0,
        },
        state,
        thread_id=thread_id,
        occurred_at=ended if saved_at is not None else None,
    )


def announce_failed(
    state: Any, *, stage: str, reason: str, thread_id: Optional[str] = None
) -> None:
    """A run ended without an article, where the graph's own code sees it end."""
    _announce(
        FAILED,
        {
            "stage": stage,
            "reason": reason,
            "seconds": _seconds(run_started_at(state), datetime.now(timezone.utc)),
        },
        state,
        thread_id=thread_id,
    )
