from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class InvitationAnalyticsSummarySchema(BaseModel):
    total_invitations: int
    accepted: int
    declined: int
    expired: int
    pending: int
    acceptance_rate: float
    decline_rate: float
    expiry_rate: float
    avg_time_to_acceptance_hours: float

class InvitationTopInviterSchema(BaseModel):
    user_id: str
    name: str
    email: str
    invitation_count: int

class InvitationPopularRoleSchema(BaseModel):
    role_id: str
    name: str
    invitation_count: int

class InvitationDailyTrendSchema(BaseModel):
    date: Optional[str]
    total: int
    accepted: int
    pending: int

class InvitationWorkspaceStatSchema(BaseModel):
    workspace_id: str
    name: str
    total_invitations: int
    accepted_invitations: int
    acceptance_rate: float

class InvitationPeriodSchema(BaseModel):
    start_date: str
    end_date: str
    days: int

class InvitationAnalyticsResponseSchema(BaseModel):
    summary: InvitationAnalyticsSummarySchema
    top_inviters: List[InvitationTopInviterSchema]
    popular_roles: List[InvitationPopularRoleSchema]
    daily_trend: List[InvitationDailyTrendSchema]
    workspace_stats: List[InvitationWorkspaceStatSchema]
    period: InvitationPeriodSchema
