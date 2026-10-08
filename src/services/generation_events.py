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
import time
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

# The supported markets ISO_TO_COUNTRY has no code for (it lists the ones the search provider
# is asked for by code): their ISO 3166-1 codes, so every market a run can have is counted.
_MORE_CODES = {
    "American Samoa": "AS", "Andorra": "AD", "Angola": "AO", "Antigua and Barbuda": "AG",
    "Armenia": "AM", "Aruba": "AW", "Bahamas": "BS", "Barbados": "BB", "Benin": "BJ",
    "Bermuda": "BM", "Bhutan": "BT", "Burkina Faso": "BF", "Burundi": "BI", "Cape Verde": "CV",
    "Central African Republic": "CF", "Chad": "TD", "Comoros": "KM",
    "Republic of the Congo": "CG", "Democratic Republic of the Congo": "CD",
    "Cook Islands": "CK", "Ivory Coast": "CI", "Cuba": "CU", "Curaçao": "CW", "Djibouti": "DJ",
    "Dominica": "DM", "Equatorial Guinea": "GQ", "Eritrea": "ER", "Eswatini": "SZ", "Fiji": "FJ",
    "Gabon": "GA", "Gambia": "GM", "Gibraltar": "GI", "Greenland": "GL", "Grenada": "GD",
    "Guadeloupe": "GP", "Guam": "GU", "Guinea": "GN", "Guinea-Bissau": "GW", "Kiribati": "KI",
    "Lesotho": "LS", "Liberia": "LR", "Liechtenstein": "LI", "Marshall Islands": "MH",
    "Micronesia": "FM", "Monaco": "MC", "Montserrat": "MS", "Nauru": "NR",
    "New Caledonia": "NC", "Niue": "NU", "North Macedonia": "MK", "Palau": "PW",
    "Pitcairn Islands": "PN", "Réunion": "RE", "Saint Barthélemy": "BL", "Saint Helena": "SH",
    "Saint Kitts and Nevis": "KN", "Saint Lucia": "LC", "Saint Martin": "MF",
    "Saint Pierre and Miquelon": "PM", "Saint Vincent and the Grenadines": "VC", "Samoa": "WS",
    "San Marino": "SM", "São Tomé and Príncipe": "ST", "Seychelles": "SC", "Sint Maarten": "SX",
    "Solomon Islands": "SB", "Suriname": "SR", "Timor-Leste": "TL", "Tokelau": "TK",
    "Tonga": "TO", "Turks and Caicos Islands": "TC", "Tuvalu": "TV", "Vanuatu": "VU",
    "Wallis and Futuna": "WF",
}  # fmt: skip
_CODE_OF_COUNTRY = {
    **{name.lower(): code for name, code in _MORE_CODES.items()},
    **{name.lower(): code.upper() for code, name in ISO_TO_COUNTRY.items()},
}
_CODES = set(_CODE_OF_COUNTRY.values())


def country_code(country: Any) -> Optional[str]:
    """The two-letter code of a run's country, which arrives as a code or as its name.
    None for "Global" and for anything that is not a supported market: a code is sent only
    when it is one of the list's own, never what a client typed."""
    text = str(country or "").strip()
    if len(text) == 2 and text.upper() in _CODES:
        return text.upper()
    return _CODE_OF_COUNTRY.get(text.lower())


def offered_content_type(content_type: Any) -> Optional[str]:
    """The article's type as its canonical key, or None when it is not one the product offers.

    The content-type step takes its answer as sent, so a changed client can put any short
    text there, and a short word is what the sender lets through: only the keys the outline
    models are registered under ever leave as ``content_type``."""
    from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL, normalize_content_type

    key = normalize_content_type(str(content_type or "")) if content_type else ""
    return key if key in CONTENT_TYPE_TO_MODEL else None


# When each run's outline was approved, by thread, kept in this process only. The article is
# written in the one invocation that follows the approval, so the seconds from it to the save
# need no place in the run's state. A run another process takes up after a restart has no
# entry here, and its event goes without them.
_WRITING_BEGAN: dict[str, float] = {}
_MOST_RUNS_WRITING = 2000


def _clock() -> float:
    """Seconds on a clock that only goes forward (a deploy or a time sync never moves it)."""
    return time.monotonic()


def writing_began(thread_id: Optional[str] = None) -> None:
    """The outline was approved and the article's writing starts: called by the outline gate."""
    thread = thread_id or _thread_id()
    if not thread:
        return
    _WRITING_BEGAN.pop(thread, None)
    _WRITING_BEGAN[thread] = _clock()
    while len(_WRITING_BEGAN) > _MOST_RUNS_WRITING:
        del _WRITING_BEGAN[next(iter(_WRITING_BEGAN))]


def _writing_seconds(thread_id: Optional[str]) -> Optional[int]:
    """Whole seconds since the outline's approval, or None when this process did not see it.
    The entry is taken out: the run ends with the event that asks."""
    began = _WRITING_BEGAN.pop(thread_id or _thread_id() or "", None)
    return None if began is None else max(0, round(_clock() - began))


def _aware(moment: Optional[datetime]) -> Optional[datetime]:
    return moment.replace(tzinfo=timezone.utc) if moment and moment.tzinfo is None else moment


def completion_time(
    state: Any,
    *,
    created_at: Optional[datetime],
    saved_before: Optional[datetime],
    saved_after: Optional[datetime],
) -> Optional[datetime]:
    """When this run's article was saved: the same moment for a save that runs twice, so the
    event's key and time do not move on a replay.

    * The row is this run's own (made after the run began): its creation time.
    * The row is an earlier run's (a thread started again): the time this run first saved
      into it. A replayed save finds that time on the row before it saves again
      (``saved_before``, at or after the run's start); the first save has only the time it
      leaves on the row (``saved_after``).

    None when the run has no start mark or the row no times: the caller's own clock then.
    """
    started = run_started_at(state)
    created_at, saved_before, saved_after = map(_aware, (created_at, saved_before, saved_after))
    if started is None or created_at is None or created_at >= started:
        return created_at
    if saved_before is not None and saved_before >= started:
        return saved_before
    return saved_after if saved_after is not None and saved_after >= started else None


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


def events_are_sent() -> bool:
    """Whether this server sends analytics events at all (the project's key is set)."""
    return bool(os.getenv("POSTHOG_PROJECT_KEY"))


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
        if not events_are_sent():
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
    started = run_started_at(state)
    if saved_at is not None and saved_at.tzinfo is None:
        saved_at = saved_at.replace(tzinfo=timezone.utc)
    if saved_at is not None and started is not None and saved_at < started:
        # A thread started again saves into the row it already has: that row's time is the
        # earlier run's. This run's article was saved now.
        saved_at = None
    ended = saved_at or datetime.now(timezone.utc)
    review = ((state or {}).get("content") or {}).get("review") or {}
    repairs = review.get("repair_attempts")
    _announce(
        COMPLETED,
        {
            "content_type": offered_content_type(content_type),
            "word_count": int(word_count),
            "seconds": _seconds(started, ended),
            # From the outline's approval to the save: the server's own time writing it.
            "writing_seconds": _writing_seconds(thread_id),
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
            # An article that failed: from the outline's approval to its end.
            "writing_seconds": _writing_seconds(thread_id) if stage == ARTICLE else None,
        },
        state,
        thread_id=thread_id,
    )
