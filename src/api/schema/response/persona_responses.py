from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from uuid import UUID


class PersonaResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    full_name: Optional[str] = None
    professional_title: Optional[str] = None
    areas_of_expertise: List[str] = []
    experience_type: Optional[str] = None
    years_of_experience: Optional[int] = None
    credentials: List[Dict[str, Any]] = []
    employer: Optional[str] = None
    writing_voice: Optional[str] = None
    bio: Optional[str] = None
    social_profiles: List[Dict[str, Any]] = []
    linkedin_url: Optional[str] = None  # derived from social_profiles, backward-compat
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PersonaListResponse(BaseModel):
    personas: List[PersonaResponse]
    total_count: int
