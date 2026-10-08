"""
The incident banner: one notice for every signed-in user while a provider or our own servers fail.

A super admin switches it on and off without a deploy. Its state is one JSON value in Redis, which
every API instance shares, stored with the banner's own end time as its expiry: a banner always
ends (at most a day later), so one nobody switched off can't outlive its incident. There is no
banner when the key is absent, expired or unreadable, and when Redis itself can't be reached:
reading it never fails, it answers "none". Reading touches Redis only, never PostgreSQL, so the
banner can still be read when the database is what is failing.

Does NOT:
- Handle HTTP requests/responses (routes)
- Check authentication or permissions (the routes' dependencies do)
- Write the audit log (the routes do)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, get_args

from src.api.cache.redis_client import cache
from src.api.middleware.exceptions import RextExternalServiceException
from src.api.schema.incident_banner_schema import BannerArea
from src.utils.logger import logger

#: The one banner. A new one replaces it.
BANNER_KEY = "incident_banner:current"

#: The areas a banner may name; anything else read back from Redis is left out.
KNOWN_AREAS = frozenset(get_args(BannerArea))

NO_BANNER: Dict[str, Any] = {
    "active": False,
    "message": None,
    "areas": [],
    "started_at": None,
    "expires_at": None,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def read_banner(now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    The banner showing now, or NO_BANNER.

    Anything short of a well-formed, unexpired value is "none": the read is on every signed-in
    page, and a stored value somebody mangled must not show, or break, anything.
    """
    try:
        stored = await cache.get(BANNER_KEY)
    except Exception as error:  # the cache client catches its own; this is the last line
        logger.warning("Incident banner read failed", error=str(error))
        return dict(NO_BANNER)

    if not isinstance(stored, dict):
        return dict(NO_BANNER)
    message = stored.get("message")
    expires_at = _parse_time(stored.get("expires_at"))
    if not isinstance(message, str) or not message.strip() or expires_at is None:
        return dict(NO_BANNER)
    # Redis expires the key itself; this covers a clock that disagrees with it.
    if expires_at <= (now or _now()):
        return dict(NO_BANNER)

    # The routes answer with their own JSON, so the response model doesn't check this: only the
    # areas the schema knows go out, each once, whatever a stale or hand-edited value holds.
    areas = stored.get("areas")
    known = (
        [area for area in dict.fromkeys(areas) if area in KNOWN_AREAS]
        if isinstance(areas, list) and all(isinstance(area, str) for area in areas)
        else []
    )
    return {
        "active": True,
        "message": message,
        "areas": known,
        "started_at": _parse_time(stored.get("started_at")),
        "expires_at": expires_at,
    }


async def set_banner(
    message: str,
    areas: List[str],
    duration_minutes: int,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Switch the banner on (or replace it), to show for `duration_minutes`.

    Raises:
        RextExternalServiceException: Redis didn't take the value, so no banner is showing.
    """
    started_at = now or _now()
    expires_at = started_at + timedelta(minutes=duration_minutes)
    value = {
        "message": message,
        "areas": list(areas),
        "started_at": started_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    saved = await cache.set(BANNER_KEY, value, ttl=duration_minutes * 60)
    if not saved:
        raise RextExternalServiceException(
            message="The banner couldn't be switched on: the store that holds it can't be reached.",
            service_name="redis",
            status_code=503,
        )
    logger.info("Incident banner switched on", minutes=duration_minutes, areas=list(areas))
    return {
        "active": True,
        "message": message,
        "areas": list(areas),
        "started_at": started_at,
        "expires_at": expires_at,
    }


async def restore_banner(previous: Dict[str, Any]) -> None:
    """
    Put back what was showing before a switch that then couldn't be recorded (its audit entry
    failed): the earlier banner for the time it had left, or none. So a switch nobody can find in
    the audit log doesn't stay on every page. Best effort: it logs and never raises, since it runs
    while another error is already on its way to the caller.
    """
    try:
        expires_at = previous.get("expires_at")
        if previous.get("active") and isinstance(expires_at, datetime):
            remaining = int((expires_at - _now()).total_seconds())
            if remaining > 0:
                started_at = previous.get("started_at")
                await cache.set(
                    BANNER_KEY,
                    {
                        "message": previous.get("message"),
                        "areas": list(previous.get("areas") or []),
                        "started_at": started_at.isoformat()
                        if isinstance(started_at, datetime)
                        else None,
                        "expires_at": expires_at.isoformat(),
                    },
                    ttl=remaining,
                )
                return
        if cache.is_enabled and cache.redis is not None:
            await cache.redis.delete(BANNER_KEY)
    except Exception as error:
        logger.error("Incident banner could not be put back", error=str(error))


async def clear_banner() -> bool:
    """
    Switch the banner off. True when one was showing.

    Raises:
        RextExternalServiceException: Redis can't be reached, so a banner may still be showing.
    """
    unreachable = RextExternalServiceException(
        message="The banner couldn't be switched off: the store that holds it can't be reached.",
        service_name="redis",
        status_code=503,
    )
    if not cache.is_enabled or cache.redis is None:
        raise unreachable
    try:
        # The client itself, not its `delete`, which answers False for a failure as it does for
        # a key that wasn't there: here the difference is a banner still on every page.
        was_showing = bool(await cache.redis.delete(BANNER_KEY))
    except Exception as error:
        logger.error("Incident banner delete failed", error=str(error))
        raise unreachable from error
    logger.info("Incident banner switched off", was_showing=was_showing)
    return was_showing
