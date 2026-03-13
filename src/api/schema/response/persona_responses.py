from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from uuid import UUID

class PersonaResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str] = None
    full_name: Optional[str] = None
    professional_title: Optional[str] = None
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
