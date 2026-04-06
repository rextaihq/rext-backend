from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class LoginGuideGeneratedContent(BaseGeneratedContent):
    platform_name: Optional[str] = Field(default=None, description="The platform.")
    common_login_issues: Optional[List[str]] = Field(default_factory=list, description="List of issues discussed.")
    support_contact_included: Optional[bool] = Field(default=True)
