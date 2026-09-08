"""
Admin: Account-Creation IP Allowlist API.

CRUD over the list of public IPs / CIDR ranges that may bypass the per-device
cap on creating multiple non-paid accounts (see ``check_device_account_limit``
in ``src/api/routes/users/auth.py``).

All endpoints require the admin or super_admin role (``is_admin`` dependency).
Mutations are written to the audit log.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.permissions import is_admin
from src.api.schema.account_creation_allowlist_schema import (
    AllowlistEntryCreateRequest,
    AllowlistEntryDeletedResponse,
    AllowlistEntryResponse,
    AllowlistEntryUpdateRequest,
    AllowlistListResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.account_creation_allowlist_service import (
    AccountCreationAllowlistService,
)
from src.utils.audit_helper import create_audit_log_async
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler

router = APIRouter(
    prefix="/account-creation-allowlist",
    tags=["Admin - Account Creation Allowlist"],
)


def _serialize(entry) -> dict:
    return entry.to_dict(include_nulls=True)


@router.get("", response_model=SuccessResponse[AllowlistListResponse])
@db_transaction_handler("list account creation allowlist", auto_commit=False)
async def list_allowlist_entries(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
):
    """
    List every allowlist entry (active and inactive), newest first.

    **Requires admin or super_admin role.**
    """
    service = AccountCreationAllowlistService(db)
    entries = await service.list_entries(include_inactive=True)
    return success(
        data={
            "entries": [_serialize(e) for e in entries],
            "total_count": len(entries),
        },
        request=request,
        message="Account creation allowlist retrieved successfully",
    )


@router.post("", response_model=SuccessResponse[AllowlistEntryResponse])
@db_transaction_handler("create account creation allowlist entry", auto_commit=True)
async def create_allowlist_entry(
    request: Request,
    payload: AllowlistEntryCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
):
    """
    Add an IP address or CIDR range to the allowlist.

    **Requires admin or super_admin role.**

    - 422 if ``ip_address`` is not a valid IPv4/IPv6 address or CIDR range.
    - 409 if the (normalized) address is already in the list.
    """
    admin_user_id = current_user.get("identity")
    service = AccountCreationAllowlistService(db)
    entry = await service.add_entry(
        ip_address=payload.ip_address,
        label=payload.label,
        admin_user_id=UUID(admin_user_id) if admin_user_id else None,
        is_active=payload.is_active,
    )

    await create_audit_log_async(
        db=db,
        user_id=UUID(admin_user_id) if admin_user_id else None,
        action="account_creation_allowlist.create",
        resource_type="account_creation_ip_allowlist",
        resource_id=str(entry.id),
        new_values={
            "ip_address": entry.ip_address,
            "label": entry.label,
            "is_active": entry.is_active,
        },
        request=request,
    )

    return created(
        data=_serialize(entry),
        request=request,
        message="Allowlist entry created successfully",
    )


@router.patch("/{entry_id}", response_model=SuccessResponse[AllowlistEntryResponse])
@db_transaction_handler("update account creation allowlist entry", auto_commit=True)
async def update_allowlist_entry(
    request: Request,
    entry_id: UUID,
    payload: AllowlistEntryUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
):
    """
    Update an entry's ``label`` and/or ``is_active`` flag. The ``ip_address``
    itself is immutable — delete and re-add to change it.

    **Requires admin or super_admin role.** 404 if the entry does not exist.
    """
    admin_user_id = current_user.get("identity")
    # Only forward the fields the client actually sent so unspecified ones keep
    # the service's "leave unchanged" sentinel default.
    fields = payload.model_dump(exclude_unset=True)
    service = AccountCreationAllowlistService(db)
    entry = await service.update_entry(entry_id, **fields)

    await create_audit_log_async(
        db=db,
        user_id=UUID(admin_user_id) if admin_user_id else None,
        action="account_creation_allowlist.update",
        resource_type="account_creation_ip_allowlist",
        resource_id=str(entry.id),
        new_values={
            "ip_address": entry.ip_address,
            "label": entry.label,
            "is_active": entry.is_active,
        },
        request=request,
    )

    return success(
        data=_serialize(entry),
        request=request,
        message="Allowlist entry updated successfully",
    )


@router.delete("/{entry_id}", response_model=SuccessResponse[AllowlistEntryDeletedResponse])
@db_transaction_handler("delete account creation allowlist entry", auto_commit=True)
async def delete_allowlist_entry(
    request: Request,
    entry_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin),
):
    """
    Permanently remove an entry from the allowlist.

    **Requires admin or super_admin role.** 404 if the entry does not exist.
    """
    admin_user_id = current_user.get("identity")
    service = AccountCreationAllowlistService(db)
    entry = await service.get_entry(entry_id)
    old_values = {
        "ip_address": entry.ip_address,
        "label": entry.label,
        "is_active": entry.is_active,
    }
    await service.delete_entry(entry_id)

    await create_audit_log_async(
        db=db,
        user_id=UUID(admin_user_id) if admin_user_id else None,
        action="account_creation_allowlist.delete",
        resource_type="account_creation_ip_allowlist",
        resource_id=str(entry_id),
        old_values=old_values,
        request=request,
    )

    return success(
        data={"id": str(entry_id), "deleted": True},
        request=request,
        message="Allowlist entry deleted successfully",
    )
