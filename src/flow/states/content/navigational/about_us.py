from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class AboutUsContentState(BaseFinalContent, total=False):
    company_name: str
    mission_statement: str
    key_milestones: Optional[list[str]]
    team_members_mentioned: Optional[list[str]]
