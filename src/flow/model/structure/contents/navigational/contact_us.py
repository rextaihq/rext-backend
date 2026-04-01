from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ContactUsGeneratedContent(BaseGeneratedContent):
    company_name: str = Field(description="Company being contacted.")
    contact_methods: List[str] = Field(description="Channels available.")
    expected_response_time: Optional[str] = Field(description="When to expect a reply.")
    office_locations: Optional[List[str]] = Field(description="Physical addresses.")
