from pydantic import BaseModel
from typing import List, Optional

# For Reviewers
class UsersBase(BaseModel):
    name: str
    email: str
    expertise: Optional[List[str]] = None
    affiliated_topics: Optional[List[str]] = None