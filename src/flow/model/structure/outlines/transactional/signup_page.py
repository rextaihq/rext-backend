from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class SignupPageOutline(BaseOutline):
    """Outline for a signup or registration page."""
    platform_name: str = Field(description="What the user is signing up for.")
    value_prop_reminder: str = Field(description="Short text reminding them WHY they should sign up.")
    social_login_options: Optional[List[str]] = Field(description="E.g., 'Google', 'GitHub'.")
    required_fields: List[str] = Field(description="E.g., 'Email', 'Password', 'Company Name'.")
