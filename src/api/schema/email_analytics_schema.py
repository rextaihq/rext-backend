from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class EmailOverviewStatsSchema(BaseModel):
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    total_complained: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    bounce_rate: float
    complaint_rate: float


class EmailTemplateStatsSchema(BaseModel):
    template_type: str
    sent: int
    delivered: int
    opened: int
    clicked: int
    open_rate: float
    click_rate: float


class EmailTemplatesResponseSchema(BaseModel):
    templates: List[EmailTemplateStatsSchema]
    total_count: int


class EmailTimelineItemSchema(BaseModel):
    date: datetime
    sent: int
    opened: int
    clicked: int


class EmailTimelineResponseSchema(BaseModel):
    timeline: List[EmailTimelineItemSchema]
    total_count: int


class EmailFailureItemSchema(BaseModel):
    id: UUID
    to: str
    template_type: str
    status: str
    error_message: Optional[str] = None
    sent_at: datetime


class EmailFailuresResponseSchema(BaseModel):
    failures: List[EmailFailureItemSchema]
    total_count: int
