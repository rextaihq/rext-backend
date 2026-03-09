from pydantic import BaseModel
from typing import List, Any

class CleanupResponse(BaseModel):
    deleted_count: int
    message: str

class PendingDeletionsResponse(BaseModel):
    pending_deletions: List[Any]
    count: int
