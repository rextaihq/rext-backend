from pydantic import BaseModel
from typing import List, Dict, Any


class MetaDescriptionRequest(BaseModel):
    """
    Request model for meta description generation.

    Attributes:
        page_title: The title of the page (e.g., "Best SEO Tools for 2024")
        target_keywords: List of target keywords (e.g., ["SEO tools", "keyword research"])
    """
    page_title: str
    target_keywords: List[str]


class MetaDescriptionValidation(BaseModel):
    """
    Validation results for meta description.

    Attributes:
        length: Actual character length of the description
        is_optimal_length: Whether length is between 120-160 characters
        character_count: Formatted string like "142/160"
        warnings: List of validation warnings
    """
    length: int
    is_optimal_length: bool
    character_count: str
    warnings: List[str]


class MetaDescriptionResponse(BaseModel):
    """
    Response model for meta description generation.

    Attributes:
        meta_description: The generated SEO-optimized meta description
        validation: Validation results for the generated description
    """
    meta_description: str
    validation: MetaDescriptionValidation
    
