from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class KnowledgeSummary(BaseModel):
    web_count: int
    file_count: int
    text_count: int
    total_count: int

class WorkspaceKnowledgeResponse(BaseModel):
    web_knowledge: List[Any]
    file_knowledge: List[Any]
    text_knowledge: List[Any]
    summary: KnowledgeSummary

class KnowledgeSearchResult(BaseModel):
    results: List[Any]
    query: str
    total_results: int

class WebKnowledgeListResponse(BaseModel):
    web_knowledge: List[Any]
    total_count: int
    limit: int
    offset: int
    has_more: bool

class WebKnowledgeResponse(BaseModel):
    web_knowledge: Dict[str, Any]

class WebKnowledgeDeleteResponse(BaseModel):
    web_id: str

class FileKnowledgeListResponse(BaseModel):
    file_knowledge: List[Any]
    total_count: int
    limit: int
    offset: int
    has_more: bool

class FileKnowledgeResponse(BaseModel):
    file_knowledge: Dict[str, Any]

class FileKnowledgeDeleteResponse(BaseModel):
    file_id: str

class TextKnowledgeListResponse(BaseModel):
    text_knowledge: List[Any]
    total_count: int
    limit: int
    offset: int
    has_more: bool

class TextKnowledgeResponse(BaseModel):
    text_knowledge: Dict[str, Any]

class TextKnowledgeDeleteResponse(BaseModel):
    text_id: str
