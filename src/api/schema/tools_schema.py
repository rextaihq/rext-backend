from pydantic import BaseModel, HttpUrl

class CanonicalTagRequest(BaseModel):
    url: HttpUrl


class CanonicalTagResponse(BaseModel):
    canonical_tag: str
    url: str
    normalized_url: str
