from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class LoginGuideOutline(BaseOutline):
    """Outline for a guide directing users on how to log in or access their accounts."""
    platform_name: str = Field(description="The platform the user is trying to access.")
    common_login_issues: List[str] = Field(description="List of issues like 'Forgot Password' or '2FA Failures'.")
    support_contact_included: bool = Field(default=True, description="Whether to include a link to actual support.")
