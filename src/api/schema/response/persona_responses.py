from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class PersonaResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: Optional[str]
    avatar_url: Optional[str]
    full_name: Optional[str]
    professional_title: Optional[str]
    areas_of_expertise: List[str]
    tone_of_voice: Optional[str]
    bio: Optional[str]
    linkedin_url: Optional[str]
    demographics: Optional[Dict[str, Any]]
    pain_points: List[str]
    goals: List[str]
    behaviors: List[str]
    created_at: str
    updated_at: str

class PersonaListResponse(BaseModel):
    personas: List[PersonaResponse]
    total_count: int
