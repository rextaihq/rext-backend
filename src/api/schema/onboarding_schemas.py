"""Onboarding schemas."""

from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class OnboardingStepUpdate(BaseModel):
    """Schema for updating onboarding step."""

    step: int = Field(..., ge=0, le=5, description="Step number (0-5)")
    action: str = Field(..., description="Action: complete, skip, or set_current")


class OnboardingResponse(BaseModel):
    """Schema for onboarding status response."""

    id: UUID
    user_id: UUID
    completed: bool
    current_step: int
    completed_steps: List[int]
    skipped_steps: List[int]
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class OnboardingReset(BaseModel):
    """Schema for resetting onboarding."""

    confirm: bool = Field(..., description="Confirmation to reset onboarding")


# Onboarding step definitions (for frontend reference)
ONBOARDING_STEPS = [
    {
        "id": 0,
        "name": "welcome",
        "title": "Welcome to WREXT",
        "description": "Learn what WREXT can do for you",
        "required": True,
    },
    {
        "id": 1,
        "name": "create_workspace",
        "title": "Create Your First Workspace",
        "description": "Set up a workspace for your team",
        "required": True,
    },
    {
        "id": 2,
        "name": "invite_team",
        "title": "Invite Your Team",
        "description": "Add team members to collaborate",
        "required": False,
    },
    {
        "id": 3,
        "name": "upload_knowledge",
        "title": "Upload Knowledge Base",
        "description": "Add your first knowledge base",
        "required": False,
    },
    {
        "id": 4,
        "name": "generate_content",
        "title": "Generate Content",
        "description": "Create your first AI-generated content",
        "required": False,
    },
    {
        "id": 5,
        "name": "complete",
        "title": "You're All Set!",
        "description": "Explore WREXT and start creating",
        "required": True,
    },
]
