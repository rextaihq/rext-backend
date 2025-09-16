from pydantic import BaseModel, HttpUrl,Field
from typing import Optional,List

# Knowledge Schema
class WorkspaceSchema(BaseModel):
    title: Optional[str] = None
    description: str
    url: Optional[HttpUrl] = None
