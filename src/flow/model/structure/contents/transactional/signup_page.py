from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class SignupPageGeneratedContent(BaseGeneratedContent):
    platform_name: Optional[str] = Field(default=None, description="Platform name.")
    value_prop_reminder: Optional[str] = Field(
        default=None, description="Reminder of signup value."
    )
    social_login_options: Optional[List[str]] = Field(
        default=None, description="Options for social login."
    )
    required_fields: Optional[List[str]] = Field(
        default_factory=list, description="Fields required to signup."
    )
