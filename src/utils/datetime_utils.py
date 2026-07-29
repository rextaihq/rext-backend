from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.utils.logger import logger

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
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
            
        dt = datetime.fromisoformat(date_str)
        
        # Ensure timezone awareness
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
            
        return dt
    except ValueError as e:
        raise ValueError(f"Invalid ISO datetime format: {date_str}") from e


def resolve_scheduled_datetime(dt: datetime, user_timezone: Optional[str]) -> datetime:
    """Interpret a user-picked scheduling datetime and return it as UTC-aware.

    - If `dt` already carries an explicit UTC offset, that offset is trusted
      as-is (e.g. a programmatic caller that already computed the exact instant).
    - If `dt` is naive (no offset), it is wall-clock time in the user's account
      timezone — NOT the server's or browser's — and is converted to UTC here.
      An unknown/invalid timezone name falls back to UTC rather than raising,
      so a bad profile value can't crash scheduling.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)

    tz_name = user_timezone or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(
            "resolve_scheduled_datetime: unknown timezone %r, falling back to UTC",
            tz_name,
        )
        tz = ZoneInfo("UTC")

    return dt.replace(tzinfo=tz).astimezone(timezone.utc)
