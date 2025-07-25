from pydantic import BaseModel, Field
from typing import List, Optional

class TopicSelectionSchema(BaseModel):
    topic:List[str]