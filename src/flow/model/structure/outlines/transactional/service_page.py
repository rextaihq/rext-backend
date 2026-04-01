from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class ServicePageOutline(BaseOutline):
    """Outline for a local business or agency service page."""
    service_name: str = Field(description="What is being provided (e.g., 'Plumbing', 'SEO Consulting').")
    service_area: Optional[str] = Field(description="Locations covered, if local.")
    the_process: List[str] = Field(description="How the service works, step-by-step.")
    why_choose_us: List[str] = Field(description="Differentiators or selling points.")
