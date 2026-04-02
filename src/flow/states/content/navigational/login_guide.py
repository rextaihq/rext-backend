from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class LoginGuideContentState(BaseFinalContent, total=False):
    platform_name: str
    common_login_issues: list[str]
    support_contact_included: bool
