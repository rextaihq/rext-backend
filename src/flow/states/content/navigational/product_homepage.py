from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.content.base import BaseFinalContent


class ProductHomepageContentState(BaseFinalContent, total=False):
    product_name: str
    hero_headline: str
    primary_call_to_action: str
    key_benefits: list[str]
    social_proof_elements: Optional[list[str]]
