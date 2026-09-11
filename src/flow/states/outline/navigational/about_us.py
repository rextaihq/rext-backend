from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.outline.base import BaseOutlineState


class AboutUsOutlineState(BaseOutlineState, total=False):
    company_name: str
    mission_statement: str
    key_milestones: Optional[list[str]]
    team_members_mentioned: Optional[list[str]]
