from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# Note: AdminEmailLogResponse and ResendEmailRequest already exist in src.api.schema.admin_email_schema
# We are just adding the response wrappers here

from src.api.schema.admin_email_schema import AdminEmailLogResponse

class FailedEmailsResponseSchema(BaseModel):
    emails: List[AdminEmailLogResponse]
    total: int
    limit: int
    offset: int
    days_back: int

class ResendEmailResponseSchema(BaseModel):
    original_email_id: str
    new_email_id: str
    new_status: str
    retry_count: int

class BatchResendSuccessfulItemSchema(BaseModel):
    original_id: str
    new_id: str
    status: str

class BatchResendFailedItemSchema(BaseModel):
    id: str
    error: str

class BatchResendResponseSchema(BaseModel):
    successful: List[BatchResendSuccessfulItemSchema]
    failed: List[BatchResendFailedItemSchema]
