from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class SignupPageContentState(BaseFinalContent, total=False):
    platform_name: str
    value_prop_reminder: str
    social_login_options: Optional[list[str]]
    required_fields: list[str]
