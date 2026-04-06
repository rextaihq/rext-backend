from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ContactUsGeneratedContent(BaseGeneratedContent):
    company_name: Optional[str] = Field(default=None, description="Company being contacted.")
    contact_methods: Optional[List[str]] = Field(default_factory=list, description="Channels available.")
    expected_response_time: Optional[str] = Field(default=None, description="When to expect a reply.")
    office_locations: Optional[List[str]] = Field(default=None, description="Physical addresses.")
