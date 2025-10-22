"""
Invoice schemas for subscription invoices.

This module defines Pydantic models for invoice operations.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class InvoiceItem(BaseModel):
    """Schema for an invoice line item."""
    description: str = Field(..., description="Item description")
    quantity: int = Field(..., description="Quantity")
    unit_price: float = Field(..., description="Unit price")
    total: float = Field(..., description="Total amount for this item")


class Invoice(BaseModel):
    """Schema for an invoice."""
    invoice_id: str = Field(..., description="Invoice ID")
    invoice_number: Optional[str] = Field(None, description="Human-readable invoice number")
    status: str = Field(..., description="Invoice status (paid, unpaid, refunded, etc.)")
    amount: float = Field(..., description="Total amount")
    currency: str = Field(default="USD", description="Currency code")
    tax: Optional[float] = Field(None, description="Tax amount")
    subtotal: Optional[float] = Field(None, description="Subtotal before tax")
    invoice_url: Optional[str] = Field(None, description="URL to view/download invoice")
    invoice_date: str = Field(..., description="Invoice date (ISO format)")
    due_date: Optional[str] = Field(None, description="Due date (ISO format)")
    paid_at: Optional[str] = Field(None, description="Payment date (ISO format)")
    customer_email: Optional[str] = Field(None, description="Customer email")
    customer_name: Optional[str] = Field(None, description="Customer name")
    items: Optional[List[InvoiceItem]] = Field(default_factory=list, description="Invoice line items")

    class Config:
        json_schema_extra = {
            "example": {
                "invoice_id": "inv_abc123",
                "invoice_number": "INV-2025-001",
                "status": "paid",
                "amount": 29.99,
                "currency": "USD",
                "tax": 2.60,
                "subtotal": 27.39,
                "invoice_url": "https://lemonsqueezy.com/invoice/abc123",
                "invoice_date": "2025-10-01T00:00:00Z",
                "due_date": "2025-10-15T00:00:00Z",
                "paid_at": "2025-10-02T14:30:00Z",
                "customer_email": "user@example.com",
                "customer_name": "John Doe",
                "items": [
                    {
                        "description": "Pro Plan - Monthly",
                        "quantity": 1,
                        "unit_price": 29.99,
                        "total": 29.99
                    }
                ]
            }
        }


class InvoiceListResponse(BaseModel):
    """Schema for invoice list response."""
    invoices: List[Invoice] = Field(default_factory=list, description="List of invoices")
    count: int = Field(..., description="Number of invoices returned")

    class Config:
        json_schema_extra = {
            "example": {
                "invoices": [
                    {
                        "invoice_id": "inv_abc123",
                        "invoice_number": "INV-2025-001",
                        "status": "paid",
                        "amount": 29.99,
                        "currency": "USD",
                        "invoice_url": "https://lemonsqueezy.com/invoice/abc123",
                        "invoice_date": "2025-10-01T00:00:00Z",
                        "paid_at": "2025-10-02T14:30:00Z"
                    }
                ],
                "count": 1
            }
        }
