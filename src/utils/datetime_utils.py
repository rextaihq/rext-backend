import calendar
from datetime import date, datetime, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.utils.logger import logger


def add_months(dt: datetime, months: int) -> datetime:
    """
    Add a specified number of months to a datetime object, preserving the day of the month
    if possible, or snapping to the last day of the target month (e.g., Jan 31 + 1 month = Feb 28/29).
    """
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1

    # Get the last day of the target month
    _, last_day = calendar.monthrange(year, month)

    # Use the minimum of the original day or the last day of the target month
    day = min(dt.day, last_day)

    return dt.replace(year=year, month=month, day=day)


def next_billing_anchor(anchor: datetime, now: Optional[datetime] = None) -> datetime:
    """Return the next billing-period end strictly after ``now``.

    The cadence is one calendar month, anchored to ``anchor``. Advancing is done
    from the ORIGINAL anchor (``add_months(anchor, n)``), not by repeatedly
    stepping the previous result, so the billing day is preserved as closely as
    possible even when the stored reset date is several months stale (e.g. a
    dormant subscription that missed multiple resets). End-of-month anchors such
    as Jan 31 fall back to the last day of shorter months via ``add_months``.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    # Match the tz-awareness of the anchor so the comparison never raises.
    if anchor.tzinfo is None and now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    elif anchor.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # If the anchor is already in the future it is itself the next period end.
    result = anchor
    months = 0
    while result <= now:
        months += 1
        result = add_months(anchor, months)
    return result


def parse_provider_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a payment-provider ISO-8601 timestamp to a naive-UTC datetime.

    LemonSqueezy sends UTC timestamps (sometimes suffixed with ``Z``). The
    subscription tables store naive-UTC datetimes (see ``renews_at`` /
    ``trial_end_date``), so normalise to naive UTC to stay consistent with the
    existing columns and avoid naive/aware comparison errors.
    """
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def utc_now() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def utc_now_naive() -> datetime:
    """Get current UTC datetime as naive datetime (no timezone info).

    Warning: This is deprecated and should only be used for legacy compatibility.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_iso_datetime(date_str: str) -> datetime:
    """Parse ISO 8601 datetime string to timezone-aware datetime."""
    if not date_str:
        raise ValueError("Date string cannot be empty")

    try:
        # Handle formats ending in Z
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"

        dt = datetime.fromisoformat(date_str)

        # Ensure timezone awareness
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except ValueError as e:
        raise ValueError(f"Invalid ISO datetime format: {date_str}") from e


def account_zone(user_timezone: Optional[str]) -> tzinfo:
    """The timezone a user's account names, as a tzinfo.

    An unknown or invalid name falls back to UTC rather than raising, so a bad
    profile value can't crash scheduling or the calendar.
    """
    tz_name = user_timezone or "UTC"
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("account_zone: unknown timezone %r, falling back to UTC", tz_name)
        # Use the stdlib UTC singleton, not ZoneInfo("UTC") - if the IANA tzdata
        # database isn't installed (e.g. a slim container missing the tzdata
        # package), ZoneInfo("UTC") throws too, and scheduling must not depend
        # on tzdata being present to handle the plain-UTC case.
        return timezone.utc


def resolve_scheduled_datetime(dt: datetime, user_timezone: Optional[str]) -> datetime:
    """Interpret a user-picked scheduling datetime and return it as UTC-aware.

    - If `dt` already carries an explicit UTC offset, that offset is trusted
      as-is (e.g. a programmatic caller that already computed the exact instant).
    - If `dt` is naive (no offset), it is wall-clock time in the user's account
      timezone — NOT the server's or browser's — and is converted to UTC here
      (see `account_zone` for an unknown timezone).
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)

    return dt.replace(tzinfo=account_zone(user_timezone)).astimezone(timezone.utc)


def moved_to_day(when: datetime, day: date, user_timezone: Optional[str]) -> datetime:
    """`when` moved to another calendar day, keeping its time of day.

    The day and the time of day are the account timezone's, so a 09:00 publish
    stays at 09:00 on the new day across a daylight-saving change. Returns UTC.
    """
    local = when.astimezone(account_zone(user_timezone))
    return resolve_scheduled_datetime(datetime.combine(day, local.time()), user_timezone)
