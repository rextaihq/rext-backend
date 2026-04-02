from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class ContactUsOutline(BaseOutline):
    """Outline for a contact page or guide."""
    company_name: str = Field(description="The company being contacted.")
    contact_methods: List[str] = Field(description="Channels available (e.g., 'Email', 'Phone', 'Live Chat').")
    expected_response_time: Optional[str] = Field(description="When the user can expect a reply.")
    office_locations: Optional[List[str]] = Field(description="Physical addresses, if applicable.")
