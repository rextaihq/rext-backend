from pydantic import BaseModel
from typing import List, Optional,Literal
from datetime import datetime

class NotificationBase(BaseModel):
    title: str
    description: str
    notification_type: str
    status: Optional[str] = "unread"