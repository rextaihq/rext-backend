from pydantic import BaseModel, Field
from typing import Optional

class KeywordRankRequest(BaseModel):
    keyword: str = Field(..., json_schema_extra={"example": "best seo tools"})
    website_url: str = Field(..., json_schema_extra={"example": "https://example.com"})

class KeywordRankResponse(BaseModel):
    keyword: str
    website_url: str
    rank_position: Optional[int] = None
    found_url: Optional[str] = None
    status: str