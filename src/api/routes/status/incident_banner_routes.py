"""
The incident banner API.

- ``GET /api/v1/status/banner``: any signed-in user. The dashboard's shell reads it about once a
  minute on every page, so it touches no database and never answers with an error for a banner
  that is missing, expired or unreadable: it answers ``active: false``.
- ``PUT`` and ``DELETE /api/v1/admin/status/banner``: switch it on (or replace it) and off.
  They require ``security.manage`` and are written to the audit log.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.incident_banner_schema import (
    IncidentBannerResponse,
    IncidentBannerSetRequest,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services import incident_banner_service
from src.utils.audit_helper import create_audit_log_async
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter(prefix="/status", tags=["Status"])
admin_router = APIRouter(prefix="/status", tags=["Admin - Status"])


@router.get("/banner", response_model=SuccessResponse[IncidentBannerResponse])
async def read_incident_banner(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """The banner showing now, or ``active: false``. For any signed-in user."""
    banner = await incident_banner_service.read_banner()
    return success(data=banner, request=request, message="Incident banner retrieved successfully")


@admin_router.put("/banner", response_model=SuccessResponse[IncidentBannerResponse])
@require_permissions("security.manage", workspace_scoped=False)
@db_transaction_handler("set incident banner", auto_commit=True)
async def set_incident_banner(
    request: Request,
    payload: IncidentBannerSetRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Switch the banner on, or replace the one showing.

    **Requires security.manage.**

    - 422 for an empty or over-long message, an unknown area, or a duration outside 15 minutes
      to 24 hours.
    - 503 if the store that holds the banner can't be reached; no banner is showing then.
    """
    admin_user_id = current_user.get("identity")
    banner = await incident_banner_service.set_banner(
        message=payload.message,
        areas=list(payload.areas),
        duration_minutes=payload.duration_minutes,
    )

    await create_audit_log_async(
        db=db,
        user_id=UUID(admin_user_id) if admin_user_id else None,
        action="incident_banner.set",
        resource_type="incident_banner",
        resource_id="current",
        new_values={
            "message": payload.message,
            "areas": list(payload.areas),
            "duration_minutes": payload.duration_minutes,
        },
        request=request,
    )

    return success(data=banner, request=request, message="Incident banner switched on")


@admin_router.delete("/banner", response_model=SuccessResponse[IncidentBannerResponse])
@require_permissions("security.manage", workspace_scoped=False)
@db_transaction_handler("clear incident banner", auto_commit=True)
async def clear_incident_banner(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Switch the banner off. Answers ``active: false`` whether or not one was showing.

    **Requires security.manage.** 503 if the store can't be reached: a banner may still show.
    """
    admin_user_id = current_user.get("identity")
    was_showing = await incident_banner_service.clear_banner()

    await create_audit_log_async(
        db=db,
        user_id=UUID(admin_user_id) if admin_user_id else None,
        action="incident_banner.clear",
        resource_type="incident_banner",
        resource_id="current",
        new_values={"was_showing": was_showing},
        request=request,
    )

    return success(
        data=dict(incident_banner_service.NO_BANNER),
        request=request,
        message="Incident banner switched off",
    )
