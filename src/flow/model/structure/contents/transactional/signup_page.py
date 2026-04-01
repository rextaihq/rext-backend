from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class SignupPageGeneratedContent(BaseGeneratedContent):
    platform_name: str = Field(description="Platform name.")
    value_prop_reminder: str = Field(description="Reminder of signup value.")
    social_login_options: Optional[List[str]] = Field(description="Options for social login.")
    required_fields: List[str] = Field(description="Fields required to signup.")
