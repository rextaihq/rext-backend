"""License response schemas."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class LicenseAdminRow(BaseModel):
    """Schema for license details in lists or detail views."""

    id: UUID
    license_key: str
    product_name: str
    status: str
    activation_limit: Optional[int] = None
    activation_count: int
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    message: Optional[str] = None


class LicenseActivationRow(BaseModel):
    """Schema for license activation details."""

    id: UUID
    license_id: UUID
    instance_id: str
    instance_name: Optional[str] = None
    is_active: bool
    activated_at: datetime
    deactivated_at: Optional[datetime] = None
    message: Optional[str] = None


class LicenseValidateResponse(BaseModel):
    """Schema for license validation response data."""

    valid: bool
    license_key: str
    status: str
    activated: bool
    activation_limit: Optional[int] = None
    activation_usage: Optional[int] = None
    expires_at: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    product_name: Optional[str] = None
    variant_name: Optional[str] = None
    message: Optional[str] = None


class LicenseActivationData(BaseModel):
    """Schema for the activation result data."""

    activation: LicenseActivationRow
    license: LicenseAdminRow
    message: Optional[str] = None


class LicenseListResponse(BaseModel):
    """Schema for the license list response data."""

    licenses: List[LicenseAdminRow]
    total: int
    message: Optional[str] = None


class LicenseActivationListResponse(BaseModel):
    """Schema for the license activation list response data."""

    activations: List[LicenseActivationRow]
    total: int
    active_count: int
    message: Optional[str] = None


class LicenseRevokeResponse(BaseModel):
    """Schema for the license revocation response data."""

    id: UUID
    license_key: str
    status: str
    revoked_by: UUID
    reason: Optional[str] = None
    message: Optional[str] = None
