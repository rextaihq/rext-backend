from datetime import datetime, timezone
from typing import Optional

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
