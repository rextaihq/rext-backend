from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class KnowledgeBaseBrief(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: Optional[str]
    created_at: str
    updated_at: str
    items_count: Optional[int] = None

class KnowledgeBaseListResponse(BaseModel):
    knowledge_bases: List[KnowledgeBaseBrief]
    total_count: int
    limit: int
    offset: int
    has_more: bool

class KnowledgeBaseResponse(BaseModel):
    knowledge_base: Dict[str, Any] # to_dict output

class KnowledgeBaseDeleteResponse(BaseModel):
    kb_id: str
