from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class KnowledgeBaseBrief(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items_count: Optional[int] = None

class KnowledgeBaseListResponse(BaseModel):
    knowledge_bases: List[KnowledgeBaseBrief]
    total_count: int
    limit: int
    offset: int
    has_more: bool

class KnowledgeBaseDetail(BaseModel):
    """Typed detail model replacing Dict[str, Any]."""
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items_count: Optional[int] = None

class KnowledgeBaseResponse(BaseModel):
    knowledge_base: KnowledgeBaseDetail

class KnowledgeBaseDeleteResponse(BaseModel):
    kb_id: UUID
