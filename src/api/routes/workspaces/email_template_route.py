"""
Email Template Routes

Endpoints for managing workspace email templates.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.email_template_schema import (
    CreateEmailTemplateRequest,
    EmailTemplateListResponse,
    EmailTemplateResponse,
    PreviewEmailRequest,
    PreviewEmailResponse,
    TemplateVariablesResponse,
    UpdateEmailTemplateRequest,
)
from src.api.schema.response.workspace_responses import (
    DefaultEmailTemplateResponse,
    EmailTemplateDeleteResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.email_template_service import EmailTemplateService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter(
    prefix="/workspace/email-templates",
    tags=["workspace", "email-templates"],
    responses={404: {"description": "Not found"}},
)


@router.get("/variables/{template_type}", response_model=SuccessResponse[TemplateVariablesResponse])
@require_permissions("workspace.read")
@db_transaction_handler("get template variables", auto_commit=False)
async def get_template_variables(
    template_type: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    """
    Get available variables for a template type.

    Returns the list of variables that can be used in email templates.
    """
    service = EmailTemplateService(db)
    data = await service.get_template_variables(template_type=template_type)
    return success(data=data, message="Template variables retrieved successfully")


@router.post("/preview", response_model=SuccessResponse[PreviewEmailResponse])
@require_permissions("workspace.read")
@db_transaction_handler("preview email template", auto_commit=False)
async def preview_email_template(
    preview_request: PreviewEmailRequest, request: Request, db: AsyncSession = Depends(get_async_db)
):
    """
    Preview an email template with sample data.

    Renders the template with sample variable values to show what it will look like.
    """
    service = EmailTemplateService(db)
    data = await service.preview_template(
        subject=preview_request.subject,
        body=preview_request.body,
        template_type=preview_request.template_type,
    )
    return success(data=data, message="Email template preview generated successfully")


@router.get("/", response_model=SuccessResponse[EmailTemplateListResponse])
@db_transaction_handler("list email templates", auto_commit=False)
async def list_email_templates(
    workspace_id: str,
    request: Request,
    template_type: Optional[str] = Query(None, description="Filter by template type"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all email templates for a workspace.

    Args:
        workspace_id: Workspace UUID (query parameter)
        template_type: Optional filter by template type

    Optionally filter by template type.
    """
    user_id = UUID(current_user.get("identity"))
    service = EmailTemplateService(db)

    data = await service.list_templates(
        workspace_id=UUID(workspace_id), user_id=user_id, template_type=template_type
    )
    return success(data=data, message="Email templates retrieved successfully")


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=SuccessResponse[EmailTemplateResponse]
)
@db_transaction_handler("create email template", auto_commit=True)
@require_permissions("workspace.update", workspace_scoped=True)
async def create_email_template(
    template_data: CreateEmailTemplateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new email template for a workspace.

    Validates template variables and creates the template.
    """
    user_id = UUID(current_user.get("identity"))
    service = EmailTemplateService(db)

    template = await service.create_template(
        workspace_id=UUID(template_data.workspace_id),
        user_id=user_id,
        template_type=template_data.template_type,
        subject=template_data.subject,
        body=template_data.body,
    )

    return success(data=template.to_dict(), message="Email template created successfully")


@router.put("/{template_id}", response_model=SuccessResponse[EmailTemplateResponse])
@db_transaction_handler("update email template", auto_commit=True)
@require_permissions("workspace.update", workspace_scoped=True)
async def update_email_template(
    template_id: str,
    template_data: UpdateEmailTemplateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update an existing email template.

    Validates template variables if subject or body is being updated.
    """
    user_id = UUID(current_user.get("identity"))
    service = EmailTemplateService(db)

    template = await service.update_template(
        template_id=UUID(template_id),
        user_id=user_id,
        subject=template_data.subject,
        body=template_data.body,
        is_active=template_data.is_active,
    )

    return success(data=template.to_dict(), message="Email template updated successfully")


@router.delete("/{template_id}", response_model=SuccessResponse[EmailTemplateDeleteResponse])
@db_transaction_handler("delete email template", auto_commit=True)
@require_permissions("workspace.update", workspace_scoped=True)
async def delete_email_template(
    template_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Delete an email template.

    Cannot delete default templates.
    """
    user_id = UUID(current_user.get("identity"))
    service = EmailTemplateService(db)

    await service.delete_template(template_id=UUID(template_id), user_id=user_id)

    return success(data={"template_id": template_id}, message="Email template deleted successfully")


@router.get(
    "/defaults/{template_type}", response_model=SuccessResponse[DefaultEmailTemplateResponse]
)
@require_permissions("workspace.read")
@db_transaction_handler("get default template", auto_commit=False)
async def get_default_template_for_type(
    template_type: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    """
    Get the default template for a specific type.

    Useful for resetting or starting with a default template.
    """
    service = EmailTemplateService(db)
    data = await service.get_default_template(template_type=template_type)
    return success(data=data, message="Default template retrieved successfully")
