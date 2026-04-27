from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class FeatureOverviewOutline(BaseOutline):
    """Outline for a page describing the features of a product."""
    product_name: str = Field(description="The product these features belong to.")
    number_of_features_highlighted: int = Field(description="How many major features are discussed.")
    target_user_role: Optional[str] = Field(description="Who these features are built for (e.g., 'Developers', 'Marketers').")
    integration_mentions: Optional[List[str]] = Field(description="Any third-party integrations mentioned along with these features.")
