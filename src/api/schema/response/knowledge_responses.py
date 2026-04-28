from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID


# ---------------------------------------------------------------------------
# Shared typed item models
# ---------------------------------------------------------------------------

class WebKnowledgeItem(BaseModel):
    id: UUID
    workspace_id: UUID
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FileKnowledgeItem(BaseModel):
    id: UUID
    workspace_id: UUID
    filename: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TextKnowledgeItem(BaseModel):
    id: UUID
    workspace_id: UUID
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Aggregated / summary responses
# ---------------------------------------------------------------------------

class KnowledgeSummary(BaseModel):
    web_count: int
    file_count: int
    text_count: int
    total_count: int

class WorkspaceKnowledgeResponse(BaseModel):
    web_knowledge: List[WebKnowledgeItem]
    file_knowledge: List[FileKnowledgeItem]
    text_knowledge: List[TextKnowledgeItem]
    summary: KnowledgeSummary

class KnowledgeSearchResult(BaseModel):
    results: List[WebKnowledgeItem]
    query: str
    total_results: int


# ---------------------------------------------------------------------------
# Web knowledge responses
# ---------------------------------------------------------------------------

class WebKnowledgeListResponse(BaseModel):
    web_knowledge: List[WebKnowledgeItem]
    total_count: int
    limit: int
    offset: int
    has_more: bool

class WebKnowledgeResponse(BaseModel):
    web_knowledge: WebKnowledgeItem

class WebKnowledgeDeleteResponse(BaseModel):
    web_id: UUID


# ---------------------------------------------------------------------------
# File knowledge responses
# ---------------------------------------------------------------------------

class FileKnowledgeListResponse(BaseModel):
    file_knowledge: List[FileKnowledgeItem]
    total_count: int
    limit: int
    offset: int
    has_more: bool

class FileKnowledgeResponse(BaseModel):
    file_knowledge: FileKnowledgeItem

class FileKnowledgeDeleteResponse(BaseModel):
    file_id: UUID


# ---------------------------------------------------------------------------
# Text knowledge responses
# ---------------------------------------------------------------------------

class TextKnowledgeListResponse(BaseModel):
    text_knowledge: List[TextKnowledgeItem]
    total_count: int
    limit: int
    offset: int
    has_more: bool

class TextKnowledgeResponse(BaseModel):
    text_knowledge: TextKnowledgeItem

class TextKnowledgeDeleteResponse(BaseModel):
    text_id: UUID
