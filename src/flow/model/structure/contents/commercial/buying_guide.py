from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class BuyingGuideGeneratedContent(BaseGeneratedContent):
    product_category: Optional[str] = Field(default=None, description="The category being bought.")
    key_features_to_consider: Optional[List[str]] = Field(
        default_factory=list, description="Important features to look for."
    )
    budget_tiers: Optional[List[str]] = Field(
        default=None, description="Summary of pricing or budget levels."
    )
    common_mistakes_to_avoid: Optional[List[str]] = Field(
        default=None, description="Pitfalls buyers make."
    )


if __name__ == "__main__":
    # Simulates your LLM output
    raw_llm_output = {
        "title": "Test",
        "internal_links": [{"url": "https://test.com"}],  # Missing fields!
        "outbound_links": [{"url": "https://external.com"}],
    }

    content = BuyingGuideGeneratedContent.model_validate(raw_llm_output)
    print(content.internal_links[0].link_type)  # "internal" ✓
