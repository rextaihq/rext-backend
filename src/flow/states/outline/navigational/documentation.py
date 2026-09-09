from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.outline.base import BaseOutlineState


class DocumentationOutlineState(BaseOutlineState, total=False):
    topic_or_module: str
    intended_audience_technical_level: str
    prerequisites_needed: Optional[list[str]]
    includes_code_snippets: bool
