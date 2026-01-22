from pydantic import BaseModel

class TitleRequest(BaseModel):
    keyword: str
    topic: str
    brand: str
    tone: str
