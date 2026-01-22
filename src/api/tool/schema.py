from pydantic import BaseModel
from typing import List, Dict, Any


class MetaDescriptionRequest(BaseModel):

    page_title: str
    target_keywords: List[str]


class MetaDescriptionValidation(BaseModel):

    length: int
    is_optimal_length: bool
    character_count: str
    warnings: List[str]


class MetaDescriptionResponse(BaseModel):

    meta_description: str
    validation: MetaDescriptionValidation


class TitleRequest(BaseModel):
    keyword: str
    topic: str
    brand: str
    tone: str


class TitleResponse(BaseModel):
    titles: List[str]

