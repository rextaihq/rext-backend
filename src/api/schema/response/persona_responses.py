from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class PersonaResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str]
    avatar_url: Optional[str]
    full_name: Optional[str]
    professional_title: Optional[str]
    areas_of_expertise: List[str]
    tone_of_voice: Optional[str] = None
    bio: Optional[str] = None
    linkedin_url: Optional[str] = None
    demographics: Optional[Dict[str, Any]] = None
    pain_points: List[str]
    goals: List[str]
    behaviors: List[str]
    created_at: datetime
    updated_at: datetime


class PersonaListResponse(BaseModel):
    personas: List[PersonaResponse]
    total_count: int
