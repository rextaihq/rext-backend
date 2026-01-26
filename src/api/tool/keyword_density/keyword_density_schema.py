from pydantic import BaseModel, Field
from typing import List

class KeywordDensityRequest(BaseModel):
    content: str = Field(..., json_schema_extra={"example": "SEO tools help improve website ranking"})
    keywords: List[str] = Field(..., json_schema_extra={"example": ["seo"]})

class KeywordResult(BaseModel):
    keyword: str
    count: int
    density_percent: float

class KeywordDensityResponse(BaseModel):
    total_words: int
    keywords: List[KeywordResult]
