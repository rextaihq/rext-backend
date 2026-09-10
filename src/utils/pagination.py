import base64
import json
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID


def encode_cursor(created_at: datetime, notification_id: UUID) -> str:
    """Encode pagination cursor from notification fields."""
    payload = {
        "c": created_at.isoformat(),
        "i": str(notification_id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> Optional[Tuple[datetime, UUID]]:
    """Decode pagination cursor. Returns (created_at, id) or None if invalid."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        created_at = datetime.fromisoformat(payload["c"])
        notification_id = UUID(payload["i"])
        return created_at, notification_id
    except (json.JSONDecodeError, KeyError, ValueError, UnicodeDecodeError):
        return None
