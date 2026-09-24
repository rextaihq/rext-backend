"""Schemas for the admin account-creation IP allowlist API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AllowlistEntryCreateRequest(BaseModel):
    """Body for POST /api/v1/admin/account-creation-allowlist."""

    ip_address: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="A single IPv4/IPv6 address or a CIDR range "
        '(e.g. "203.0.113.10" or "203.0.113.0/24"). Stored normalized.',
    )
    label: Optional[str] = Field(
        None,
        max_length=255,
        description='Optional human note, e.g. "London office egress".',
    )
    is_active: bool = Field(
        True,
        description="Whether the entry takes effect immediately (default true).",
    )


class AllowlistEntryUpdateRequest(BaseModel):
    """Body for PATCH /api/v1/admin/account-creation-allowlist/{entry_id}."""

    label: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class AllowlistEntryResponse(BaseModel):
    id: str
    ip_address: str
    label: Optional[str] = None
    is_active: bool
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AllowlistListResponse(BaseModel):
    entries: List[AllowlistEntryResponse]
    total_count: int


class AllowlistEntryDeletedResponse(BaseModel):
    id: str
    deleted: bool
