from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

class PaginationSchema(BaseModel):
    page: int
    per_page: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool

class CustomerListItemWorkspaceSchema(BaseModel):
    id: str
    name: str

class CustomerListItemSubscriptionSchema(BaseModel):
    id: Optional[str] = None
    status: Optional[str] = None
    plan_id: Optional[str] = None
    plan_name: Optional[str] = None

class CustomerListItemSchema(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: str
    last_login_at: Optional[str] = None
    is_active: bool
    is_verified: bool
    subscription: CustomerListItemSubscriptionSchema
    workspaces: List[CustomerListItemWorkspaceSchema]

class CustomerListResponseSchema(BaseModel):
    customers: List[CustomerListItemSchema]
    pagination: PaginationSchema

class CustomerDetailUserSchema(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    is_active: bool
    status: str
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None

class CustomerDetailSubscriptionPlanSchema(BaseModel):
    id: Optional[str] = None
    name: str
    price_monthly: float
    price_yearly: float

class CustomerDetailSubscriptionSchema(BaseModel):
    id: str
    plan: CustomerDetailSubscriptionPlanSchema
    status: str
    billing_period: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    trial_end_date: Optional[str] = None
    cancelled_at: Optional[str] = None

class CustomerDetailWorkspaceSchema(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None

class CustomerDetailActivitySummarySchema(BaseModel):
    last_login: Optional[str] = None
    total_content_created: int
    total_knowledge_items: int
    workspaces_count: int

class CustomerDetailSchema(BaseModel):
    user: CustomerDetailUserSchema
    subscription: Optional[CustomerDetailSubscriptionSchema] = None
    workspaces: List[CustomerDetailWorkspaceSchema]
    usage: Optional[Any] = None
    activity_summary: CustomerDetailActivitySummarySchema
    audit_events: List[Any]
    notes: List[Any]

class CustomerActionResponseSchema(BaseModel):
    status: str
    new_api_calls: Optional[int] = None
    new_trial_end: Optional[str] = None
    extension_days: Optional[int] = None
    cancelled_at: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None

class CustomerNoteResponseSchema(BaseModel):
    id: str
    note: str
    category: str
    created_at: Optional[str] = None
