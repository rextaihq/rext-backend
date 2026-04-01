from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class LoginGuideGeneratedContent(BaseGeneratedContent):
    platform_name: str = Field(description="The platform.")
    common_login_issues: List[str] = Field(description="List of issues discussed.")
    support_contact_included: bool = Field(default=True)
