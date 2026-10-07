from typing import List, Literal, Optional

from pydantic import BaseModel


class TrashDeleter(BaseModel):
    id: str
    # Their name, or their email when they have none; None once the account is gone.
    name: Optional[str] = None


class TrashItem(BaseModel):
    kind: Literal["article", "persona"]
    id: str
    # The article's title or the persona's name.
    name: str
    deleted_at: str
    deleted_by: Optional[TrashDeleter] = None
    # After this the nightly purge deletes it for good.
    recovery_deadline: str
    days_remaining: int


class TrashListResponse(BaseModel):
    items: List[TrashItem]
    total_count: int
    retention_days: int


class TrashActionResponse(BaseModel):
    kind: Literal["article", "persona"]
    id: str
    name: Optional[str] = None
