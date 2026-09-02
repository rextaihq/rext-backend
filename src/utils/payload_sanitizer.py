import logging
from html import escape
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Maximum allowed payload size in bytes (64 KB)
MAX_PAYLOAD_SIZE_BYTES = 65_536

# Maximum nesting depth for payload objects
MAX_NESTING_DEPTH = 5

# Maximum number of keys in a single payload object
MAX_PAYLOAD_KEYS = 50

# Maximum string value length
MAX_STRING_LENGTH = 10_000


def sanitize_notification_payload(
    payload: Optional[Dict[str, Any]],
    max_size_bytes: int = MAX_PAYLOAD_SIZE_BYTES,
) -> Optional[Dict[str, Any]]:
    """
    Validate and sanitize a notification payload dict.

    - Enforces size limits to prevent database bloat
    - HTML-escapes all string values to prevent stored XSS
    - Limits nesting depth and key count
    - Returns None if payload is None or empty

    Args:
        payload: The raw payload dict to sanitize.
        max_size_bytes: Maximum serialized size in bytes.

    Returns:
        Sanitized payload dict, or None if input is None/empty.

    Raises:
        ValueError: If payload exceeds size or structure limits.
    """
    if payload is None:
        return None

    if not isinstance(payload, dict):
        logger.warning("Notification payload is not a dict, discarding")
        return None

    if not payload:
        return None

    # Check serialized size
    import json

    serialized = json.dumps(payload, default=str)
    if len(serialized.encode("utf-8")) > max_size_bytes:
        raise ValueError(f"Notification payload exceeds maximum size of {max_size_bytes} bytes")

    return _sanitize_value(payload, depth=0)


def _sanitize_value(value: Any, depth: int) -> Any:
    """Recursively sanitize a value, HTML-escaping all strings."""
    if depth > MAX_NESTING_DEPTH:
        return "[nested object truncated]"

    if isinstance(value, str):
        truncated = value[:MAX_STRING_LENGTH]
        return escape(truncated)

    if isinstance(value, dict):
        if len(value) > MAX_PAYLOAD_KEYS:
            raise ValueError(f"Payload object has {len(value)} keys, maximum is {MAX_PAYLOAD_KEYS}")
        return {_sanitize_key(k): _sanitize_value(v, depth + 1) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item, depth + 1) for item in value[:100]]

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    # For any other type, convert to string and escape
    return escape(str(value)[:MAX_STRING_LENGTH])


def _sanitize_key(key: Any) -> str:
    """Ensure dict keys are safe strings."""
    key_str = str(key)[:200]
    return escape(key_str)
