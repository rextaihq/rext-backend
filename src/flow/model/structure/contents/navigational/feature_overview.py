from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class FeatureOverviewGeneratedContent(BaseGeneratedContent):
    product_name: Optional[str] = Field(default=None, description="The product these features belong to.")
    number_of_features_highlighted: Optional[int] = Field(default=None, description="How many major features are discussed.")
    target_user_role: Optional[str] = Field(default=None, description="Who these features are built for.")
    integration_mentions: Optional[List[str]] = Field(default=None, description="Any third-party integrations.")
