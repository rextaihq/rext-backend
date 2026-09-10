from __future__ import annotations

from src.flow.states.outline.base import BaseOutlineState


class LoginGuideOutlineState(BaseOutlineState, total=False):
    platform_name: str
    common_login_issues: list[str]
    support_contact_included: bool
