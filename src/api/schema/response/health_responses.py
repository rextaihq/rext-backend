from typing import Any, Dict

from pydantic import BaseModel


class BasicHealthResponse(BaseModel):
    status: str
    service: str
    timestamp: float


class PaymentHealthResponse(BaseModel):
    status: str
    timestamp: float
    checks: Dict[str, Any]


class QuickPaymentHealthResponse(BaseModel):
    status: str
    configured: bool
    timestamp: float
