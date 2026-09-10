from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.outline.base import BaseOutlineState


class ContactUsOutlineState(BaseOutlineState, total=False):
    company_name: str
    contact_methods: list[str]
    expected_response_time: Optional[str]
    office_locations: Optional[list[str]]
