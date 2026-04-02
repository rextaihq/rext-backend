from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class FeatureOverviewGeneratedContent(BaseGeneratedContent):
    product_name: str = Field(description="The product these features belong to.")
    number_of_features_highlighted: int = Field(description="How many major features are discussed.")
    target_user_role: Optional[str] = Field(description="Who these features are built for.")
    integration_mentions: Optional[List[str]] = Field(description="Any third-party integrations.")
